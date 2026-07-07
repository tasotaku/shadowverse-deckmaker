"""逆方向マッチングCLI(供給起点)。design.md §6.4・計画書Step1。

通常のexplore.pyは「アンカー→供給」で引くが、これは逆に**供給起点**で引く: 対象card_idを1枚指定し、
その供給タグ(トークン伝播込み・explore.py.card_supply_tagsを共用)が全active anchor_requireの
どの行(希少要求)に型一致で噛むかを列挙する。同クラス+ニュートラル・同一フォーマット合法の要求だけを
対象にする(design.md§6.1「クラス固有キーワードはそのクラス内でのみ意味を持つ」＋§1.5フォーマット公理)。
判定は_matches(型一致)に委ねる想起のみ・ML/類似は使わない。accumulate要求は型一致のみ見て
量の算術(deck_rates)はforward exploreの仕事としてスキップする(計画書「詰まったときのルール」)。

実行: PYTHONPATH=src python -m svdeck.reverse <card_id> [--format rotation|unlimited]
"""

import sqlite3
import sys
from typing import NamedTuple

from svdeck.bench import CategoryLookup, FulfillmentMap, Tag, load_fulfillment_map
from svdeck.db import connect
from svdeck.explore import DEFAULT_FORMAT, _matched_supply_tag, _requirement_tag, card_supply_tags


class AnchorRequireRow(NamedTuple):
    anchor_id: int
    anchor_card_id: int
    anchor_name: str
    anchor_class_name: str
    anchor_is_include_rotation: int
    requirement: str
    req_tag: str | None


def load_active_anchor_requires(conn: sqlite3.Connection) -> list[AnchorRequireRow]:
    # AI_NOTE: 全status='active'のanchor_requireをanchor_require JOIN cardで読む(アンカー側の
    # name/class_name/is_include_rotationは対象カードとのクラス・フォーマット絞り込みに必須)。
    # dead行はrequire.py recheckの担当のためここでは対象外(計画書スコープ「require.pyには手を出さない」)。
    rows = conn.execute(
        """
        SELECT r.id, c.card_id, c.name, c.class_name, c.is_include_rotation, r.requirement, r.req_tag
        FROM anchor_require r
        JOIN card c ON c.card_id = r.card_id
        WHERE r.status = 'active'
        ORDER BY c.card_id, r.id
        """
    ).fetchall()
    return [AnchorRequireRow(*row) for row in rows]


class ReverseMatch(NamedTuple):
    anchor_name: str
    requirement: str
    matched_tag: str


def find_reverse_matches(
    conn: sqlite3.Connection,
    target_card_id: int,
    target_class_name: str,
    target_is_neutral: bool,
    format_name: str,
    fmap: FulfillmentMap,
    category_lookup: CategoryLookup,
    supply_tags: list[tuple[str, Tag]],
) -> list[ReverseMatch]:
    # AI_NOTE: design.md§6.4の実体。対象要求の絞り込みは(1)アンカーclassが対象カードのclassと一致、
    # または対象カードがニュートラル(ニュートラルは全クラスのアンカーを供給しうる)(2)format='rotation'なら
    # アンカーがis_include_rotation=1、の2条件(計画書(B)本文どおり)。判定はexplore.pyのtag_searchと同じ
    # classify→natural/rules振り分け→_matched_supply_tagの型一致経路を再利用し、独自ロジックは複製しない。
    matches: list[ReverseMatch] = []
    for row in load_active_anchor_requires(conn):
        if row.anchor_card_id == target_card_id:
            continue
        if not (target_is_neutral or row.anchor_class_name == target_class_name):
            continue
        if format_name == "rotation" and not row.anchor_is_include_rotation:
            continue

        tag = _requirement_tag(row.req_tag, row.requirement)
        category = fmap.classify(tag)
        if category in ("unclassified", "auto", "auto_or_supply", "construction"):
            continue
        if category == "natural":
            rule = fmap.natural_rule_for(tag)
            allowed = rule.supplies if rule is not None else []
            lookup = None
        else:
            allowed = fmap.supplies_for(tag)
            lookup = category_lookup if fmap.category_resolution_for(tag) else None

        matched = _matched_supply_tag(tag, supply_tags, allowed, lookup)
        if matched is not None:
            matches.append(ReverseMatch(row.anchor_name, row.requirement, matched))
    return matches


def format_reverse_report(
    card_id: int,
    card_name: str,
    class_name: str,
    format_name: str,
    supply_tags: list[tuple[str, Tag]],
    matches: list[ReverseMatch],
    format_warning: str | None = None,
) -> str:
    # AI_NOTE: 完成形の具体像(計画書)通りのフォーマット。供給タグ一覧は生文字列(注記込み)をそのまま出す。
    # format_warningは対象カード自身がフォーマット非合法な場合の注意(explore.pyと対称・調書は出す)。
    lines = [f"=== 逆方向マッチング: [{card_id}] {card_name} ({class_name}) ==="]
    if format_warning:
        lines.append(format_warning)
    tag_text = ", ".join(raw for raw, _ in supply_tags) if supply_tags else "(なし)"
    lines.append(f"供給タグ: {tag_text}")
    format_note = "rotation合法" if format_name == "rotation" else "unlimited"
    lines.append(f"--- 満たしうる active 要求({class_name}+ニュートラルのアンカー・{format_note})---")
    if not matches:
        lines.append("満たす active 要求なし")
    else:
        for match in matches:
            lines.append(f"- [{match.anchor_name}] 「{match.requirement}」 ← マッチ: {match.matched_tag}")
    return "\n".join(lines) + "\n"


def reverse(card_id: int, format_name: str = DEFAULT_FORMAT) -> str:
    # AI_NOTE: CLI本体。対象カードのclass/is_include_rotationを取得→card_supply_tagsで供給タグ
    # (トークン伝播込み)を取得→全active anchor_requireを同クラス+ニュートラル・同一フォーマット合法に
    # 絞って型一致判定、という流れ。explore.pyのDEFAULT_FORMATをそのままデフォルトに使う(計画書指定)。
    conn = connect()
    try:
        row = conn.execute(
            "SELECT name, class_name, is_include_rotation FROM card WHERE card_id = ?", (card_id,)
        ).fetchone()
        if row is None:
            return f"card_id {card_id} はcardテーブルに存在しません。\n"
        card_name, class_name, is_include_rotation = row
        # AI_NOTE: 対象カード自身がrotation非合法なら、満たすアンカーがあっても同一フォーマットで閉じない。
        # explore.pyと対称に警告する(調書自体は出し判断は人に残す・design.md§1.5フォーマット公理)。
        format_warning = None
        if format_name == "rotation" and not is_include_rotation:
            format_warning = (
                "⚠ このカード自身はローテーション非合法(is_include_rotation=0)。--format unlimited での探索を検討"
            )

        fmap = load_fulfillment_map()
        category_lookup = CategoryLookup(conn)
        supply_tags = card_supply_tags(conn, card_id)
        is_neutral = class_name == "ニュートラル"
        matches = find_reverse_matches(
            conn, card_id, class_name, is_neutral, format_name, fmap, category_lookup, supply_tags
        )
        return format_reverse_report(
            card_id, card_name, class_name, format_name, supply_tags, matches, format_warning
        )
    finally:
        conn.close()


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口。explore.py mainと同じ流儀(引数不正・--format値不正はusage表示で終了)。
    args = sys.argv[1:]
    if not args:
        print("usage: python -m svdeck.reverse <card_id> [--format rotation|unlimited]")
        sys.exit(1)
    card_id = int(args[0])
    format_name = DEFAULT_FORMAT
    if "--format" in args:
        format_index = args.index("--format") + 1
        if format_index >= len(args) or args[format_index] not in ("rotation", "unlimited"):
            print("usage: python -m svdeck.reverse <card_id> [--format rotation|unlimited]")
            sys.exit(1)
        format_name = args[format_index]
    print(reverse(card_id, format_name))


if __name__ == "__main__":
    main()
