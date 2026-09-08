"""保存された全40枚の構築2件から、実際の交換札を集計する。"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from svdeck.discovery_evidence import JSONDict, digest, read_only
from svdeck.discovery_sources import load_sources, save_sources


def _distribution(cards: list[JSONDict], field: str) -> dict[str, int]:
    # AI_NOTE: 不明な属性は不明のまま数え、別の種類やコストへ補完しない。
    counts: dict[str, int] = {}
    for card in cards:
        key = str(card[field]) if card[field] is not None else "unknown"
        counts[key] = counts.get(key, 0) + card["count"]
    return dict(sorted(counts.items()))


def _deck(source: JSONDict, catalog: dict[int, JSONDict], context: JSONDict) -> JSONDict:
    # AI_NOTE: 全リストを厳密に受け取り、原資料の名前と保存DBの属性を区別して集計する。
    try:
        entries = json.loads(source["content"])
    except ValueError as exc:
        raise ValueError(f"{source['source_hash']}: contentには全40枚のJSON配列が必要です。部分内訳から補完しません") from exc
    if not isinstance(entries, list):
        raise ValueError("contentはcard_id/countと任意のnameを持つJSON配列です。総数内訳だけでは比較できません")
    result = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or not {"card_id", "count"} <= set(entry) <= {"card_id", "count", "name"}:
            raise ValueError("各札にはcard_id/countと任意のnameだけを指定してください")
        cid, count = entry["card_id"], entry["count"]
        if type(cid) is not int or type(count) is not int or count <= 0:
            raise ValueError("card_idは整数、countは1以上の整数です")
        if cid in seen:
            raise ValueError(f"同じcard_idが重複しています: {cid}")
        if cid not in catalog:
            raise ValueError(f"保存DBにないcard_idです: {cid}。名前や内訳から推測しません")
        if "name" in entry and not isinstance(entry["name"], str):
            raise ValueError("任意のnameを指定する場合は原資料の文字列を使ってください")
        seen.add(cid)
        card = catalog[cid]
        issues = []
        if card["class_name"] not in (context["class_name"], "ニュートラル"):
            issues.append("対象クラス外")
        if context["format"] == "rotation" and not card["rotation"]:
            issues.append("保存DBではローテーション対象外")
        if card["is_token"]:
            issues.append("生成専用カード")
        if card["copy_limit"] is None:
            issues.append("採用上限が保存DBで不明")
        elif count > card["copy_limit"]:
            issues.append(f"保存DBの採用上限{card['copy_limit']}枚を超過")
        result.append({**card, "count": count, "recorded_name": entry.get("name"), "eligibility_issues": issues})
    total = sum(card["count"] for card in result)
    if total != 40:
        raise ValueError(f"全40枚が必要ですが{total}枚です。欠けた札や枚数は推測しません")
    return {"source_hash": source["source_hash"], "total_count": total,
            "cards": sorted(result, key=lambda card: card["card_id"]),
            "type_counts": _distribution(result, "type"), "cost_counts": _distribution(result, "cost")}


def compare_decks(session: Path, context: JSONDict, before_hash: str, after_hash: str) -> JSONDict:
    # AI_NOTE: 検証済みの2資料と保存DBだけで計算し、同じ入力なら同じ識別値で資料へ追記する。
    sources = {source["source_hash"]: source for source in load_sources(session)}
    if before_hash not in sources or after_hash not in sources:
        raise ValueError("比較する2件には、この探索にattachした資料のsource_hashを指定してください")
    conn = read_only(session / "snapshot.db")
    conn.row_factory = sqlite3.Row
    try:
        catalog = {row["card_id"]: dict(row) for row in conn.execute(
            "SELECT card_id,name,cost,type_category AS type,class_name,is_token,"
            "is_include_rotation AS rotation,deck_enabled_num AS copy_limit FROM card")}
    finally:
        conn.close()
    before, after = (_deck(sources[key], catalog, context) for key in (before_hash, after_hash))
    before_counts = {card["card_id"]: card["count"] for card in before["cards"]}
    after_counts = {card["card_id"]: card["count"] for card in after["cards"]}
    added: list[JSONDict] = []
    removed: list[JSONDict] = []
    for cid in sorted(before_counts.keys() | after_counts.keys()):
        change = after_counts.get(cid, 0) - before_counts.get(cid, 0)
        if change:
            (added if change > 0 else removed).append({"card_id": cid, "name": catalog[cid]["name"], "count": abs(change)})
    added_count, removed_count = sum(card["count"] for card in added), sum(card["count"] for card in removed)
    kinds = before["type_counts"].keys() | after["type_counts"].keys()
    delta = {"added": added, "removed": removed, "added_count": added_count, "removed_count": removed_count,
             "exchanged_count": added_count,
             "type_net_change": {kind: after["type_counts"].get(kind, 0) - before["type_counts"].get(kind, 0)
                                 for kind in sorted(kinds)}}
    limits = ["元資料の実在・正しさ、勝率、交換の強さは判定しない。",
              "名前・種類・コスト・採用上限と採用上の問題は探索開始時の保存DBによる。過去の能力・合法性を復元しない。",
              "原資料の名前はrecorded_nameに保持し、nameは保存DBから取得した名前。",
              "exchanged_countは入れた総枚数（抜いた総枚数と同じ）。種別の純増減type_net_changeとは別。"]
    value = {"before_source_hash": before_hash, "after_source_hash": after_hash,
             "snapshot_sha256": context["snapshot_sha256"], "class_name": context["class_name"],
             "format": context["format"], "before": before, "after": after, "delta": delta, "limitations": limits}
    source = {"title": "全40枚の構築間での交換札と分布", "kind": "機械計算",
              "location": f"before source_hash={before_hash}; after source_hash={after_hash}",
              "observed_at": None, "content": json.dumps(value, ensure_ascii=False, indent=2), "limitations": limits}
    saved = save_sources(session, {"sources": [source]})
    return {**value, "source_hash": digest(source), "saved_new": bool(saved["added"])}
