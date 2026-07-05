"""回帰ベンチv3: 環境デッキを教師データに要求タグ充足の見逃しを機械採点する。

design.md §8-7の自己改善ループ①。meta_deck/meta_deck_card(環境デッキ81件)を教師データとし、
「要求タグ持ちカードの各要求が、同じデッキの他のカードの供給タグで充足できるか」を採点する。
充足できない組は人類が正解を知っているのにタグ語彙・充足マップでは繋がらない語彙の穴の候補で、
充足率がリコール指標になる。

v2(72.7%)からの追加(親レビュー: 残り未充足7件はv2の自然増モデル誤りとカテゴリ階層欠如):
  - natural: 自然増を「ターン単位固定レート」から「PP単位×デッキ形状」へ置き換え(rules.md#墓場の自然増)。
    累積PP(T)=T(T+1)/2に後攻エクストラPP楽観+2を足した値を期限とし、per_pp レートで判定する
  - category_resolution: 要求パラメータがカテゴリ(tribe名+フォロワー、コスト修飾可)で供給パラメータが
    個体名の場合、DBのcard_tribe/tribeとcard.type_categoryから個体名→種族集合を引いて階層解決する
  - トークン召喚(*)を連携・ネクロマンス・墓場≥Nの間接供給として追加(死亡→墓場+1、召喚→連携+1)

実行: python -m svdeck.bench
"""

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import NamedTuple, TypedDict

from svdeck.db import connect
from svdeck.meta import _normalize_name

FULFILLMENT_MAP_PATH = Path(__file__).resolve().parent / "data" / "fulfillment_map.json"
REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "bench_report.txt"
RANKING_TOP_N = 15

# AI_NOTE: PP単位自然増モデル(rules.md#墓場の自然増・design.md§6.2)。累積PP(T)=T(T+1)/2に
# 後攻エクストラPP(T1-5で+1・T6以降で+1)を楽観的に加算した値をT8の期限として固定する。
# +2込みにする判断根拠: ユーザー確定「連携20はT8前後で達成しうる」から逆算したdedicatedレート0.55/PPだと
# 素の累積36PPでは19.8となり閾値未達になってしまうため、エクストラ込みの38PPで19.8→20.9とし整合させた。
DEADLINE_TURN = 8
_CUM_PP_BASE = DEADLINE_TURN * (DEADLINE_TURN + 1) // 2
DEADLINE_CUM_PP = _CUM_PP_BASE + 2  # 後攻エクストラPP楽観込み(36+2=38)

# AI_NOTE: 「ベース名(パラメータ)」形式のタグを分解する正規表現。パラメータの丸括弧は
# 「墓場≥6」のように付かないタグもあるため、マッチしない場合はベース名=タグ全体・パラメータ無しとして扱う。
_TAG_PATTERN = re.compile(r"^(.+?)\((.+)\)$")

# AI_NOTE: パラメータ先頭の所有者・ゾーンprefixの揺れを吸収する(自場:アミュレット→アミュレット等)。
# 複数マッチしうる順(長い方を先)で並べる。
_PARAM_PREFIXES = ["自場:", "自手札:", "相手場:", "相手手札:", "味方", "相手"]


class Tag(NamedTuple):
    base: str
    param: str | None  # 括弧内パラメータの正規化後の文字列。パラメータ無しタグはNone


class SupplyPattern(NamedTuple):
    # AI_NOTE: fulfillment_map.jsonのsupplies配列専用の型。実タグのTagとは別に持つ理由は、
    # 「(*)=パラメータ不問」と「((X))=パラメータ捕捉」を区別するフラグ(capture)が実タグには無い概念のため。
    base: str
    capture: bool  # True: ((X))= 要求側paramと供給側paramの一致を要求。False: (*)または無パラメータ=不問


def _normalize_param(param: str) -> str:
    # AI_NOTE: meta.py._normalize_nameの作法(中黒・全角/半角記号の揺れ吸収)に準じつつ、
    # 要求タグ特有の所有者・ゾーンprefix(自場:等)と比較演算子付き数値(≥3等)を取り除いて
    # 「対象の名詞句」だけを残す。これにより要求側「自場:アミュレット」と供給側「アミュレット」が一致する。
    text = param
    for prefix in _PARAM_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = re.sub(r"[≥]\s*\d+", "", text)
    text = re.sub(r"[≥]\s*N", "", text)
    text = text.replace("・", "").replace("&", "＆").replace("=", "＝").strip()
    return text


def parse_tag(raw_tag: str) -> Tag:
    # AI_NOTE: 「超進化イベント条件:存在(自場:超進化後のフォロワー)」のような複合prefix付きタグは
    # ":"以降だけを実質タグとして扱う(ラベルを剥がして中身のパターンマッチに載せる)。
    text = raw_tag.split(":", 1)[1] if ":" in raw_tag and "(" in raw_tag.split(":", 1)[1] else raw_tag
    match = _TAG_PATTERN.match(text)
    if match:
        return Tag(base=match.group(1), param=_normalize_param(match.group(2)))
    # AI_NOTE: 「墓場≥6」「墓場≥N」のように丸括弧を使わず末尾に≥数値/≥Nが直結するタグ形式がある。
    # このケースは括弧形式の(*)相当として扱うため、ベース名を「墓場≥N」の形に正規化して閾値の違いを畳む。
    threshold_match = re.match(r"^(.+?)[≥](?:\d+|N)$", text)
    if threshold_match:
        return Tag(base=f"{threshold_match.group(1)}≥N", param=None)
    return Tag(base=text, param=None)


def parse_pattern(raw_pattern: str) -> SupplyPattern:
    # AI_NOTE: fulfillment_map.jsonのパターン記法(*)=パラメータ不問と((X))=パラメータ捕捉を解釈する。
    # 「墓場+(*)」→ベース名"墓場+"・パラメータ不問。「存在((X))」→ベース名"存在"・パラメータ捕捉あり。
    # 「進化権」のようにパラメータ自体が無いタグはパラメータ不問(capture=False)として扱う。
    if raw_pattern.endswith("((X))"):
        return SupplyPattern(base=raw_pattern[: -len("((X))")], capture=True)
    if raw_pattern.endswith("(*)"):
        return SupplyPattern(base=raw_pattern[: -len("(*)")], capture=False)
    # AI_NOTE: 「墓場≥N」のように括弧を使わないベース名パターンはparse_tagのベース名正規化と合わせる。
    return SupplyPattern(base=parse_tag(raw_pattern).base, capture=False)


# AI_NOTE: natural判定用にタグ生文字列から閾値Nを数値抽出する。「ネクロマンス(6)」→6、
# 「墓場≥6」→6、「墓場≥N」「連携(N)」のようにNがプレースホルダで数値化できないものはNoneを返す
# (bench.py側でN不明として供給照合のみにフォールバックする合図に使う)。
_N_IN_PARENS = re.compile(r"\((\d+)\)$")
_N_AFTER_THRESHOLD = re.compile(r"[≥](\d+)$")


def extract_n(raw_tag: str) -> int | None:
    paren_match = _N_IN_PARENS.search(raw_tag)
    if paren_match:
        return int(paren_match.group(1))
    threshold_match = _N_AFTER_THRESHOLD.search(raw_tag)
    if threshold_match:
        return int(threshold_match.group(1))
    return None


class FulfillmentRule(TypedDict, total=False):
    require: str
    supplies: list[str]
    confidence: str
    category_resolution: bool


class NaturalRule(TypedDict):
    # AI_NOTE: v3でdeadline_turnを廃止しDEADLINE_CUM_PP固定値に統一(rules.md#墓場の自然増)。
    # natural_rateはper_pp単位(1PPあたりの増加量)。deckプロファイルはconfidence注記とnoteで人が追える。
    require: str
    natural_rate: float
    supplies: list[str]
    confidence: str


class FulfillmentMapRaw(TypedDict, total=False):
    auto: list[str]
    auto_or_supply: list[str]
    construction: list[str]
    natural_rules: list[NaturalRule]
    rules: list[FulfillmentRule]
    unclassified: list[str]


class CompiledNaturalRule(NamedTuple):
    require_base: str
    natural_rate: float
    supplies: list[SupplyPattern]


class CompiledRule(NamedTuple):
    require: SupplyPattern
    supplies: list[SupplyPattern]
    category_resolution: bool


class FulfillmentMap:
    """要求タグ→供給タグの充足マップ。auto/auto_or_supply/construction/natural/rules/unclassifiedの6分類を保持する。"""

    def __init__(self, raw: FulfillmentMapRaw) -> None:
        self.auto_bases: set[str] = {parse_pattern(t).base for t in raw["auto"]}
        self.auto_or_supply_bases: set[str] = {parse_pattern(t).base for t in raw.get("auto_or_supply", [])}
        self.construction_bases: set[str] = {parse_pattern(t).base for t in raw["construction"]}
        self.natural_rules: list[CompiledNaturalRule] = [
            CompiledNaturalRule(
                require_base=parse_pattern(rule["require"]).base,
                natural_rate=rule["natural_rate"],
                supplies=[parse_pattern(s) for s in rule["supplies"]],
            )
            for rule in raw.get("natural_rules", [])
        ]
        self.rules: list[CompiledRule] = [
            CompiledRule(
                require=parse_pattern(rule["require"]),
                supplies=[parse_pattern(s) for s in rule["supplies"]],
                category_resolution=rule.get("category_resolution", False),
            )
            for rule in raw["rules"]
        ]
        self.unclassified_bases: set[str] = {parse_pattern(t).base for t in raw.get("unclassified", [])}

    def classify(self, require: Tag) -> str:
        # AI_NOTE: 分類の優先順はauto/auto_or_supply/construction/unclassified→natural→rules→
        # どれにもマッチしなければunclassified(マップの穴)。auto_or_supplyはautoの次に判定し、
        # 供給タグも別途保持したい要求(進化イベント等)をauto単独と区別する。
        if require.base in self.auto_bases:
            return "auto"
        if require.base in self.auto_or_supply_bases:
            return "auto_or_supply"
        if require.base in self.construction_bases:
            return "construction"
        if require.base in self.unclassified_bases:
            return "unclassified"
        if any(require.base == rule.require_base for rule in self.natural_rules):
            return "natural"
        if any(require.base == rule.require.base for rule in self.rules):
            return "scored"
        return "unclassified"

    def natural_rule_for(self, require: Tag) -> CompiledNaturalRule | None:
        for rule in self.natural_rules:
            if rule.require_base == require.base:
                return rule
        return None

    def supplies_for(self, require: Tag) -> list[SupplyPattern]:
        # AI_NOTE: 同じベース名のruleが複数あっても(現状は無い想定)全部合成して候補を返す。
        supplies: list[SupplyPattern] = []
        for rule in self.rules:
            if rule.require.base == require.base:
                supplies.extend(rule.supplies)
        return supplies

    def category_resolution_for(self, require: Tag) -> bool:
        # AI_NOTE: 該当ベース名のruleでcategory_resolution:trueが1つでも立っていれば階層解決を許す。
        return any(rule.require.base == require.base and rule.category_resolution for rule in self.rules)


def load_fulfillment_map(path: Path = FULFILLMENT_MAP_PATH) -> FulfillmentMap:
    raw: FulfillmentMapRaw = json.loads(path.read_text(encoding="utf-8"))
    return FulfillmentMap(raw)


class CardCategory(NamedTuple):
    tribe_names: set[str]
    type_category: str | None  # follower/amulet/spell
    cost: int | None


class CategoryLookup:
    """個体名(正規化済み) → (種族集合, タイプ, コスト) の逆引き。

    要求パラメータがカテゴリ(tribe名+フォロワー等)で供給パラメータが個体名の場合の階層解決に使う
    (design.md §6.1「タグの文字列一致だけでは噛まないペア」への対応・v3追加)。トークンも含めて
    card.card_id全件を対象にする。名前照合はmeta.py._normalize_name準拠。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._by_name: dict[str, CardCategory] = {}
        self.tribe_names: set[str] = {row[0] for row in conn.execute("SELECT name FROM tribe")}
        rows = conn.execute("SELECT card_id, name, type_category, cost FROM card").fetchall()
        tribe_rows = conn.execute(
            "SELECT ct.card_id, t.name FROM card_tribe ct JOIN tribe t ON t.id = ct.tribe_id"
        ).fetchall()
        tribes_by_card: dict[int, set[str]] = {}
        for card_id, tribe_name in tribe_rows:
            tribes_by_card.setdefault(card_id, set()).add(tribe_name)
        for card_id, name, type_category, cost in rows:
            normalized = _normalize_name(name)
            self._by_name[normalized] = CardCategory(
                tribe_names=tribes_by_card.get(card_id, set()), type_category=type_category, cost=cost
            )

    def get(self, name: str) -> CardCategory | None:
        return self._by_name.get(_normalize_name(name))


# AI_NOTE: 要求パラメータの「(コストN以下)?種族名(・)?フォロワー」形式を種族名・上限コストへ分解する。
# 「アーティファクト・フォロワー」「妖精フォロワー」(中黒なし)「コスト5以下アーティファクト・フォロワー」の
# 3パターンを吸収する。「フォロワーコスト2以下」のようなサフィックス修飾やロイヤル等クラス名は対象外
# (パースできなければ非マッチのままレポートに「階層解決不能」として出す設計)。
_CATEGORY_PARAM_PATTERN = re.compile(r"^(?:コスト(\d+)以下)?(.+?)・?フォロワー$")


def _resolve_category_param(param: str, tribe_names: set[str]) -> tuple[str, int | None] | None:
    match = _CATEGORY_PARAM_PATTERN.match(param)
    if not match:
        return None
    max_cost_text, tribe_name = match.groups()
    if tribe_name not in tribe_names:
        return None  # tribeテーブルに存在しない語(例:単なる「フォロワー」)は種族カテゴリ要求ではない
    max_cost = int(max_cost_text) if max_cost_text is not None else None
    return tribe_name, max_cost


def _category_matches(
    require: Tag, supply_tags: list[Tag], allowed_patterns: list[SupplyPattern], category_lookup: CategoryLookup
) -> bool:
    # AI_NOTE: 要求パラメータがtribe名+フォロワー形式(コスト修飾可)の場合のみ試す。供給側の個体名
    # パラメータをCategoryLookupで引き、その種族を持つフォロワーであれば充足とみなす(design.md
    # 「個体名タグ→カテゴリ要求の階層欠如」への対応)。マッチしうるルール(capture=True)にのみ適用する。
    if require.param is None:
        return False
    resolved = _resolve_category_param(require.param, category_lookup.tribe_names)
    if resolved is None:
        return False
    tribe_name, max_cost = resolved
    for allowed in allowed_patterns:
        if not allowed.capture:
            continue
        for supply in supply_tags:
            if supply.base != allowed.base or supply.param is None:
                continue
            category = category_lookup.get(supply.param)
            if category is None or category.type_category != "follower":
                continue
            if tribe_name not in category.tribe_names:
                continue
            if max_cost is not None and (category.cost is None or category.cost > max_cost):
                continue
            return True
    return False


def _matches(
    require: Tag,
    supply_tags: list[Tag],
    allowed_patterns: list[SupplyPattern],
    category_lookup: CategoryLookup | None = None,
) -> bool:
    # AI_NOTE: allowed_patterns(ルールのsupplies)のうち、ベース名が一致し
    # ((X))ケースは要求側paramと供給側paramの正規化済み完全一致まで見る供給タグが、
    # 実際に候補集合の中にあるか判定する。通常一致で見つからずcategory_lookupが渡された場合のみ
    # (=呼び出し元がそのルールのcategory_resolution:trueを確認済み)階層解決にフォールバックする。
    for allowed in allowed_patterns:
        for supply in supply_tags:
            if supply.base != allowed.base:
                continue
            if not allowed.capture:
                return True  # (*)相当・パラメータ無し: パラメータ不問
            if supply.param == require.param:
                return True  # ((X))相当: 要求・供給のパラメータが一致して初めて充足
    if category_lookup is not None:
        return _category_matches(require, supply_tags, allowed_patterns, category_lookup)
    return False


class DeckCard(NamedTuple):
    card_id: int
    card_name: str
    require_tags: list[str]
    supply_tags: list[str]


def _load_decks(conn: sqlite3.Connection) -> dict[int, tuple[str, list[DeckCard]]]:
    # AI_NOTE: meta_deck×meta_deck_cardからcard_id解決済みの行だけを集め、デッキごとにカードの
    # require/supplyタグをまとめる。1枚のカードがrequire/supply両方持つ場合もあるため両方持たせる。
    decks: dict[int, tuple[str, list[DeckCard]]] = {}
    deck_rows = conn.execute("SELECT id, name FROM meta_deck").fetchall()
    for deck_id, deck_name in deck_rows:
        card_rows = conn.execute(
            "SELECT DISTINCT c.card_id, c.name FROM meta_deck_card mdc "
            "JOIN card c ON c.card_id = mdc.card_id WHERE mdc.deck_id = ?",
            (deck_id,),
        ).fetchall()
        cards = []
        for card_id, card_name in card_rows:
            require_tags = [
                row[0]
                for row in conn.execute(
                    "SELECT tag FROM atom_tag WHERE card_id = ? AND kind = 'require'", (card_id,)
                )
            ]
            supply_tags = [
                row[0]
                for row in conn.execute(
                    "SELECT tag FROM atom_tag WHERE card_id = ? AND kind = 'supply'", (card_id,)
                )
            ]
            cards.append(DeckCard(card_id=card_id, card_name=card_name, require_tags=require_tags, supply_tags=supply_tags))
        decks[deck_id] = (deck_name, cards)
    return decks


class UnfulfilledExample(NamedTuple):
    deck_name: str
    card_name: str
    card_note: str | None


class BenchResult(NamedTuple):
    category_counts: Counter[str]
    scored_total: int
    fulfilled_total: int
    unfulfilled_by_tag: dict[str, list[UnfulfilledExample]]
    affected_decks_by_tag: dict[str, set[int]]  # 未充足タグ→影響デッキid集合(同名デッキを正しく別カウントするため)
    unclassified_tags: set[str]
    natural_unknown_tags: set[str]  # natural対象だがNが数値抽出できず供給照合のみにフォールバックしたタグ


def _self_name_fulfilled(require: Tag, card_name: str) -> bool:
    # AI_NOTE: 「存在(自場:X)」のXがカード自身の名前(正規化一致)なら、そのカード自身(同名3積みの
    # 自分自身)が供給になるため他カード探索より前に充足扱いにする(design.md v2の自己除外ルール例外)。
    # meta.py._normalize_nameを流用し、攻略サイト表記の揺れ吸収と同じ正規化で比較する。
    if require.base != "存在" or require.param is None:
        return False
    return _normalize_name(require.param) == _normalize_name(card_name)


def _natural_fulfilled(raw_tag: str, rule: CompiledNaturalRule) -> bool | None:
    # AI_NOTE: 蓄積型要求(ネクロマンス/墓場≥N/連携)のPP単位自然増モデル(rules.md#墓場の自然増・
    # design.md§6.2)。N <= rate(per_pp)×DEADLINE_CUM_PP なら供給タグ無しでも自動充足。
    # rateはdedicated(専用構築)値を使う——環境デッキにその要求カードが入っている時点で専用構築と
    # みなせるため(design.md§6.2の注記どおり)。Nがプレースホルダで数値抽出できないタグ
    # (「墓場≥N」「連携(N)」)はNoneを返し、呼び出し元に供給照合へのフォールバックを促す。
    n = extract_n(raw_tag)
    if n is None:
        return None
    return n <= rule.natural_rate * DEADLINE_CUM_PP


def run_bench(conn: sqlite3.Connection, fmap: FulfillmentMap) -> BenchResult:
    # AI_NOTE: 各デッキ×各カード×そのカードのrequireタグごとに分類する。auto/auto_or_supplyは
    # 常時充足、construction/unclassifiedはスコア対象外。naturalは閾値内なら自動充足、超過または
    # N不明なら通常の供給照合(rulesと同じ_matches、category_lookup併用)にフォールバックする。
    # scored/naturalはどちらも最終的にscored_total/fulfilled_totalへ計上し充足率の分母に含める。
    category_lookup = CategoryLookup(conn)
    decks = _load_decks(conn)
    category_counts: Counter[str] = Counter()
    scored_total = 0
    fulfilled_total = 0
    unfulfilled_by_tag: dict[str, list[UnfulfilledExample]] = {}
    unclassified_tags: set[str] = set()
    natural_unknown_tags: set[str] = set()
    affected_decks_by_tag: dict[str, set[int]] = {}

    for deck_id, (deck_name, cards) in decks.items():
        card_supplies = {card.card_id: [parse_tag(t) for t in card.supply_tags] for card in cards}
        for card in cards:
            for raw_tag in card.require_tags:
                require = parse_tag(raw_tag)
                category = fmap.classify(require)
                category_counts[category] += 1

                if category in ("auto", "auto_or_supply"):
                    continue
                if category == "construction":
                    continue
                if category == "unclassified":
                    unclassified_tags.add(raw_tag)
                    continue

                if _self_name_fulfilled(require, card.card_name):
                    scored_total += 1
                    fulfilled_total += 1
                    continue

                if category == "natural":
                    rule = fmap.natural_rule_for(require)
                    assert rule is not None
                    natural_ok = _natural_fulfilled(raw_tag, rule)
                    if natural_ok is None:
                        natural_unknown_tags.add(raw_tag)
                    elif natural_ok:
                        scored_total += 1
                        fulfilled_total += 1
                        continue
                    allowed = rule.supplies
                    use_category = False
                else:
                    allowed = fmap.supplies_for(require)
                    use_category = fmap.category_resolution_for(require)

                scored_total += 1
                other_supplies = [
                    tag
                    for other_id, tags in card_supplies.items()
                    if other_id != card.card_id
                    for tag in tags
                ]
                if _matches(require, other_supplies, allowed, category_lookup if use_category else None):
                    fulfilled_total += 1
                    continue

                affected_decks_by_tag.setdefault(raw_tag, set()).add(deck_id)
                note_row = conn.execute("SELECT note FROM card_note WHERE card_id = ?", (card.card_id,)).fetchone()
                note = note_row[0] if note_row else None
                unfulfilled_by_tag.setdefault(raw_tag, []).append(
                    UnfulfilledExample(deck_name=deck_name, card_name=card.card_name, card_note=note)
                )

    return BenchResult(
        category_counts=category_counts,
        scored_total=scored_total,
        fulfilled_total=fulfilled_total,
        unfulfilled_by_tag=unfulfilled_by_tag,
        affected_decks_by_tag=affected_decks_by_tag,
        unclassified_tags=unclassified_tags,
        natural_unknown_tags=natural_unknown_tags,
    )


def format_report(result: BenchResult) -> str:
    # AI_NOTE: 標準出力とdata/bench_report.txtの両方に同じ全文を出す前提のフォーマット関数。
    lines: list[str] = []
    fulfillment_rate = result.fulfilled_total / result.scored_total if result.scored_total else 0.0
    lines.append("=== 回帰ベンチv3: 要求充足の機械採点 ===")
    lines.append(
        f"総計: スコア対象{result.scored_total}件 / 充足{result.fulfilled_total}件 / "
        f"充足率{fulfillment_rate:.1%}"
    )
    lines.append("区分別件数:")
    for category in ("scored", "natural", "auto", "auto_or_supply", "construction", "unclassified"):
        lines.append(f"  {category}: {result.category_counts.get(category, 0)}件")
    lines.append("")

    lines.append(f"=== 未充足ランキング(影響デッキ数降順・上位{RANKING_TOP_N}) ===")
    ranked = sorted(
        result.unfulfilled_by_tag.items(),
        key=lambda item: len(result.affected_decks_by_tag[item[0]]),
        reverse=True,
    )
    for tag, examples in ranked[:RANKING_TOP_N]:
        affected = len(result.affected_decks_by_tag[tag])
        lines.append(f"- {tag} (影響デッキ数: {affected})")
        for example in examples[:2]:
            note_part = f" note: {example.card_note}" if example.card_note else ""
            lines.append(f"    例: {example.deck_name} / {example.card_name}{note_part}")
    lines.append("")

    lines.append("=== unclassifiedタグ一覧(分類待ち) ===")
    for tag in sorted(result.unclassified_tags):
        lines.append(f"- {tag}")
    lines.append("")

    lines.append("=== natural判定でN不明のため供給照合のみにフォールバックしたタグ(注記) ===")
    if result.natural_unknown_tags:
        for tag in sorted(result.natural_unknown_tags):
            lines.append(f"- {tag}")
    else:
        lines.append("(なし)")
    lines.append("")

    lines.append("=== v3 natural_rules注記(PP単位・dedicated形状で採点、user_confirmed_2026-07-06) ===")
    lines.append(f"- 期限: 累積PP(T{DEADLINE_TURN})={_CUM_PP_BASE} + 後攻エクストラPP楽観+2 = {DEADLINE_CUM_PP}")
    lines.append("- natural_rules: ネクロマンス((X))・墓場≥N rate=0.5/PP (user_confirmed)")
    lines.append("- natural_rules: 連携((X)) rate=0.55/PP (user_confirmed、T8で連携20達成の逆算値)")

    return "\n".join(lines) + "\n"


def main() -> None:
    conn = connect()
    try:
        fmap = load_fulfillment_map()
        result = run_bench(conn, fmap)
    finally:
        conn.close()
    report = format_report(result)
    print(report)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
