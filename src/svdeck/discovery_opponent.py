"""固定したDBの相手構築と効果を、比較用の追加資料へまとめる。"""

from __future__ import annotations

import json
from pathlib import Path

from svdeck.discovery_evidence import CLASSES, JSONDict, _card_rows, _related_cards, read_only


def opponent_sources(db: Path, context: JSONDict, deck_ids: list[int]) -> JSONDict:
    # AI_NOTE: 全構築を検査してから資料を返し、途中の不正な構築を除外して成功扱いしない。
    if not deck_ids or any(type(n) is not int or n <= 0 for n in deck_ids):
        raise ValueError("相手構築のIDは正の整数を1件以上指定してください")
    if len(set(deck_ids)) != len(deck_ids):
        raise ValueError("相手構築のIDが重複しています")
    conn = read_only(db)
    try:
        sources = []
        for did in deck_ids:
            deck = conn.execute("SELECT name,format,url,tier,updated_on,fetched_at FROM meta_deck WHERE id=?",
                                (did,)).fetchone()
            if deck is None or deck[1] != context["format"]:
                raise ValueError(f"相手構築 {did} がないか、探索とフォーマットが異なります")
            entries = list(conn.execute("SELECT card_id,card_name,count FROM meta_deck_card WHERE deck_id=? ORDER BY card_id",
                                        (did,)))
            if (not entries or any(type(cid) is not int or type(n) is not int or n <= 0 for cid, _, n in entries)
                    or sum(n for _, _, n in entries) != 40 or len({cid for cid, _, _ in entries}) != len(entries)):
                raise ValueError(f"相手構築 {did} は一意なカードIDと正の枚数からなる40枚が必要です")
            ids = {cid for cid, _, _ in entries}
            rows = _card_rows(conn, context["class_name"], context["format"])
            by_id = {c["card_id"]: c for c in rows}
            if not ids <= by_id.keys():
                raise ValueError(f"相手構築 {did} にDB未収録のカードがあります")
            classes = {by_id[cid]["class_name"] for cid in ids} - {"ニュートラル"}
            if len(classes) != 1 or not classes <= set(CLASSES):
                raise ValueError(f"相手構築 {did} のクラスを一意に確認できません")
            opponent_class = next(iter(classes))
            named_counts: dict[str, int] = {}
            named_limits: dict[str, int] = {}
            for cid, _, count in entries:
                card = by_id[cid]
                if (card["is_token"] or count > (card["copy_limit"] or 0)
                        or (context["format"] == "rotation" and not card["rotation"])):
                    raise ValueError(f"相手構築 {did} のカード {cid} は保存版の構築条件に適合しません")
                name = card["name"]
                named_counts[name] = named_counts.get(name, 0) + count
                named_limits[name] = min(named_limits.get(name, card["copy_limit"]), card["copy_limit"])
            # AI_NOTE: 再録の別IDも同名の上限を共有するため、ID別の検査に加えて合算する。
            if any(count > named_limits[name] for name, count in named_counts.items()):
                raise ValueError(f"相手構築 {did} は再録を含む同名カードの枚数上限を超えています")
            # AI_NOTE: 参照先は既存の探索規則で辿るが、相手構築から到達する効果だけを採用する。
            for card in rows:
                card["deck_eligible"] = card["card_id"] in ids
            expanded = _related_cards(rows, context["ability_keywords"],
                                      dict(conn.execute("SELECT id,name FROM card_set ORDER BY id")))
            related = {c["card_id"]: c for c in expanded}
            selected, pending = set(ids), list(ids)
            while pending:
                card = related[pending.pop()]
                for cid in card.get("related_card_ids", []):
                    if cid not in selected:
                        selected.add(cid)
                        pending.append(cid)
            counts = {cid: n for cid, _, n in entries}
            listed_names = {cid: name for cid, name, _ in entries}
            cards = []
            for cid in sorted(selected):
                card = related[cid]
                cards.append({**card, "deck_eligible": bool(not card["is_token"] and card["copy_limit"]
                              and card["class_name"] in (opponent_class, "ニュートラル")
                              and (context["format"] == "unlimited" or card["rotation"])),
                              "in_reference_deck": cid in ids, "count": counts.get(cid, 0),
                              "listed_name": listed_names.get(cid)})
            source_column = "source_json" in {r[1] for r in conn.execute("PRAGMA table_info(meta_deck)")}
            source = conn.execute("SELECT source_json FROM meta_deck WHERE id=?", (did,)).fetchone()[0] if source_column else None
            payload = {"version": 1, "snapshot_sha256": context["snapshot_sha256"],
                       "snapshot_captured_at": context["captured_at"], "format": context["format"],
                       "own_class": context["class_name"], "opponent_class": opponent_class,
                       "deck": {"id": did, "name": deck[0], "url": deck[2], "saved_tier": deck[3],
                                "updated_on": deck[4], "fetched_at": deck[5], "total_cards": 40,
                                "source": json.loads(source) if source else None}, "cards": cards,
                       "interpretation": "相手が採用しうる札と参照効果の保存資料。手札・PP・盤面・取得頻度・現在の普及を示さない。"
                                         "構築外の参照札は、本文の生成条件を満たす場合だけ使用できる。"}
            sources.append({"title": f"相手の保存構築と効果：{deck[0]}", "kind": "opponent-deck-material",
                            "location": f"snapshot:{context['snapshot_sha256']}:meta_deck/{did}",
                            "observed_at": context["captured_at"],
                            "content": json.dumps(payload, ensure_ascii=False, indent=2),
                            "limitations": ["保存版で合法な40枚。最新公式や実戦の再確認は行っていない。",
                                            "採用枚数は取得率・常に持っていることの証明ではない。",
                                            "カード注記は評価を含む保存情報で、公式の効果本文と区別する。"]})
        return {"sources": sources}
    finally:
        conn.close()
