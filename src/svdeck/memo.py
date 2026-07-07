"""カード用途メモ(LLM走査用の自由文コーパス)を生成する。

タグ(離散・厳密)では引けない抽象クエリ(「回復を無意味化できるカード」等)のために、
skill_text忠実(装飾タグのみ除去)＋card_noteを1カード1行のテキストに整形する。card_atom由来の
効果要約は skill_text の冗長コピーで無価値化したため廃止(design.md §6.1 2026-07-07改訂)。
全カード分でも約100KBに収まり、LLMが1回で全readして意味検索できる。再取得後に再実行して作り直す。

実行: python -m svdeck.memo  (data/card_memo.txt を出力)
"""

import re

from svdeck.db import DB_PATH, connect

MEMO_PATH = DB_PATH.parent / "card_memo.txt"


def build_memo(skill_text: str | None, note: str | None) -> str:
    # AI_NOTE: skill_textは<color=...>等の装飾タグだけ除去し文面は忠実に残す(要約しない)。noteは末尾に" / note:"で連結。
    text = re.sub(r"</?color[^>]*>", "", skill_text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if note:
        text = f"{text} / note:{note}"
    return text


def run() -> None:
    conn = connect()
    try:
        lines = [
            f"{cid}|{cls}|{cost}|{name}|{build_memo(skill_text, note)}"
            for cid, name, cls, cost, skill_text, note in conn.execute(
                "SELECT c.card_id, c.name, c.class_name, c.cost, c.skill_text, n.note "
                "FROM card c LEFT JOIN card_note n USING(card_id) WHERE c.is_token=0 ORDER BY c.card_id"
            )
        ]
    finally:
        conn.close()
    MEMO_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[memo] {len(lines)}枚 → {MEMO_PATH}")


if __name__ == "__main__":
    run()
