"""固定DBの保存分析を、本文へ照合する未検証の資料として追記する。"""

from __future__ import annotations

import json
from pathlib import Path

from svdeck.discovery_evidence import JSONDict, digest, read_only
from svdeck.discovery_sources import save_sources

LIMITATIONS = [
    "保存分析はAIによる未検証の下書き。効果本文・進化・参照先・注記を優先して照合する。",
    "抽出元本文の版は未保存。抽出日時と現在本文だけでは同じ版と確認できない。",
    "増減には発動条件との接続不足、重なる集合、取得枚数と純増の混在があり、そのまま合計できない。",
    "分析が空・未保存であることを、効果や状態変化が存在しない証拠にしない。",
    "保存分析内のタグは旧表記を含み得る。現在の検索タグはcard.tagsに保持する。",
    "資料への包含は採用可能性、生成可能性、コンボの成立、強さ、新規性の認定ではない。",
]


def save_effects(session: Path, context: JSONDict, card_ids: list[int]) -> JSONDict:
    # AI_NOTE: 全選択とJSONを先に検査し、途中の不備で一部だけ追記しない。
    cards = {c["card_id"]: c for c in context["cards"]}
    if not card_ids or any(type(cid) is not int or cid not in cards for cid in card_ids):
        raise ValueError("固定資料に含まれるカードIDを1件以上指定してください")
    sources = []
    conn = read_only(session / "snapshot.db")
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for cid in sorted(set(card_ids)):
            analyses = {}
            for table, column in (("card_atom", "atoms_json"), ("card_vschema", "schema_json")):
                row = (conn.execute(f"SELECT {column},model,extracted_at FROM {table} WHERE card_id=?", (cid,)).fetchone()
                       if table in tables else None)
                analyses[table] = {"availability": "stored" if row else "not_saved",
                                   "value": json.loads(row[0]) if row else None,
                                   "model": row[1] if row else None,
                                   "extracted_at": row[2] if row else None,
                                   "source_text_version": "unverified"}
            card = cards[cid]
            content = {"card": card, "stored_analyses": analyses,
                       "context_sha256": digest(context), "snapshot_sha256": context["snapshot_sha256"],
                       "interpretation": "本文と条件を照合するための保存資料。自動計算・意味検証はしていない。"}
            sources.append({"title": f"{card['name']}：本文と未検証の保存分析", "kind": "stored_effect_analysis",
                            "location": f"snapshot:{context['snapshot_sha256']}#card:{cid}",
                            "observed_at": context["captured_at"],
                            "content": json.dumps(content, ensure_ascii=False, indent=2),
                            "limitations": [*LIMITATIONS, "observed_atは探索用DBの固定時刻で、分析や公式本文の再確認時刻ではない。"]})
    finally:
        conn.close()
    return save_sources(session, {"sources": sources})
