"""言い換え・下位概念変換表のローダ・照会CLI。design.md §6.1・計画書Step2。

口語/抽象語(例:「除去」「顔詰め」)からシステム語(タグ・公式キーワード)への対応を引く。
fulfillment_map.json(ルール上の充足関係)とは別物で、こちらは語の同義(synonym)/包含(hyponym)関係を
扱う。判定(型一致)には使わず、人がクエリを書くときの語彙補助・想起支援に限定する
(design.md §3.1「LLMを使うのは想起補助のみ」の対話クエリモードを支える)。

実行: PYTHONPATH=src python -m svdeck.paraphrase <語>
"""

import json
import sys
from pathlib import Path
from typing import TypedDict

PARAPHRASE_MAP_PATH = Path(__file__).resolve().parent / "data" / "paraphrase_map.json"


class ParaphraseEntry(TypedDict):
    term: str
    relation: str  # synonym(同義) または hyponym(下位概念を列挙)
    maps_to: list[str]
    confidence: str  # confirmed または draft
    note: str


class ParaphraseMapRaw(TypedDict):
    entries: list[ParaphraseEntry]


def load_paraphrase_map(path: Path = PARAPHRASE_MAP_PATH) -> dict[str, ParaphraseEntry]:
    # AI_NOTE: bench.load_fulfillment_mapと同じ流儀(JSON読込→型付きdictへ変換)。
    # キーはterm自体(照会はterm完全一致のみ・部分一致やゆらぎ吸収は非対象・司令塔の目利き拡張時に検討)。
    raw: ParaphraseMapRaw = json.loads(path.read_text(encoding="utf-8"))
    return {entry["term"]: entry for entry in raw["entries"]}


def lookup(term: str, entries: dict[str, ParaphraseEntry] | None = None) -> ParaphraseEntry | None:
    # AI_NOTE: エントリ全体(relation/confidence/note込み)が欲しい呼び出し元向け。未知語はNoneを返し
    # 例外は出さない(照会は人の想起補助でしかなく、未登録が異常系ではないため)。
    table = entries if entries is not None else load_paraphrase_map()
    return table.get(term)


def expand(term: str, entries: dict[str, ParaphraseEntry] | None = None) -> list[str]:
    # AI_NOTE: maps_to側(システム語)だけが欲しい呼び出し元向けの薄いラッパ。未知語は空リスト。
    entry = lookup(term, entries)
    return entry["maps_to"] if entry is not None else []


def main() -> None:
    # AI_NOTE: 人手が触る照会CLI。reverse.py/keywords.pyと同じくusage表示で終了する作法。
    args = sys.argv[1:]
    if not args:
        print("usage: python -m svdeck.paraphrase <語>")
        sys.exit(1)
    term = args[0]
    entry = lookup(term)
    if entry is None:
        print(f"{term}: 該当なし")
        return
    print(f"{term} ({entry['relation']}) → {', '.join(entry['maps_to'])}")


if __name__ == "__main__":
    main()
