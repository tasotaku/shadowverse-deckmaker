"""能力調整(ナーフ/アッパー)の告知を受けて、card_id指定で1枚だけミラーを更新する。

公式APIは単体カード取得に対応しない(card_idフィルタが無視され全件が返る)ため、全件fetchを
回さず調整を反映する手段としてこのモジュールを使う。告知に載る新しい値を人が渡し、その1枚の
card列とcommon_jsonを書き換え、変化した項目をcard_change履歴へ残す。

実行例:
    python -m svdeck.apply_change 10001110 atk=1 life=3 skill_text="新しい能力テキスト"
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from svdeck.db import connect

# 調整で個別更新を許可する項目。card列名 = common_jsonのキーと1:1対応。
UPDATABLE_FIELDS = ("skill_text", "cost", "atk", "life", "deck_enabled_num")
# INTEGER列。CLIの文字列入力をintへ変換する対象。
INT_FIELDS = frozenset({"cost", "atk", "life", "deck_enabled_num"})


def apply_card_change(
    conn: sqlite3.Connection, card_id: int, changes: dict[str, Any], today: str
) -> int:
    # AI_NOTE: 1枚だけの調整適用。card列とcommon_jsonを同時に書き換え、実際に変化した項目のみ
    # card_changeへ記録する。fieldはUPDATABLE_FIELDSでホワイトリスト検証してからSQLへ埋めるため
    # インジェクション不可。存在しないcard_id・不正fieldは人手入力の境界としてValueErrorで落とす。
    row = conn.execute("SELECT common_json FROM card WHERE card_id = ?", (card_id,)).fetchone()
    if row is None:
        raise ValueError(f"card_id={card_id} は card テーブルに存在しません")
    common = json.loads(row[0])

    for field in changes:
        if field not in UPDATABLE_FIELDS:
            raise ValueError(f"更新不可なフィールドです: {field} (許可: {', '.join(UPDATABLE_FIELDS)})")

    applied = 0
    for field, new_value in changes.items():
        old_value = conn.execute(
            f"SELECT {field} FROM card WHERE card_id = ?", (card_id,)
        ).fetchone()[0]
        if str(old_value) == str(new_value):
            continue
        conn.execute(f"UPDATE card SET {field} = ? WHERE card_id = ?", (new_value, card_id))
        common[field] = new_value
        conn.execute(
            "INSERT INTO card_change (snapshot_date, card_id, field, old_value, new_value) "
            "VALUES (?, ?, ?, ?, ?)",
            (today, card_id, field, str(old_value), str(new_value)),
        )
        print(f"  {field}: {old_value} -> {new_value}")
        applied += 1

    if applied:
        conn.execute(
            "UPDATE card SET common_json = ? WHERE card_id = ?",
            (json.dumps(common, ensure_ascii=False), card_id),
        )
    return applied


def _parse_change(token: str) -> tuple[str, Any]:
    # AI_NOTE: CLIの "field=value" を分解する。INT_FIELDSは数値へ変換し、変換失敗は入力ミスとして落とす。
    if "=" not in token:
        raise ValueError(f"'field=value' 形式で指定してください: {token!r}")
    field, raw = token.split("=", 1)
    field = field.strip()
    if field in INT_FIELDS:
        try:
            return field, int(raw)
        except ValueError:
            raise ValueError(f"{field} は整数で指定してください: {raw!r}")
    return field, raw


def run() -> None:
    # AI_NOTE: CLIエントリポイント。card_idと複数の field=value を受け、1トランザクションで適用してcommitする。
    parser = argparse.ArgumentParser(description="能力調整をcard_id指定で1枚だけ適用する")
    parser.add_argument("card_id", type=int)
    parser.add_argument("changes", nargs="+", metavar="field=value")
    args = parser.parse_args()

    changes = dict(_parse_change(token) for token in args.changes)
    today = datetime.now(timezone.utc).astimezone().date().isoformat()

    conn = connect()
    try:
        card = conn.execute(
            "SELECT name FROM card WHERE card_id = ?", (args.card_id,)
        ).fetchone()
        name = card[0] if card else "?"
        print(f"[apply] card_id={args.card_id} ({name})")
        applied = apply_card_change(conn, args.card_id, changes, today)
        conn.commit()
    finally:
        conn.close()

    print(f"[apply] 完了: {applied}項目を更新" if applied else "[apply] 変更なし(値が現状と同じ)")


if __name__ == "__main__":
    run()
