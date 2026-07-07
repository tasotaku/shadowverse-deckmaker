"""アンカー深掘りCLI(explore)。design.md §6検索の2本(タグ検索+LLM走査)+算術チェック+クロージャ組み+
§7novelty照合+LLM走査パック出しを1コマンドにまとめる。

.claude/plans/anchor-require-and-explore.md のフェーズ2・Step7〜9。anchor_requireから対象アンカーの
要求を読み、要求ごとにタグ検索(bench.pyの_matches経由・同クラス+ニュートラル)で供給候補card_idを列挙し、
蓄積型(accumulate)要求には算術チェック(自然増レート+候補上乗せの貪欲スケジュール)を接続する。
さらに全active要求を同時に閉じる3枚以内のクロージャ候補を列挙し、クロージャ候補card_idについて
novelty照合(meta_deck/meta_deck_cardでアンカーとの同居デッキ検索・design.md§7「フィルタしない・
全部見せる」)、全active要求についてLLM走査パック(skill_text+card_noteコーパスdata/card_memo.txtを
読ませる走査指示文。2026-07-07改訂でLIKE全文検索(旧はしご2段目)を廃止し常設化)を調書末尾に添える。

実行: PYTHONPATH=src python -m svdeck.explore <card_id> [--format rotation|unlimited]
"""

import sqlite3
import sys
from itertools import combinations
from typing import NamedTuple

from svdeck.bench import (
    CategoryLookup,
    FulfillmentMap,
    MeasuredRates,
    SupplyPattern,
    Tag,
    _card_counter_contrib,
    _matches,
    _token_counts_from_atoms,
    _token_supply_tags,
    cumulative_pp_for_turn,
    derive_rates,
    extract_n,
    load_fulfillment_map,
    measure_deck_rates,
    parse_tag,
)
from svdeck.db import connect

DEFAULT_FORMAT = "rotation"
CLOSURE_CANDIDATE_TOP_N = 8  # AI_NOTE: 組合せ爆発対策(計画書「詰まったときのルール」)。8枚→遅ければ5枚に下げる想定
CLOSURE_MAX_SIZE = 3


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


def card_supply_tags(conn: sqlite3.Connection, card_id: int) -> list[tuple[str, Tag]]:
    # AI_NOTE: _class_filtered_candidates内にあった「1カード分の供給タグ取得+トークン伝播」を
    # 独立ヘルパーに抽出(計画書Step1(A)・挙動不変)。reverse.py(逆方向マッチング)からも同じ
    # 「カードの供給タグ(トークン伝播込み)」が要るため共用する。戻り値は(生タグ文字列, パース済みTag)の
    # ペアのリスト——調書のヒット根拠にマッチした供給側タグの生文字列を表示するため両方持つ。
    # AI_NOTE: トークン能力の伝播(design.md§6.1)。トークン召喚(X)/存在(X)を持つカードについて、
    # Xをis_token=1のカードとして解決しその供給タグを注記付きで追記する。単層のみ(伝播で得た
    # タグをさらに再伝播しない=supply_tagsの元のスナップショットだけを走査)。X=プレースホルダ
    # (◯◯)/自カード名(自己参照)はスキップ——呼び出し側で既にクラス/フォーマット絞り込み済みの
    # 候補が前提であり、TはAの効果が生む同文脈のカードなので追加のクラスチェックが不要なため。
    # トークン召喚(X)と存在(X)は同じXを指すことが多く伝播が重複しうるため(raw, Tag)で重複除去する。
    name_row = conn.execute("SELECT name FROM card WHERE card_id = ?", (card_id,)).fetchone()
    name = name_row[0] if name_row else None
    supply_tags = [
        (row[0], parse_tag(row[0]))
        for row in conn.execute("SELECT tag FROM atom_tag WHERE card_id = ? AND kind = 'supply'", (card_id,))
    ]
    propagated: dict[tuple[str, Tag], None] = {}
    for _, parsed in supply_tags:
        if parsed.base not in ("トークン召喚", "存在") or not parsed.param:
            continue
        token_name = parsed.param
        if token_name in ("◯◯", name):
            continue
        for entry in _token_supply_tags(conn, token_name):
            propagated.setdefault(entry, None)
    supply_tags.extend(propagated.keys())
    return supply_tags


def _class_filtered_candidates(
    conn: sqlite3.Connection, class_name: str, format_name: str, exclude_card_id: int
) -> list[tuple[int, str, int | None, list[tuple[str, Tag]]]]:
    # AI_NOTE: require.py._class_filtered_supply_tagsはタグの集合しか返さずcard_id対応が失われるため
    # ここではカード単位(card_id, name, cost, supply_tags)で持ち直す。design.md§6.1の
    # 「同クラス+ニュートラル」フィルタとStep7要件の「アンカー自身は除外」「rotation時is_include_rotation」を
    # 同時に満たす。
    # AI_NOTE: トークン(is_token=1)は非デッキ(単独でデッキに入らない)なので供給候補から除外する
    # (NULL安全な IS NOT 1=「トークンでない」で判定)。トークンの能力は card_supply_tags の伝播ロジックで
    # 生成カード側に載るため、直接候補に出すと非デッキ供給の偽候補になる。
    # AI_NOTE: 計画書Step1(A)でトークン伝播ロジックをcard_supply_tagsへ抽出し、ここはそれを呼ぶだけの
    # 薄い形にした(挙動不変)。
    format_filter = " AND c.is_include_rotation = 1" if format_name == "rotation" else ""
    rows = conn.execute(
        f"""
        SELECT DISTINCT c.card_id, c.name, c.cost
        FROM card c JOIN atom_tag at ON at.card_id = c.card_id
        WHERE at.kind = 'supply' AND c.class_name IN (?, 'ニュートラル')
          AND c.is_token IS NOT 1 AND c.card_id != ?{format_filter}
        """,
        (class_name, exclude_card_id),
    ).fetchall()
    return [(candidate_id, name, cost, card_supply_tags(conn, candidate_id)) for candidate_id, name, cost in rows]


def _matched_supply_tag(
    tag: Tag, supply_tags: list[tuple[str, Tag]], allowed: list[SupplyPattern], lookup: CategoryLookup | None
) -> str | None:
    # AI_NOTE: _matchesはboolしか返さないため、供給側タグを1つずつ_matchesに通して「どのタグで
    # 当たったか」を特定する(bench.pyのロジック複製はしない)。直接一致もカテゴリ階層解決も
    # タグ単位の呼び出しで元の全体判定と同値(どちらもタグごとの独立判定のOR)。
    for raw, parsed in supply_tags:
        if _matches(tag, [parsed], allowed, lookup):
            return raw
    return None


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
        # AI_NOTE: ヒット根拠にはマッチした供給側の生タグ(例:墓場+(1))を出す。要求側タグを出すと
        # 全候補が同じラベルになり調書の根拠として読めないため(司令塔レビュー指摘)。
        matched = _matched_supply_tag(tag, supply_tags, allowed, lookup)
        if matched is not None:
            hits.append(Candidate(candidate_id, name, cost, f"タグ:{matched}"))
    return hits


class CardContribInfo(NamedTuple):
    # AI_NOTE: クロージャのPP収支検査でも算術チェックでも同じ「1枚あたりの寄与」が要るため、
    # 候補card_idに対する寄与情報をここで1回だけ引いて使い回す形にする。
    card_id: int
    name: str
    cost: int | None
    renkei: float
    graveyard: float
    extra_pp: int


def _card_contrib_info(conn: sqlite3.Connection, card_id: int, category_lookup: CategoryLookup) -> CardContribInfo:
    # AI_NOTE: bench._card_counter_contribは(type_category, supply_tags, category_lookup, token_counts)を
    # 取るラッパ無し関数のため、explore側でcard1枚分の入力(type_category・supply_tags・atoms_json)を
    # DBから集めてから渡す。bench.pyのロジック自体は複製せずそのままimportして使う(計画書の決定事項)。
    row = conn.execute("SELECT name, cost, type_category FROM card WHERE card_id = ?", (card_id,)).fetchone()
    name, cost, type_category = row
    supply_tags = [
        parse_tag(r[0]) for r in conn.execute("SELECT tag FROM atom_tag WHERE card_id = ? AND kind = 'supply'", (card_id,))
    ]
    atom_row = conn.execute("SELECT atoms_json FROM card_atom WHERE card_id = ?", (card_id,)).fetchone()
    token_counts = _token_counts_from_atoms(atom_row[0] if atom_row else None)
    contrib = _card_counter_contrib(type_category, supply_tags, category_lookup, token_counts)
    return CardContribInfo(card_id, name, cost, contrib.renkei, contrib.graveyard, contrib.extra_pp)


_COUNTER_BY_TAG_BASE = {"墓場≥N": "graveyard", "ネクロマンス": "graveyard", "連携": "renkei"}


def _counter_for_tag(tag: Tag) -> str | None:
    # AI_NOTE: 蓄積型のカウンタ種別(graveyard/renkei)をタグベース名から引く。fulfillment_mapの
    # natural_rulesが持つcounter属性と同じ語彙(design.md§6.2)。未知のベース名はNone=算術スキップの合図。
    return _COUNTER_BY_TAG_BASE.get(tag.base)


class GreedyStep(NamedTuple):
    card_id: int
    name: str
    copies: int
    gained: float
    pp_spent: int


class ArithmeticResult(NamedTuple):
    counter: str
    threshold: int
    deadline_turn: int
    cum_pp: int
    dedicated_rate: float
    generic_rate: float
    natural_only_dedicated: float  # dedicatedレートのみでの到達見込み値
    generic_warning: bool  # 汎用レートでは自然増だけで届かない(表示のみの警告)
    topup_schedule: list[GreedyStep]
    topup_total: float
    passed: bool  # 専用構築レート+候補上乗せの楽観上界で届くか(これがFalseの時だけハードフィルタ相当)
    shortfall: float  # 不足量(0以上。passed時は0)


def compute_arithmetic(
    conn: sqlite3.Connection,
    tag: Tag,
    threshold: int,
    deadline_turn: int,
    candidates: list[Candidate],
    measured: MeasuredRates | None,
    fmap: FulfillmentMap,
    category_lookup: CategoryLookup,
) -> ArithmeticResult | None:
    # AI_NOTE: design.md§6.2「蓄積型の算術チェック」+「実測レートの限界と却下の運用」の実装。
    # (a)専用構築レート(dedicated)のみで届くか (b)候補供給の上乗せ(Δ/PP効率順の貪欲・各3積み)込みで
    # 届くかを計算する。passed=Falseは「専用構築+上乗せの楽観上界でも届かない」場合のみ=計画書が
    # ハードフィルタを許す唯一のケース。汎用レート(generic_warning)は表示専用の警告に留める
    # (計画書「算術FAILはハードフィルタにしない」)。
    counter = _counter_for_tag(tag)
    if counter is None:
        return None
    rule = fmap.natural_rule_for(tag)
    fallback_rate = rule.natural_rate if rule is not None else 0.0
    dedicated_rate = measured.dedicated.get(counter, fallback_rate) if measured is not None else fallback_rate
    generic_rate = measured.generic.get(counter, fallback_rate) if measured is not None else fallback_rate

    cum_pp = cumulative_pp_for_turn(deadline_turn)
    natural_only_dedicated = dedicated_rate * cum_pp
    generic_warning = generic_rate * cum_pp < threshold

    gap = threshold - natural_only_dedicated
    schedule: list[GreedyStep] = []
    topped_up = natural_only_dedicated
    if gap > 0:
        efficiency: list[tuple[float, CardContribInfo]] = []
        for candidate in candidates:
            info = _card_contrib_info(conn, candidate.card_id, category_lookup)
            per_copy_gain = info.graveyard if counter == "graveyard" else info.renkei
            if per_copy_gain <= 0:
                continue
            pp_per_copy = max(info.cost or 1, 1) + info.extra_pp
            efficiency.append((per_copy_gain / pp_per_copy, info))
        efficiency.sort(key=lambda item: item[0], reverse=True)
        for _, info in efficiency:
            if topped_up >= threshold:
                break
            pp_per_copy = max(info.cost or 1, 1) + info.extra_pp
            per_copy_gain = info.graveyard if counter == "graveyard" else info.renkei
            copies = 0
            gained = 0.0
            pp_spent = 0
            for _ in range(3):  # AI_NOTE: 各3積み上限(計画書の絞り込みルール)
                if topped_up >= threshold:
                    break
                topped_up += per_copy_gain
                copies += 1
                gained += per_copy_gain
                pp_spent += pp_per_copy
            if copies > 0:
                schedule.append(GreedyStep(info.card_id, info.name, copies, gained, pp_spent))

    passed = topped_up >= threshold
    shortfall = max(threshold - topped_up, 0.0)
    return ArithmeticResult(
        counter=counter,
        threshold=threshold,
        deadline_turn=deadline_turn,
        cum_pp=cum_pp,
        dedicated_rate=dedicated_rate,
        generic_rate=generic_rate,
        natural_only_dedicated=natural_only_dedicated,
        generic_warning=generic_warning,
        topup_schedule=schedule,
        topup_total=topped_up,
        passed=passed,
        shortfall=shortfall,
    )


class RequirementReport(NamedTuple):
    require: RequireRow
    tag_hits: list[Candidate]
    manual: bool  # タグ文法非合致(unclassified等)で機械検索が成立しなかった要求
    arithmetic: ArithmeticResult | None  # accumulate要求のみ設定。閾値抽出不能ならNone(算術スキップ)


def build_requirement_report(
    conn: sqlite3.Connection,
    require: RequireRow,
    fmap: FulfillmentMap,
    category_lookup: CategoryLookup,
    class_name: str,
    format_name: str,
    anchor_card_id: int,
    measured: MeasuredRates | None,
) -> RequirementReport:
    # AI_NOTE: 1要求分のタグ検索+算術チェックをまとめて実行する(2026-07-07・全文検索(旧はしご2段目)は
    # 廃止・LLM走査パックの常設化で代替)。tag_searchが0件でもmanualとは限らない(分類は通ったが
    # 該当カードが無いだけ)ため、manual判定はclassifyの結果だけで独立に見る。
    tag = _requirement_tag(require.req_tag, require.requirement)
    category = fmap.classify(tag)
    manual = category == "unclassified"
    tag_hits = tag_search(conn, tag, fmap, category_lookup, class_name, format_name, anchor_card_id)

    arithmetic = None
    if require.req_type == "accumulate" and require.deadline_turn is not None:
        threshold = extract_n(require.req_tag if require.req_tag else require.requirement)
        if threshold is not None:
            arithmetic = compute_arithmetic(
                conn, tag, threshold, require.deadline_turn, tag_hits, measured, fmap, category_lookup
            )
    return RequirementReport(require, tag_hits, manual, arithmetic)


def format_candidate(candidate: Candidate) -> str:
    cost_text = str(candidate.cost) if candidate.cost is not None else "?"
    return f"    {candidate.card_id} {candidate.name} (コスト{cost_text}) [{candidate.reason}]"


def format_arithmetic(arithmetic: ArithmeticResult) -> list[str]:
    # AI_NOTE: design.md§6.2の表示規約通り「専用構築レート+上乗せの楽観上界でも届かない」場合のみ
    # FAILとして不足量を添えて出す。汎用レートの不足は警告(⚠)止まりで非表示フィルタにしない
    # (計画書「算術FAILはハードフィルタにしない」)。
    lines = [
        f"  [算術] 自然増: 専用構築レート{arithmetic.dedicated_rate:.3f}/PP × 累積PP{arithmetic.cum_pp}"
        f"(T{arithmetic.deadline_turn}) ≈ {arithmetic.natural_only_dedicated:.1f} / 要求{arithmetic.threshold}"
    ]
    if arithmetic.generic_warning:
        lines.append(
            f"  ⚠ 汎用レート{arithmetic.generic_rate:.3f}/PPでは自然増のみで不足(専用構築寄りの前提が必要)"
        )
    if arithmetic.topup_schedule:
        schedule_text = ", ".join(
            f"{step.name}×{step.copies}(+{step.gained:.1f}/{step.pp_spent}PP)" for step in arithmetic.topup_schedule
        )
        lines.append(f"  上乗せ貪欲スケジュール: {schedule_text} → 合計{arithmetic.topup_total:.1f}")
    if arithmetic.passed:
        lines.append(f"  → PASS(専用構築レート+上乗せの楽観上界で到達: {arithmetic.topup_total:.1f} ≥ {arithmetic.threshold})")
    else:
        lines.append(f"  → FAIL(楽観上界でも不足量{arithmetic.shortfall:.1f}。候補は非表示にせず上に列挙済み)")
    return lines


def format_report(
    card_id: int,
    card_name: str,
    class_name: str,
    card_note: str | None,
    reports: list[RequirementReport],
    format_warning: str | None = None,
) -> str:
    # AI_NOTE: 計画書「完成形の具体像」の調書フォーマットに合わせる。要求ごとに[タグ検索]の件数+
    # 候補一覧、0件は「機械検索0件」を明示する(2026-07-07・全文検索セクションは廃止、代わりにLLM走査
    # パックが全active要求に付く=format_scan_pack側)。
    lines = [f"=== アンカー調書: [{card_id}] {card_name} ({class_name}) ==="]
    if format_warning:
        lines.append(format_warning)
    lines.append(f"card_note: {card_note}" if card_note else "card_note: (なし)")
    lines.append("")

    for i, report in enumerate(reports, start=1):
        require = report.require
        deadline = f" deadline=T{require.deadline_turn}" if require.deadline_turn is not None else ""
        lines.append(f"--- 要求{i} ({require.req_type}/{require.status}): {require.requirement}{deadline}")
        if report.manual:
            lines.append("  [manual] requirementがタグ文法に合致せず機械検索対象外(要LLM走査)")
        total_hits = len(report.tag_hits)
        if total_hits == 0:
            lines.append("  機械検索0件")
        else:
            lines.append(f"  [タグ検索] {len(report.tag_hits)}件")
            for hit in report.tag_hits:
                lines.append(format_candidate(hit))
        if report.require.req_type == "accumulate":
            if report.arithmetic is not None:
                lines.extend(format_arithmetic(report.arithmetic))
            else:
                lines.append("  [算術] 閾値/deadlineが機械抽出できないため算術スキップ")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _closure_candidate_pool(
    conn: sqlite3.Connection, reports: list[RequirementReport], category_lookup: CategoryLookup
) -> dict[int, list[Candidate]]:
    # AI_NOTE: 要求ごとの候補プールを効率順(Δ/PP)上位CLOSURE_CANDIDATE_TOP_N枚に絞る
    # (計画書「組合せ爆発対策」)。accumulate要求は算術のΔ/PPで並べ、それ以外(event/presence/construction)は
    # ヒット順のまま(優劣を機械判定する材料が無いため)先頭から取る。activeのみ対象(dead要求は閉じない)。
    # 2026-07-07: 全文検索(fulltext_hits)廃止によりtag_hitsのみで組む(LLM走査ヒットは人が手で足す
    # 現状の人間協働モデルを踏襲・計画書「技術的決定事項」)。
    pool: dict[int, list[Candidate]] = {}
    for idx, report in enumerate(reports):
        if report.require.status != "active":
            continue
        all_hits = report.tag_hits
        if not all_hits:
            continue
        if report.arithmetic is not None:
            tag = _requirement_tag(report.require.req_tag, report.require.requirement)
            counter = _counter_for_tag(tag)
            scored = []
            for candidate in all_hits:
                info = _card_contrib_info(conn, candidate.card_id, category_lookup)
                gain = info.graveyard if counter == "graveyard" else info.renkei
                pp = max(info.cost or 1, 1) + info.extra_pp
                scored.append((gain / pp if pp else 0.0, candidate))
            scored.sort(key=lambda item: item[0], reverse=True)
            pool[idx] = [candidate for _, candidate in scored[:CLOSURE_CANDIDATE_TOP_N]]
        else:
            pool[idx] = all_hits[:CLOSURE_CANDIDATE_TOP_N]
    return pool


class ClosureCandidateSet(NamedTuple):
    card_ids: tuple[int, ...]
    names: tuple[str, ...]
    covered_require_indices: frozenset[int]
    pp_notes: list[str]  # accumulate要求を含む場合のPP収支検査結果(PASS/不足量)


def find_closures(
    conn: sqlite3.Connection,
    reports: list[RequirementReport],
    category_lookup: CategoryLookup,
) -> list[ClosureCandidateSet]:
    # AI_NOTE: design.md§6.3「提案単位=要求クロージャ」の実装。全active要求を同時に閉じる3枚以内の
    # 「最小」カードセットを列挙する。サイズ昇順で列挙するため1枚で複数要求を満たすカードのセットが
    # 先に出る。既に全要求を閉じたセットの上位集合(スーパーセット)は最小でないため列挙しない
    # (§6.3「最小カード集合」・司令塔レビュー指摘)。要求が無ければ空リスト(「不成立」表示はexplore側)。
    active_indices = [idx for idx, r in enumerate(reports) if r.require.status == "active"]
    if not active_indices:
        return []
    pool = _closure_candidate_pool(conn, reports, category_lookup)
    if not pool:
        return []

    # AI_NOTE: card_id -> それが満たす要求indexの集合(候補プールに出現した全要求から逆引き)。
    coverage: dict[int, set[int]] = {}
    card_names: dict[int, str] = {}
    for idx, candidates in pool.items():
        for candidate in candidates:
            coverage.setdefault(candidate.card_id, set()).add(idx)
            card_names[candidate.card_id] = candidate.name

    all_card_ids = sorted(coverage.keys())
    results: list[ClosureCandidateSet] = []
    found_sets: list[set[int]] = []  # 既に成立したセット(card_id集合)。スーパーセット除外に使う
    target = set(pool.keys())  # 候補が1件もない要求は「閉じられない」ので対象外にする(候補ゼロは明示済み)
    for size in range(1, CLOSURE_MAX_SIZE + 1):
        for combo in combinations(all_card_ids, size):
            combo_set = set(combo)
            if any(prev <= combo_set for prev in found_sets):
                continue  # 既成立セットを含む冗長な組(サイズ昇順列挙なのでprevは常により小さい成立セット)
            covered: set[int] = set()
            for card_id in combo:
                covered |= coverage[card_id]
            if covered != target:
                continue
            found_sets.append(combo_set)
            results.append(
                ClosureCandidateSet(
                    card_ids=combo,
                    names=tuple(card_names[c] for c in combo),
                    covered_require_indices=frozenset(covered),
                    pp_notes=_closure_pp_notes(conn, combo, reports, target, category_lookup),
                )
            )
    return results


def _closure_pp_notes(
    conn: sqlite3.Connection,
    combo: tuple[int, ...],
    reports: list[RequirementReport],
    target: set[int],
    category_lookup: CategoryLookup,
) -> list[str]:
    # AI_NOTE: comboにaccumulate要求が含まれる場合のみPP収支検査を添える(design.md§6.2「消費の会計」は
    # 消費側複数の合算だが、explore Step8スコープでは供給合計と閾値の比較のみを対象にする)。
    notes: list[str] = []
    for idx in sorted(target):
        report = reports[idx]
        if report.arithmetic is None:
            continue
        tag = _requirement_tag(report.require.req_tag, report.require.requirement)
        counter = _counter_for_tag(tag)
        combo_gain = report.arithmetic.natural_only_dedicated
        for card_id in combo:
            info = _card_contrib_info(conn, card_id, category_lookup)
            combo_gain += (info.graveyard if counter == "graveyard" else info.renkei) * 3  # 各3積み前提
        threshold = report.arithmetic.threshold
        if combo_gain >= threshold:
            notes.append(f"要求{idx + 1}のPP収支: PASS({combo_gain:.1f} ≥ {threshold})")
        else:
            notes.append(f"要求{idx + 1}のPP収支: 不足{threshold - combo_gain:.1f}")
    return notes


def format_closures(reports: list[RequirementReport], closures: list[ClosureCandidateSet]) -> str:
    active_count = sum(1 for r in reports if r.require.status == "active")
    lines = ["=== クロージャ候補(全active要求を閉じる最小セット) ==="]
    if active_count == 0:
        lines.append("(active要求なし)")
        return "\n".join(lines) + "\n"
    # AI_NOTE: 候補0件のactive要求はfind_closuresが対象から外すため、「全active要求を閉じた」と
    # 誤読されないよう対象外の要求を明示する(self-review指摘)。2026-07-07: 全文検索廃止によりtag_hits
    # のみで判定(fulltext_hits参照を削除)。
    no_candidate = [
        i for i, r in enumerate(reports, start=1)
        if r.require.status == "active" and not r.tag_hits
    ]
    if no_candidate:
        nums = ", ".join(f"要求{i}" for i in no_candidate)
        lines.append(f"注: {nums} は候補0件のためクロージャ対象外(LLM走査パック参照)")
    if not closures:
        lines.append(f"クロージャ不成立(active要求{active_count}件を同時に閉じる3枚以内のセットが候補プール内に無い)")
        return "\n".join(lines) + "\n"
    for i, closure in enumerate(closures, start=1):
        names = ", ".join(f"{cid} {name}" for cid, name in zip(closure.card_ids, closure.names))
        lines.append(f"{i}. {{{names}}} {len(closure.card_ids)}枚 / 充足要求: {sorted(i + 1 for i in closure.covered_require_indices)}")
        for note in closure.pp_notes:
            lines.append(f"    {note}")
    return "\n".join(lines) + "\n"


class NoveltyHit(NamedTuple):
    deck_name: str
    tier: str | None


def check_novelty(conn: sqlite3.Connection, anchor_card_id: int, candidate_card_id: int) -> list[NoveltyHit]:
    # AI_NOTE: design.md§7「主判定=ローカルの環境デッキDB」の実装。アンカーと候補が同居する
    # meta_deck行をmeta_deck_card二回JOINで検索する(即答・全ペアコストゼロ)。ヒットなし=「未踏」
    # ではなくTier表DBの限界(§7)であり、この関数の戻り値だけでは判断しない
    # (format_noveltyが注記を必ず添える)。
    rows = conn.execute(
        """
        SELECT DISTINCT d.name, d.tier
        FROM meta_deck_card mc1
        JOIN meta_deck_card mc2 ON mc1.deck_id = mc2.deck_id
        JOIN meta_deck d ON d.id = mc1.deck_id
        WHERE mc1.card_id = ? AND mc2.card_id = ?
        """,
        (anchor_card_id, candidate_card_id),
    ).fetchall()
    return [NoveltyHit(name, tier) for name, tier in rows]


def format_novelty(
    conn: sqlite3.Connection, anchor_card_id: int, anchor_name: str, closures: list[ClosureCandidateSet]
) -> str:
    # AI_NOTE: クロージャ候補に登場した各card_idについてアンカーとの同居デッキを照合する
    # (計画書Step9「候補は落とさない」)。1枚が複数クロージャに出ても照合は1回で済むようcard_id単位で
    # 重複除去してから調書行を作る。
    lines = ["=== novelty照合 ==="]
    seen: dict[int, str] = {}
    for closure in closures:
        for card_id, name in zip(closure.card_ids, closure.names):
            seen[card_id] = name
    if not seen:
        lines.append("(クロージャ候補なし・照合対象なし)")
        return "\n".join(lines) + "\n"
    for card_id in sorted(seen):
        name = seen[card_id]
        hits = check_novelty(conn, anchor_card_id, card_id)
        if hits:
            deck_text = ", ".join(f"「{h.deck_name}」({h.tier})" if h.tier else f"「{h.deck_name}」" for h in hits)
            lines.append(
                f"- ペア({anchor_name}×{name}): {deck_text}に同居→既出壁"
                "(再浮上条件はcard_note/要求noteの別達成手段・底上げ新カードを参照)"
            )
        else:
            lines.append(
                f"- ペア({anchor_name}×{name}): meta_deck共起なし"
                "(注: Tier表DBの限界により未踏の証拠ではない・提示前にWeb確認必須)"
            )
    return "\n".join(lines) + "\n"


def format_scan_pack(card_id: int, class_name: str, reports: list[RequirementReport]) -> str:
    # AI_NOTE: 2026-07-07・design.md§6.1改訂によりLLM走査を全active要求で常設化する(旧: 機械検索0件or
    # manualのみが対象だったが、全文検索(はしご2段目)廃止に伴いタグで拾えない要求を毎回LLMに回す構え
    # に変更・計画書Step2)。dead要求は対象外(既に不要と判定済み)。対象が無ければ節自体を出さない。
    targets = [(i, report.require) for i, report in enumerate(reports, start=1) if report.require.status == "active"]
    if not targets:
        return ""
    lines = ["=== LLM走査パック(全active要求・タグ検索と併用) ==="]
    for i, require in targets:
        lines.append(f"要求{i}「{require.requirement}」")
    lines.append("")
    requirement_list = "\n".join(f"- 要求{i}「{require.requirement}」" for i, require in targets)
    lines.append(
        "data/card_memo.txt(skill_text+card_noteのコーパス)を読み、以下の各要求について該当する card_id "
        f"を列挙せよ。クラスは{class_name}+ニュートラルに限定。判定は型の一致で行い、意味の近さだけで"
        f"拾わないこと。\n{requirement_list}"
    )
    return "\n".join(lines) + "\n"


def explore(card_id: int, format_name: str = DEFAULT_FORMAT) -> str:
    # AI_NOTE: CLI本体。アンカー判定→要求読込→要求ごとのタグ検索+算術→クロージャ組み→
    # novelty照合→LLM走査パック(全active要求に常設)→調書整形、を1関数で通す。measure_deck_rates/
    # derive_ratesはexplore全体で1回だけ実行し、全要求の算術チェック+クロージャのPP収支検査で使い回す。
    # scan_pack_textが空になるのはactive要求が1つも無い時のみ(format_scan_pack参照)。
    conn = connect()
    try:
        if not is_anchor(conn, card_id):
            return f"[{card_id}] はアンカー(card_tag='anchor')ではありません。explore対象外です。\n"
        row = conn.execute(
            "SELECT name, class_name, is_include_rotation FROM card WHERE card_id = ?", (card_id,)
        ).fetchone()
        if row is None:
            return f"card_id {card_id} はcardテーブルに存在しません。\n"
        card_name, class_name, is_include_rotation = row
        # AI_NOTE: アンカー自身が指定フォーマットで非合法なら調書冒頭に警告する(design.md§1.5
        # 「種・クロージャは必ずフォーマットを明示し全カードが同一フォーマットで合法」の入口チェック。
        # 調書自体は出す——候補検索はフォーマットで絞れており、判断は人に残す)。
        format_warning = None
        if format_name == "rotation" and not is_include_rotation:
            format_warning = (
                "⚠ このアンカー自身はローテーション非合法(is_include_rotation=0)。"
                "--format unlimited での探索を検討"
            )
        note_row = conn.execute("SELECT note FROM card_note WHERE card_id = ?", (card_id,)).fetchone()
        card_note = note_row[0] if note_row else None

        fmap = load_fulfillment_map()
        category_lookup = CategoryLookup(conn)
        deck_rates = measure_deck_rates(conn, category_lookup)
        measured = derive_rates(deck_rates)

        requires = load_requires(conn, card_id)
        reports = [
            build_requirement_report(conn, require, fmap, category_lookup, class_name, format_name, card_id, measured)
            for require in requires
        ]
        closures = find_closures(conn, reports, category_lookup)
        report_text = format_report(card_id, card_name, class_name, card_note, reports, format_warning)
        novelty_text = format_novelty(conn, card_id, card_name, closures)
        scan_pack_text = format_scan_pack(card_id, class_name, reports)
        sections = [report_text, format_closures(reports, closures), novelty_text]
        if scan_pack_text:
            sections.append(scan_pack_text)
        return "\n".join(sections)
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
        # AI_NOTE: 人手入力のCLIのためtypo(例: unlimted)を黙ってunlimited扱いにせずusageで落とす。
        format_index = args.index("--format") + 1
        if format_index >= len(args) or args[format_index] not in ("rotation", "unlimited"):
            print("usage: python -m svdeck.explore <card_id> [--format rotation|unlimited]")
            sys.exit(1)
        format_name = args[format_index]
    print(explore(card_id, format_name))


if __name__ == "__main__":
    main()
