"""タグ昇格CLI(promote)。LLM走査で見つけた「タグ+該当card_id群」を提案→人確認で
atom_tag(kind='supply')に書き込む。design.md §6.1「タグ昇格フェーズ」。

atom_tagは card_atom からの派生層で再抽出時に作り直されるため、昇格の正本は git 追跡の
data/promoted_tags.json 側に置き(design §8-8 ledger流儀)、再抽出後は --reapply で atom_tag へ戻す。

実行:
  PYTHONPATH=src python -m svdeck.promote --tag "守護付与" --cards 10032110,10234120           # 提案(DB無変更)
  PYTHONPATH=src python -m svdeck.promote --tag "守護付与" --cards 10032110,10234120 --confirm  # 確定(書込+追記)
  PYTHONPATH=src python -m svdeck.promote --reapply                                             # 再抽出後の再適用
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from svdeck.db import connect

PROMOTED_PATH = Path(__file__).resolve().parent / "data" / "promoted_tags.json"


class PromotedEntry(TypedDict):
    card_id: int
    tag: str
    confirmed_at: str


def load_promoted() -> list[PromotedEntry]:
    # AI_NOTE: 昇格の正本(git追跡JSON)を読む。ファイル不在は空扱い(初回)。
    if not PROMOTED_PATH.exists():
        return []
    entries: list[PromotedEntry] = json.loads(PROMOTED_PATH.read_text(encoding="utf-8"))
    return entries


def save_promoted(entries: list[PromotedEntry]) -> None:
    # AI_NOTE: 人が差分を読めるよう ensure_ascii=False + 整形で書き出す(fulfillment_map等と同じ流儀)。
    PROMOTED_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_names(conn: sqlite3.Connection, card_ids: list[int]) -> tuple[list[tuple[int, str]], list[int]]:
    # AI_NOTE: card_id→nameを引き、存在するもの/しないものに二分する(提案の確認材料+未知IDガード)。
    found, missing = [], []
    for card_id in card_ids:
        row = conn.execute("SELECT name FROM card WHERE card_id = ?", (card_id,)).fetchone()
        if row is None:
            missing.append(card_id)
        else:
            found.append((card_id, row[0]))
    return found, missing


def propose(conn: sqlite3.Connection, tag: str, card_ids: list[int]) -> None:
    # AI_NOTE: 確認材料の表示のみ・DBは一切変更しない(提案→人確認ゲートの提案側)。
    found, missing = _resolve_names(conn, card_ids)
    print(f"[提案] supplyタグ「{tag}」を次の{len(found)}枚に付与:")
    for card_id, name in found:
        print(f"  {card_id} {name}")
    if missing:
        print(f"  (未知card_idはスキップ対象: {', '.join(map(str, missing))})")
    print("確認するには --confirm を付けて再実行（atom_tag書込 + promoted_tags.json追記）")


def confirm(conn: sqlite3.Connection, tag: str, card_ids: list[int]) -> None:
    # AI_NOTE: 確定側。存在するcard_idのみ atom_tag(kind='supply') に INSERT OR IGNORE で書き、
    # 正本の promoted_tags.json に (card_id, tag) 未登録分だけ追記する(二重追記防止)。
    found, missing = _resolve_names(conn, card_ids)
    entries = load_promoted()
    existing = {(e["card_id"], e["tag"]) for e in entries}
    now = datetime.now().isoformat(timespec="seconds")
    written = 0
    for card_id, _ in found:
        conn.execute(
            "INSERT OR IGNORE INTO atom_tag (card_id, kind, tag) VALUES (?, 'supply', ?)", (card_id, tag)
        )
        written += 1
        if (card_id, tag) not in existing:
            entries.append(PromotedEntry(card_id=card_id, tag=tag, confirmed_at=now))
            existing.add((card_id, tag))
    conn.commit()
    save_promoted(entries)
    print(f"[確定] atom_tag に{written}件書込 / promoted_tags.json 総数{len(entries)}件")
    if missing:
        print(f"  未知card_idをスキップ: {', '.join(map(str, missing))}")


def reapply(conn: sqlite3.Connection) -> None:
    # AI_NOTE: 再抽出でatom_tagが作り直された後、正本JSONの全昇格を atom_tag へ戻す。
    # INSERT OR IGNORE + 正本がソースなので冪等(二重適用しても件数は増えない)。
    entries = load_promoted()
    for entry in entries:
        conn.execute(
            "INSERT OR IGNORE INTO atom_tag (card_id, kind, tag) VALUES (?, 'supply', ?)",
            (entry["card_id"], entry["tag"]),
        )
    conn.commit()
    print(f"[reapply] promoted_tags.json の{len(entries)}件を atom_tag へ再適用")


_USAGE = (
    "usage:\n"
    '  python -m svdeck.promote --tag "<tag>" --cards <id,id,...> [--confirm]\n'
    "  python -m svdeck.promote --reapply"
)


def _parse_cards(raw: str) -> list[int]:
    # AI_NOTE: 人手入力のカンマ区切りcard_id。空要素は無視し、非数値はusageで落とす(黙って解釈しない)。
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            print(_USAGE)
            sys.exit(1)
        ids.append(int(part))
    return ids


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口。--reapplyは単独・それ以外は--tag/--cards必須(explore.main流儀の引数検証)。
    args = sys.argv[1:]
    conn = connect()
    try:
        if "--reapply" in args:
            reapply(conn)
            return
        if "--tag" not in args or "--cards" not in args:
            print(_USAGE)
            sys.exit(1)
        tag = args[args.index("--tag") + 1] if args.index("--tag") + 1 < len(args) else ""
        cards_raw = args[args.index("--cards") + 1] if args.index("--cards") + 1 < len(args) else ""
        if not tag or not cards_raw:
            print(_USAGE)
            sys.exit(1)
        card_ids = _parse_cards(cards_raw)
        if not card_ids:
            print(_USAGE)
            sys.exit(1)
        if "--confirm" in args:
            confirm(conn, tag, card_ids)
        else:
            propose(conn, tag, card_ids)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
