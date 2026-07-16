"""方向A: デッキ=供給の束 × 外のカード=小さなアンカー(design.md §6.5.2)。

環境デッキ40枚(+トークン伝播)の供給タグを1つの束に畳み、デッキ外の「要求タグを持つカード」の
要求がその束に型一致するかを引く。reverse.py(1枚→アンカー要求)のデッキ版で、判定器は
explore.pyの型一致経路(classify→natural/rules→_matched_supply_tag)をそのまま共用する。

自明対策は希少度ランキング(§6.5.2): 要求タグごとに「ローテ環境デッキのうち何デッキが満たせるか」を
数え、少ないほど上位に出す(進化権のような万人向け要求は自動で沈む)。自明さの絶対判定はしない。
量の算術(§6.2 accumulate)は型一致のみでスキップ(reverse.pyと同じ割り切り・forward exploreの仕事)。

  [デッキD] -> [供給タグ束(40枚+トークン伝播・供給元カード付き)]
            -> [候補=同クラス+ニュートラル・ローテ合法・D未採用・要求タグ持ち] -> [型一致]
            -> [希少度(満たせる環境デッキ数)で昇順] -> [調書]

実行: PYTHONPATH=src python -m svdeck.augment <deck_id ...>
"""

import sqlite3
import sys
from typing import NamedTuple

from svdeck.bench import CategoryLookup, FulfillmentMap, SupplyPattern, Tag, load_fulfillment_map, parse_tag
from svdeck.db import connect
from svdeck.explore import _matched_supply_tag, card_supply_tags


class SupplyPool(NamedTuple):
    # AI_NOTE: デッキ1つ分の供給束。tags=判定用 / sources=生タグ→供給元カード名(調書のヒット根拠表示用)。
    tags: list[tuple[str, Tag]]
    sources: dict[str, list[str]]


def deck_supply_pool(conn: sqlite3.Connection, deck_id: int,
                     cache: dict[int, list[tuple[str, Tag]]]) -> SupplyPool:
    # AI_NOTE: 40枚の card_supply_tags(トークン伝播込み)を1束に。同じ生タグは供給元を追記して重複除去。
    # cacheはカード単位(全デッキ横断の希少度計算で同じカードを何度も引くため)。
    rows = conn.execute(
        "SELECT DISTINCT mdc.card_id, mdc.card_name FROM meta_deck_card mdc "
        "WHERE mdc.deck_id = ? AND mdc.card_id IS NOT NULL", (deck_id,)
    ).fetchall()
    tags: list[tuple[str, Tag]] = []
    sources: dict[str, list[str]] = {}
    for card_id, card_name in rows:
        if card_id not in cache:
            cache[card_id] = card_supply_tags(conn, card_id)
        for raw, parsed in cache[card_id]:
            if raw not in sources:
                sources[raw] = []
                tags.append((raw, parsed))
            if card_name not in sources[raw]:
                sources[raw].append(card_name)
    return SupplyPool(tags, sources)


def _requirement_route(fmap: FulfillmentMap, tag: Tag,
                       category_lookup: CategoryLookup) -> tuple[list[SupplyPattern], CategoryLookup | None] | None:
    # AI_NOTE: reverse.pyと同じ分類経路。型一致で判定できないカテゴリ(unclassified/auto系/construction)はNone。
    category = fmap.classify(tag)
    if category in ("unclassified", "auto", "auto_or_supply", "construction"):
        return None
    if category == "natural":
        rule = fmap.natural_rule_for(tag)
        return (rule.supplies if rule is not None else [], None)
    return (fmap.supplies_for(tag), category_lookup if fmap.category_resolution_for(tag) else None)


class Hit(NamedTuple):
    card_id: int
    card_name: str
    class_name: str
    cost: int
    requirement: str
    matched_supply: str
    rarity: int


def find_candidates(conn: sqlite3.Connection, deck_id: int) -> tuple[str, list[Hit], int]:
    # AI_NOTE: 方向A本体。戻り=(デッキ名, ヒット一覧(希少度昇順), ローテ環境デッキ総数)。
    deck_row = conn.execute("SELECT name FROM meta_deck WHERE id = ?", (deck_id,)).fetchone()
    if deck_row is None:
        raise ValueError(f"deck_id {deck_id} は meta_deck に存在しない")
    deck_cards = {row[0] for row in conn.execute(
        "SELECT card_id FROM meta_deck_card WHERE deck_id = ? AND card_id IS NOT NULL", (deck_id,))}
    class_row = conn.execute(
        "SELECT DISTINCT c.class_name FROM meta_deck_card mdc JOIN card c USING(card_id) "
        "WHERE mdc.deck_id = ? AND c.class_name != 'ニュートラル'", (deck_id,)).fetchall()
    class_name = class_row[0][0] if class_row else "ニュートラル"

    fmap = load_fulfillment_map()
    category_lookup = CategoryLookup(conn)
    cache: dict[int, list[tuple[str, Tag]]] = {}
    pool = deck_supply_pool(conn, deck_id, cache)

    # AI_NOTE: 希少度の分母=ローテの環境デッキ全部の供給束(対象デッキ含む)。要求タグ単位でメモ化。
    rotation_ids = [row[0] for row in conn.execute("SELECT id FROM meta_deck WHERE format = 'rotation'")]
    all_pools = {did: deck_supply_pool(conn, did, cache) for did in rotation_ids}
    rarity_memo: dict[str, int] = {}

    def rarity(raw_req: str, tag: Tag, allowed: list[SupplyPattern], lookup: CategoryLookup | None) -> int:
        if raw_req not in rarity_memo:
            rarity_memo[raw_req] = sum(
                1 for p in all_pools.values() if _matched_supply_tag(tag, p.tags, allowed, lookup) is not None
            )
        return rarity_memo[raw_req]

    hits: list[Hit] = []
    candidates = conn.execute(
        """
        SELECT c.card_id, c.name, c.class_name, c.cost, a.tag
        FROM card c JOIN atom_tag a USING(card_id)
        WHERE a.kind = 'require' AND c.is_token != 1 AND c.is_include_rotation = 1
          AND c.class_name IN (?, 'ニュートラル')
        ORDER BY c.card_id
        """,
        (class_name,),
    ).fetchall()
    for card_id, name, cls, cost, raw_req in candidates:
        if card_id in deck_cards:
            continue
        tag = parse_tag(raw_req)
        route = _requirement_route(fmap, tag, category_lookup)
        if route is None:
            continue
        allowed, lookup = route
        matched = _matched_supply_tag(tag, pool.tags, allowed, lookup)
        if matched is None:
            continue
        hits.append(Hit(card_id, name, cls, cost or 0, raw_req, matched, rarity(raw_req, tag, allowed, lookup)))
    hits.sort(key=lambda h: (h.rarity, h.card_id))
    return deck_row[0], hits, len(rotation_ids)


def format_report(deck_id: int, deck_name: str, hits: list[Hit], total_decks: int,
                  pool: SupplyPool) -> str:
    lines = [f"=== 方向A: [{deck_id}] {deck_name} の供給束に噛む外部カード (希少度昇順) ==="]
    if not hits:
        lines.append("ヒットなし")
        return "\n".join(lines) + "\n"
    for h in hits:
        srcs = ", ".join(pool.sources.get(h.matched_supply, [])[:4])
        lines.append(
            f"- [{h.card_id}] {h.card_name} ({h.class_name} {h.cost}コスト) "
            f"要求「{h.requirement}」← 供給: {h.matched_supply} (元: {srcs}) "
            f"[希少度 {h.rarity}/{total_decks}デッキ]"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口(explore/reverseと同じ流儀)。
    args = sys.argv[1:]
    if not args or not all(a.isdigit() for a in args):
        print("usage: python -m svdeck.augment <deck_id ...>")
        sys.exit(1)
    conn = connect()
    try:
        for arg in args:
            deck_id = int(arg)
            deck_name, hits, total = find_candidates(conn, deck_id)
            pool = deck_supply_pool(conn, deck_id, {})
            print(format_report(deck_id, deck_name, hits, total, pool))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
