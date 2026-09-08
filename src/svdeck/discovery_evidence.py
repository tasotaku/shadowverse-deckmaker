"""探索の入力を固定し、登録済みアンカーに限らない全文資料を作る。"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, cast

from svdeck.bench import CategoryLookup, FULFILLMENT_MAP_PATH, FulfillmentMap, FulfillmentMapRaw, parse_tag
from svdeck.explore import tag_search

JSONDict = dict[str, Any]
CLASSES = ("エルフ", "ロイヤル", "ウィッチ", "ドラゴン", "ナイトメア", "ビショップ", "ネメシス")
TEXT_FIELDS = ("skill_text", "evolution_text", "ref_effect_text", "note")


def digest(value: object) -> str:
    # AI_NOTE: キー順や改行に依存せず、資料と回答を結びつける。
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def read_object(path: Path) -> JSONDict:
    # AI_NOTE: ファイル境界でJSONの最上位型を検査する。
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSONオブジェクトが必要です: {path}")
    return value


def write_new(path: Path, value: object) -> None:
    # AI_NOTE: 排他的作成で既存の実験入力・改訂・評価を上書きしない。
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def plain(text: str | None) -> str:
    # AI_NOTE: 公式装飾タグだけを除き、値やキーワードと改行を保持する。
    return html.unescape(re.sub(r"<[^>]+>", "", (text or "").replace("<hr>", "\n"))).replace("\\n", "\n")


def read_only(path: Path) -> sqlite3.Connection:
    # AI_NOTE: 調査入口から本番DBのスキーマ作成や変更を起こさない。
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _card_rows(conn: sqlite3.Connection, class_name: str, format_name: str) -> list[JSONDict]:
    # AI_NOTE: 本文・進化・参照先・供給側を含む注記を同じDB版から取得する。
    result: list[JSONDict] = []
    sql = """SELECT c.card_id,c.name,c.class_name,c.cost,c.atk,c.life,c.type_category,
             c.is_token,c.is_include_rotation,c.deck_enabled_num,c.skill_text,
             c.evo_json,c.ref_effect_text,n.note,n.updated_at,c.card_set_id
             FROM card c LEFT JOIN card_note n ON n.card_id=c.card_id ORDER BY c.card_id"""
    for row in conn.execute(sql):
        cid, name, cls, cost, atk, life, kind, token, rotation, limit, skill, evo, ref, note, date, pack = row
        evolution = json.loads(evo) if evo else None
        evo_text = evolution.get("skill_text", "") if isinstance(evolution, dict) else ""
        eligible = bool(not token and limit and cls in (class_name, "ニュートラル")
                        and (format_name == "unlimited" or rotation))
        result.append({
            "card_id": cid, "name": name, "class_name": cls, "cost": cost, "atk": atk, "life": life,
            "type": kind, "is_token": bool(token), "rotation": bool(rotation), "copy_limit": limit,
            "card_set_id": pack, "deck_eligible": eligible,
            "tribes": [r[0] for r in conn.execute(
                "SELECT t.name FROM tribe t JOIN card_tribe ct ON ct.tribe_id=t.id WHERE ct.card_id=? ORDER BY t.id", (cid,))],
            "skill_text": plain(skill), "evolution_text": plain(evo_text), "ref_effect_text": plain(ref),
            "note": note or "", "note_updated_at": date,
            "raw": {"skill_text": skill, "evo": evolution, "ref_effect_text": ref},
            "source_url": f"https://shadowverse-wb.com/web/CardList/card?card_id={cid}&lang=ja",
            "tags": [{"kind": k, "tag": t} for k, t in conn.execute(
                "SELECT kind,tag FROM atom_tag WHERE card_id=? ORDER BY kind,tag", (cid,))],
            "requirements": [dict(zip(("type", "requirement", "tag", "deadline", "status", "note"), r))
                             for r in conn.execute("SELECT req_type,requirement,req_tag,deadline_turn,status,note "
                                                   "FROM anchor_require WHERE card_id=? ORDER BY id", (cid,))],
        })
    return result


def _related_cards(cards: list[JSONDict], keywords: dict[str, str], sets: dict[int, str]) -> list[JSONDict]:
    # AI_NOTE: 名前参照と用語定義のパック参照を辿り、集合名だけの生成を取りこぼさぬよう全トークンも添える。
    # 資料への包含は生成可能性の証明ではない。採用合法性とは分けて保持する。
    selected = {c["card_id"] for c in cards if c["deck_eligible"] or c["is_token"]}
    names: dict[str, list[int]] = {}
    for card in cards:
        names.setdefault(card["name"], []).append(card["card_id"])
    by_id = {c["card_id"]: c for c in cards}
    pending = list(selected)
    while pending:
        card = by_id[pending.pop()]
        text = "\n".join(card[field] for field in TEXT_FIELDS[:3])
        definitions: set[str] = set()
        while True:
            found = {title for title in keywords if title in text} - definitions
            if not found:
                break
            definitions |= found
            text += "\n" + "\n".join(keywords[title] for title in sorted(found))
        referenced_sets = {sid for sid, name in sets.items() if name and name in text}
        collection = {c["card_id"] for c in cards if c["card_set_id"] in referenced_sets}
        related = sorted({cid for name, ids in names.items() if name and name in text
                          for cid in ids if cid != card["card_id"]} | (collection - {card["card_id"]}))
        card["referenced_keywords"] = sorted(definitions)
        card["referenced_card_sets"] = sorted(referenced_sets)
        card["related_card_ids"] = related
        for cid in related:
            if cid not in selected:
                selected.add(cid)
                pending.append(cid)
    return [c for c in cards if c["card_id"] in selected]


def _known_decks(conn: sqlite3.Connection, cards: list[JSONDict], format_name: str) -> list[JSONDict]:
    # AI_NOTE: フォーマットとクラスを揃え、同居を新規性の証明や強さの加点にしない素材を返す。
    eligible = {c["card_id"] for c in cards if c["deck_eligible"]}
    classes = {c["class_name"] for c in cards if c["deck_eligible"]} - {"ニュートラル"}
    decks = []
    # AI_NOTE: 固定済みの旧DBは移行せず、来歴列が無い場合も未保存として読み出す。
    source_column = "source_json" if "source_json" in {r[1] for r in conn.execute("PRAGMA table_info(meta_deck)")} else "NULL"
    for did, name, url, tier, updated, fetched, source in conn.execute(
        f"SELECT id,name,url,tier,updated_on,fetched_at,{source_column} FROM meta_deck WHERE format=? ORDER BY id", (format_name,)
    ):
        entries = [{"card_id": cid, "name": cname, "count": count, "class_name": cls,
                    "currently_eligible": cid in eligible} for cid, cname, count, cls in conn.execute(
            "SELECT m.card_id,m.card_name,m.count,c.class_name FROM meta_deck_card m "
            "LEFT JOIN card c ON c.card_id=m.card_id WHERE deck_id=?", (did,))]
        deck_classes = {e["class_name"] for e in entries} - {"ニュートラル", None}
        if entries and deck_classes and deck_classes <= classes:
            decks.append({"id": did, "name": name, "url": url, "tier": tier, "updated_on": updated,
                          "fetched_at": fetched, "cards": entries, "source": json.loads(source) if source else None,
                          "currently_legal_list": all(e["currently_eligible"] for e in entries),
                          "interpretation": "保存時点の既知例。更新日と各札の現在の合法性を確認して比較する。"})
    return decks


def build_context(conn: sqlite3.Connection, class_name: str, format_name: str,
                  objective: str, docs: Path, captured_at: str) -> JSONDict:
    # AI_NOTE: 対象全文・ルール・関連する判定原則を一つの固定入力にまとめる。
    if class_name not in CLASSES or format_name not in ("rotation", "unlimited"):
        raise ValueError("対応するクラスとフォーマットを指定してください")
    keywords = dict(conn.execute("SELECT title,text FROM ability_keyword ORDER BY title"))
    sets = dict(conn.execute("SELECT id,name FROM card_set ORDER BY id"))
    cards = _related_cards(_card_rows(conn, class_name, format_name), keywords, sets)
    if not any(c["deck_eligible"] for c in cards):
        raise ValueError("採用可能なカードがありません")
    design = (docs / "design.md").read_text(encoding="utf-8")
    sections = re.split(r"(?=^## )", design, flags=re.MULTILINE)
    principles = "\n".join(s for s in sections if re.match(r"## (?:1\.|1\.5 |3\.|5\.|6\.|7\.|8\.)", s))
    return {"version": 1, "objective": objective, "class_name": class_name, "format": format_name,
            "captured_at": captured_at, "freshness": "ローカルDBの保存版。取得時刻は能力の適用日や公式再確認日ではない。",
            "cards": cards, "known_decks": _known_decks(conn, cards, format_name),
            "rules": (docs / "rules.md").read_text(encoding="utf-8"), "principles": principles,
            "ability_keywords": keywords, "card_sets": sets,
            "related_coverage": "名前参照、公式用語定義のパック参照、全生成専用カードを収録。"
                                "資料にあることは、その手順で生成できる証明ではない。集合の内容は原文・定義で確認する。",
            "fulfillment_map": read_object(FULFILLMENT_MAP_PATH)}


def search_questions(conn: sqlite3.Connection, context: JSONDict, questions: list[JSONDict]) -> list[JSONDict]:
    # AI_NOTE: 仮説から新しく生じた要求を既存の型検索へ戻し、0件でも全文走査を残す。
    fmap = FulfillmentMap(cast(FulfillmentMapRaw, context["fulfillment_map"]))
    lookup = CategoryLookup(conn)
    result = []
    allowed = {c["card_id"] for c in context["cards"] if c["deck_eligible"]}
    for question in questions:
        tag = question.get("tag")
        hits = tag_search(conn, parse_tag(tag), fmap, lookup, context["class_name"], context["format"], -1) if tag else []
        direct = {row[0] for row in conn.execute(
            "SELECT card_id FROM atom_tag WHERE kind='supply' AND tag=?", (tag,))} if tag else set()
        matched = {h.card_id for h in hits} | direct
        result.append({**question, "tag_hits": sorted(matched & allowed),
                       "direct_supply_hits": sorted(direct & allowed),
                       "requirement_matches": [h.card_id for h in hits if h.card_id in allowed],
                       "interpretation": "型検索は手掛かり。本文・注記で用途と起動条件を確認し、全文でも探す。"})
    return result


def check_evidence(items: object, cards: dict[int, JSONDict], keywords: dict[str, str] | None = None,
                   sources: list[JSONDict] | None = None) -> None:
    # AI_NOTE: 架空の出典や引用を拒む。引用が主張を支えるかは別評価で判断する。
    if not isinstance(items, list):
        raise ValueError("evidence は配列で指定してください")
    for ref in items:
        if not isinstance(ref, dict):
            raise ValueError("根拠は card_id / field / quote を持つオブジェクトです")
        cid, field, quote = ref.get("card_id"), ref.get("field"), ref.get("quote")
        if "source_hash" in ref:
            source = next((s for s in sources or [] if s["source_hash"] == ref["source_hash"]), None)
            if (set(ref) != {"source_hash", "quote"} or source is None or not isinstance(quote, str)
                    or not quote.strip() or quote not in source["content"]):
                raise ValueError("資料の引用が固定packet内のcontentと一致しません")
            continue
        if "keyword" in ref:
            title = ref["keyword"]
            if (not isinstance(title, str) or not keywords or title not in keywords or not isinstance(quote, str)
                    or not quote.strip() or quote not in keywords[title]):
                raise ValueError("キーワードの引用が固定資料の定義と一致しません")
            continue
        if type(cid) is not int or cid not in cards or field not in TEXT_FIELDS:
            raise ValueError("資料内のカードIDと本文・進化・参照先・注記を参照してください")
        if not isinstance(quote, str) or not quote.strip() or quote not in cards[cid][field]:
            raise ValueError(f"引用が固定資料の原文と一致しません: {cid}/{field}")
