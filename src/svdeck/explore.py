"""アンカー深掘りCLI(explore)。design.md §6検索はしごの1〜2段目を1コマンドにまとめる。

.claude/plans/anchor-require-and-explore.md のフェーズ2・Step7。anchor_requireから対象アンカーの
要求を読み、要求ごとに(1)タグ検索(bench.pyの_matches経由・同クラス+ニュートラル) (2)skill_text全文検索
の供給候補card_idを列挙し、人が読める調書テキストを出す。算術チェック・クロージャ組み・novelty照合・
LLM走査パックはStep8/9で追加する(このファイルでは対象外)。

実行: PYTHONPATH=src python -m svdeck.explore <card_id> [--format rotation|unlimited]
"""

import re
import sqlite3
import sys
from typing import NamedTuple

from svdeck.bench import CategoryLookup, FulfillmentMap, Tag, _matches, load_fulfillment_map, parse_tag
from svdeck.db import connect

DEFAULT_FORMAT = "rotation"


class RequireRow(NamedTuple):
    anchor_id: int
    req_type: str
    requirement: str
    req_tag: str | None
    deadline_turn: int | None
    status: str
    note: str | None


class Candidate(NamedTuple):
    card_id: int
    name: str
    cost: int | None
    reason: str  # ヒット根拠(タグ名 or マッチ語)


def is_anchor(conn: sqlite3.Connection, card_id: int) -> bool:
    # AI_NOTE: explore対象はcard_tag='anchor'のみ。それ以外は即終了させるための判定を切り出す。
    row = conn.execute("SELECT 1 FROM card_tag WHERE card_id = ? AND tag = 'anchor'", (card_id,)).fetchone()
    return row is not None


def load_requires(conn: sqlite3.Connection, card_id: int) -> list[RequireRow]:
    # AI_NOTE: require.pyのrecheckと同じ対象(status IN active/dead)を読む。dumpと違いid昇順のみで十分
    # (調書は1アンカー分なのでcard_id分岐は不要)。
    rows = conn.execute(
        """
        SELECT id, req_type, requirement, req_tag, deadline_turn, status, note
        FROM anchor_require
        WHERE card_id = ? AND status IN ('active', 'dead')
        ORDER BY id
        """,
        (card_id,),
    ).fetchall()
    return [RequireRow(*row) for row in rows]


def _requirement_tag(req_tag: str | None, requirement: str) -> Tag:
    # AI_NOTE: require.py._requirement_tagと同じ優先順位(req_tag優先・無ければrequirement自由文)。
    # require.pyの関数はモジュール内privateで再利用しづらいためここでも同じ規約を踏襲する。
    return parse_tag(req_tag if req_tag else requirement)


def _class_filtered_candidates(
    conn: sqlite3.Connection, class_name: str, format_name: str, exclude_card_id: int
) -> list[tuple[int, str, int | None, list[Tag]]]:
    # AI_NOTE: require.py._class_filtered_supply_tagsはタグの集合しか返さずcard_id対応が失われるため
    # ここではカード単位(card_id, name, cost, supply_tags)で持ち直す。design.md§6.1の
    # 「同クラス+ニュートラル」フィルタとStep7要件の「アンカー自身は除外」「rotation時is_include_rotation」を
    # 同時に満たす。
    format_filter = " AND c.is_include_rotation = 1" if format_name == "rotation" else ""
    rows = conn.execute(
        f"""
        SELECT DISTINCT c.card_id, c.name, c.cost
        FROM card c JOIN atom_tag at ON at.card_id = c.card_id
        WHERE at.kind = 'supply' AND c.class_name IN (?, 'ニュートラル')
          AND c.card_id != ?{format_filter}
        """,
        (class_name, exclude_card_id),
    ).fetchall()
    candidates = []
    for candidate_id, name, cost in rows:
        supply_tags = [
            parse_tag(row[0])
            for row in conn.execute(
                "SELECT tag FROM atom_tag WHERE card_id = ? AND kind = 'supply'", (candidate_id,)
            )
        ]
        candidates.append((candidate_id, name, cost, supply_tags))
    return candidates


def tag_search(
    conn: sqlite3.Connection,
    tag: Tag,
    fmap: FulfillmentMap,
    category_lookup: CategoryLookup,
    class_name: str,
    format_name: str,
    exclude_card_id: int,
) -> list[Candidate]:
    # AI_NOTE: はしご1段目。require.recheckと同じ分類経路(classify→natural/rules振り分け→_matches)を
    # 使うが、recheckは「見つかったか」のbool止まりなのに対しここではカード単位で当たった候補を返す。
    category = fmap.classify(tag)
    if category in ("unclassified", "auto", "auto_or_supply", "construction"):
        return []
    if category == "natural":
        rule = fmap.natural_rule_for(tag)
        allowed = rule.supplies if rule is not None else []
        use_category = False
    else:
        allowed = fmap.supplies_for(tag)
        use_category = fmap.category_resolution_for(tag)

    candidates = _class_filtered_candidates(conn, class_name, format_name, exclude_card_id)
    lookup = category_lookup if use_category else None
    hits = []
    for candidate_id, name, cost, supply_tags in candidates:
        if _matches(tag, supply_tags, allowed, lookup):
            hits.append(Candidate(candidate_id, name, cost, f"タグ:{tag.base}"))
    return hits


# AI_NOTE: パラメータからノイズ語(所有者prefix・比較演算子)を除いた名詞句だけを検索語にする。
# bench.pyの_normalize_paramと同じ正規化方針だが、全文検索語としては短すぎる語(1文字)は拾わない。
_SEARCH_NOISE = re.compile(r"[≥()（）]")


def _search_terms(tag: Tag, fmap: FulfillmentMap) -> list[str]:
    # AI_NOTE: 検索語の機械生成。(1)要求タグのベース名 (2)要求タグのパラメータ (3)fulfillment_mapで
    # 該当ベース名に紐づくsupplies語(自然/rulesどちらも)のベース名、の3系統を集めて重複除去する。
    terms = {tag.base}
    if tag.param:
        cleaned = _SEARCH_NOISE.sub("", tag.param)
        if len(cleaned) >= 2:
            terms.add(cleaned)
    for natural_rule in fmap.natural_rules:
        if natural_rule.require_base == tag.base:
            terms.update(pattern.base for pattern in natural_rule.supplies if len(pattern.base) >= 2)
    for scored_rule in fmap.rules:
        if scored_rule.require.base == tag.base:
            terms.update(pattern.base for pattern in scored_rule.supplies if len(pattern.base) >= 2)
    return [term for term in terms if len(term) >= 2]


def fulltext_search(
    conn: sqlite3.Connection,
    tag: Tag,
    fmap: FulfillmentMap,
    class_name: str,
    format_name: str,
    exclude_card_id: int,
    already_hit: set[int],
) -> list[Candidate]:
    # AI_NOTE: はしご2段目。タグ化されていない字面の概念をskill_text LIKE検索で拾う
    # (design.md§6.1検索手段のはしご・2段目)。1段目で既にヒットしたcard_idは「追加ヒット」から除外する。
    format_filter = " AND c.is_include_rotation = 1" if format_name == "rotation" else ""
    hits: dict[int, Candidate] = {}
    for term in _search_terms(tag, fmap):
        rows = conn.execute(
            f"""
            SELECT DISTINCT c.card_id, c.name, c.cost
            FROM card c
            WHERE c.class_name IN (?, 'ニュートラル') AND c.card_id != ?
              AND c.skill_text LIKE ?{format_filter}
            """,
            (class_name, exclude_card_id, f"%{term}%"),
        ).fetchall()
        for candidate_id, name, cost in rows:
            if candidate_id in already_hit or candidate_id in hits:
                continue
            hits[candidate_id] = Candidate(candidate_id, name, cost, f"全文:{term}")
    return list(hits.values())


class RequirementReport(NamedTuple):
    require: RequireRow
    tag_hits: list[Candidate]
    fulltext_hits: list[Candidate]
    manual: bool  # タグ文法非合致(unclassified等)で機械検索が成立しなかった要求


def build_requirement_report(
    conn: sqlite3.Connection,
    require: RequireRow,
    fmap: FulfillmentMap,
    category_lookup: CategoryLookup,
    class_name: str,
    format_name: str,
    anchor_card_id: int,
) -> RequirementReport:
    # AI_NOTE: 1要求分のはしご1〜2段をまとめて実行する。tag_searchが0件でもmanualとは限らない
    # (分類は通ったが該当カードが無いだけ)ため、manual判定はclassifyの結果だけで独立に見る。
    tag = _requirement_tag(require.req_tag, require.requirement)
    category = fmap.classify(tag)
    manual = category == "unclassified"
    tag_hits = tag_search(conn, tag, fmap, category_lookup, class_name, format_name, anchor_card_id)
    already_hit = {hit.card_id for hit in tag_hits}
    fulltext_hits = fulltext_search(conn, tag, fmap, class_name, format_name, anchor_card_id, already_hit)
    return RequirementReport(require, tag_hits, fulltext_hits, manual)


def format_candidate(candidate: Candidate) -> str:
    cost_text = str(candidate.cost) if candidate.cost is not None else "?"
    return f"    {candidate.card_id} {candidate.name} (コスト{cost_text}) [{candidate.reason}]"


def format_report(
    card_id: int, card_name: str, class_name: str, card_note: str | None, reports: list[RequirementReport]
) -> str:
    # AI_NOTE: 計画書「完成形の具体像」の調書フォーマットに合わせる。要求ごとに
    # [タグ検索]/[全文検索]の件数+候補一覧、0件は「機械検索0件」を明示する(Step9のLLM走査パック接続点)。
    lines = [f"=== アンカー調書: [{card_id}] {card_name} ({class_name}) ==="]
    lines.append(f"card_note: {card_note}" if card_note else "card_note: (なし)")
    lines.append("")

    for i, report in enumerate(reports, start=1):
        require = report.require
        deadline = f" deadline=T{require.deadline_turn}" if require.deadline_turn is not None else ""
        lines.append(f"--- 要求{i} ({require.req_type}/{require.status}): {require.requirement}{deadline}")
        if report.manual:
            lines.append("  [manual] requirementがタグ文法に合致せず機械検索対象外(要LLM走査)")
        total_hits = len(report.tag_hits) + len(report.fulltext_hits)
        if total_hits == 0:
            lines.append("  機械検索0件")
        else:
            lines.append(f"  [タグ検索] {len(report.tag_hits)}件")
            for hit in report.tag_hits:
                lines.append(format_candidate(hit))
            lines.append(f"  [全文検索] 追加{len(report.fulltext_hits)}件")
            for hit in report.fulltext_hits:
                lines.append(format_candidate(hit))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def explore(card_id: int, format_name: str = DEFAULT_FORMAT) -> str:
    # AI_NOTE: CLI本体。アンカー判定→要求読込→要求ごとのはしご1〜2段→調書整形、を1関数で通す
    # (Step7スコープはここまで。算術/クロージャ/novelty/LLM走査パックはStep8/9で追加)。
    conn = connect()
    try:
        if not is_anchor(conn, card_id):
            return f"[{card_id}] はアンカー(card_tag='anchor')ではありません。explore対象外です。\n"
        row = conn.execute("SELECT name, class_name FROM card WHERE card_id = ?", (card_id,)).fetchone()
        if row is None:
            return f"card_id {card_id} はcardテーブルに存在しません。\n"
        card_name, class_name = row
        note_row = conn.execute("SELECT note FROM card_note WHERE card_id = ?", (card_id,)).fetchone()
        card_note = note_row[0] if note_row else None

        fmap = load_fulfillment_map()
        category_lookup = CategoryLookup(conn)
        requires = load_requires(conn, card_id)
        reports = [
            build_requirement_report(conn, require, fmap, category_lookup, class_name, format_name, card_id)
            for require in requires
        ]
        return format_report(card_id, card_name, class_name, card_note, reports)
    finally:
        conn.close()


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口。引数不正はusage表示で終了する(require.py mainと同じ流儀)。
    args = sys.argv[1:]
    if not args:
        print("usage: python -m svdeck.explore <card_id> [--format rotation|unlimited]")
        sys.exit(1)
    card_id = int(args[0])
    format_name = DEFAULT_FORMAT
    if "--format" in args:
        format_name = args[args.index("--format") + 1]
    print(explore(card_id, format_name))


if __name__ == "__main__":
    main()
