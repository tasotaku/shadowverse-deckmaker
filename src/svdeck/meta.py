"""攻略サイト(gamewith/game8)のTier表とデッキ詳細ページから環境デッキを収集し、
外部メタ層(meta_deck / meta_deck_card)へミラーする。

対象はローテーション/アンリミテッド両フォーマットのTier表とそこからリンクされるデッキ詳細ページ。
外部メタ層は鮮度が命なので、毎回 DELETE→全INSERT で作り直す(ミラー層の作り直し方式)。

実行: python -m svdeck.meta
"""

import html
import re
import sqlite3
import time
import urllib.request
from typing import NamedTuple

from svdeck.db import connect

USER_AGENT = "Mozilla/5.0"
REQUEST_INTERVAL_SEC = 1.0

# AI_NOTE: (site, format, url)のタプル一覧。ローテ/アンリミ両方を同じループで回すため
# サイト別URL定数ではなくテーブル形式にした(フォーマット追加時はここに1行足すだけで済む)。
TIER_SOURCES: list[tuple[str, str, str]] = [
    ("gamewith", "rotation", "https://gamewith.jp/shadowverse-wb/497197"),
    ("game8", "rotation", "https://game8.jp/shadowverse-beyond/694512"),
    ("gamewith", "unlimited", "https://gamewith.jp/shadowverse-wb/550564"),
    ("game8", "unlimited", "https://game8.jp/shadowverse-beyond/780976"),
]


class DeckLink(NamedTuple):
    site: str
    url: str
    name: str
    tier: str
    format: str


class DeckDetail(NamedTuple):
    updated_on: str | None
    cards: list[tuple[str, int]]  # (card_name, count)


def _get_html(url: str) -> str:
    # AI_NOTE: HTTP境界。取得失敗は握りつぶさず呼び出し元へ伝播させる(fetch.pyと同じ作法)。
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        body: bytes = response.read()
    return body.decode("utf-8")


def _normalize_name(name: str) -> str:
    # AI_NOTE: 攻略サイト表記と公式表記の揺れ(中黒の有無・全角/半角記号)を吸収してcard.nameと突き合わせる。
    return name.replace("・", "").replace("&", "＆").replace("=", "＝").strip()


def parse_gamewith_tier(html_text: str, deck_format: str = "rotation") -> list[DeckLink]:
    # AI_NOTE: Tier表本体は<div class="w-tier-table-ui">直下の<li d-name d-tier d-link>群。
    # d-tierは数値(1〜4)なのでそのまま文字列化してtier表現とする。deck_formatは呼び出し元(TIER_SOURCES)
    # から渡してもらう単なるラベルで、パース対象の構造には影響しない。
    start = html_text.find('class="w-tier-table-ui"')
    if start == -1:
        return []
    end = html_text.find("</div>", start)
    segment = html_text[start:end]
    items = re.findall(r'd-name="([^"]+)" d-tier="(\d+)"[^>]*d-link="([^"]+)"', segment)
    return [
        DeckLink(site="gamewith", url=url, name=html.unescape(name), tier=tier, format=deck_format)
        for name, tier, url in items
    ]


def parse_gamewith_deck(html_text: str) -> DeckDetail:
    # AI_NOTE: デッキリストは<ol class="wd-decklist"><li card-number d-id></li>...</ol>で、
    # カード名はwindow.wmt.cardDatasのid->n辞書から引く(サイト独自idで公式card_idとは別体系のため)。
    updated_match = re.search(r'<time datetime="([^"]+)">', html_text)
    updated_on = updated_match.group(1) if updated_match else None

    list_start = html_text.find('<ol class="wd-decklist">')
    if list_start == -1:
        return DeckDetail(updated_on=updated_on, cards=[])
    list_end = html_text.find("</ol>", list_start)
    list_segment = html_text[list_start:list_end]
    entries = re.findall(r'card-number="(\d+)"><icard data-id="(\d+)"', list_segment)

    dict_start = html_text.find("window.wmt.cardDatas=[")
    dict_end = html_text.find("];", dict_start)
    dict_segment = html_text[dict_start + len("window.wmt.cardDatas=[") : dict_end] if dict_start != -1 else ""
    id_to_name = dict(re.findall(r"id:'(\d+)',[^}]*?n:'([^']+)'", dict_segment))

    cards = [(id_to_name[card_id], int(count)) for count, card_id in entries if card_id in id_to_name]
    return DeckDetail(updated_on=updated_on, cards=cards)


def parse_game8_tier(html_text: str, deck_format: str = "rotation") -> list[DeckLink]:
    # AI_NOTE: Game8は2026-07に「Tierバナー+横並び」から「Tierごとの表」へローテページを変更した。
    # Tier 1〜3見出しごとに次の見出しまでを切り、カード画像のalt末尾「画像」だけを読むことで、
    # 表中の「評価コメント」リンクをデッキとして誤収集せず、旧レイアウトにも依存しない。
    heading_pattern = re.compile(r'<h3[^>]*>Tier([123])[^<]*</h3>', re.DOTALL)
    links: list[DeckLink] = []
    headings = list(heading_pattern.finditer(html_text))
    for index, heading in enumerate(headings):
        tier = heading.group(1)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(html_text)
        block = html_text[heading.end() : end]
        for url, name in re.findall(r'href="([^"]+)"[^>]*><img[^>]*alt="([^"]+?)画像"', block):
            links.append(
                DeckLink(site="game8", url=url, name=html.unescape(name), tier=tier, format=deck_format)
            )
    if links:
        return links

    # AI_NOTE: 保存済みHTMLや未移行ページは旧バナー形式のままなので、移行前の抽出も後方互換として残す。
    start = html_text.find('id="hl_1"')
    end = html_text.find('id="hl_2"', start)
    if start == -1 or end == -1:
        return []
    segment = html_text[start:end]
    legacy_pattern = re.compile(r'alt="(SS|S|A|B|C)バナー".*?<div class="align">(.*?)</div>', re.DOTALL)
    for tier_match in legacy_pattern.finditer(segment):
        tier, block = tier_match.group(1), tier_match.group(2)
        for url, name in re.findall(r'href="([^"]+)"[^>]*><img[^>]*alt="([^"]+)"', block):
            links.append(DeckLink(site="game8", url=url, name=html.unescape(name), tier=tier, format=deck_format))
    return links


def parse_game8_deck(html_text: str) -> DeckDetail:
    # AI_NOTE: 「デッキレシピ」見出し(hl_1)〜「みんなの評価」見出しの区間にあるtdブロックを走査する。
    # 各tdはtooltip内のalt="{名前}画像"とその後の<b class="a-bold">×{枚数}</b>のペア。
    # 更新日はJSON-LDのdateModifiedから取る(記事メタなので構造が安定している)。
    updated_match = re.search(r'"dateModified":"([^"]+)"', html_text)
    updated_on = updated_match.group(1) if updated_match else None

    start = html_text.find('id="hl_1"')
    end = html_text.find('id="hl_2"', start) if start != -1 else -1
    if start == -1 or end == -1:
        return DeckDetail(updated_on=updated_on, cards=[])
    segment = html_text[start:end]
    pattern = re.compile(
        r'<td width="20%" class="center">\s*<span class="js-detail-tooltip.*?alt="([^"]+?)画像".*?</span>\s*'
        r'<b class="a-bold">×(\d+)</b>',
        re.DOTALL,
    )
    cards = [(html.unescape(name), int(count)) for name, count in pattern.findall(segment)]
    return DeckDetail(updated_on=updated_on, cards=cards)


def _resolve_card_id(conn: sqlite3.Connection, card_name: str) -> int | None:
    # AI_NOTE: 完全一致で見つからなければ、中黒・&表記揺れを正規化して再照合する。
    row = conn.execute("SELECT card_id FROM card WHERE name = ?", (card_name,)).fetchone()
    if row is not None:
        return int(row[0])
    normalized = _normalize_name(card_name)
    for candidate_id, candidate_name in conn.execute("SELECT card_id, name FROM card"):
        if _normalize_name(candidate_name) == normalized:
            return int(candidate_id)
    return None


def collect_deck_links() -> list[DeckLink]:
    # AI_NOTE: TIER_SOURCES(サイト×フォーマットの全組)を順にループしてデッキリンクを集める。
    # 取得間隔を空けてサーバ負荷を抑える(ソース数が増えてもリクエスト間は一律REQUEST_INTERVAL_SEC)。
    links: list[DeckLink] = []
    for site, deck_format, url in TIER_SOURCES:
        html_text = _get_html(url)
        parser = parse_gamewith_tier if site == "gamewith" else parse_game8_tier
        links.extend(parser(html_text, deck_format))
        time.sleep(REQUEST_INTERVAL_SEC)
    return links


def collect_deck_detail(link: DeckLink) -> DeckDetail:
    time.sleep(REQUEST_INTERVAL_SEC)
    html_text = _get_html(link.url)
    if link.site == "gamewith":
        return parse_gamewith_deck(html_text)
    return parse_game8_deck(html_text)


def run() -> None:
    # AI_NOTE: エントリポイント。meta_deck/meta_deck_cardを毎回作り直す(外部メタ層は鮮度優先)。
    conn = connect()
    try:
        links = collect_deck_links()
        print(f"[meta] Tier表からデッキ{len(links)}件を検出")

        deck_rows = []
        card_rows: list[tuple[int, str, int, int | None]] = []
        matched, total_cards = 0, 0
        for i, link in enumerate(links):
            detail = collect_deck_detail(link)
            deck_id = i + 1
            deck_rows.append(
                (deck_id, link.site, link.url, link.name, link.tier, link.format, detail.updated_on)
            )
            for card_name, count in detail.cards:
                card_id = _resolve_card_id(conn, card_name)
                total_cards += 1
                matched += card_id is not None
                card_rows.append((deck_id, card_name, count, card_id))
            print(f"[meta] {i + 1}/{len(links)}: [{link.site}/{link.format}] {link.name} カード{len(detail.cards)}種")

        conn.execute("DELETE FROM meta_deck_card")
        conn.execute("DELETE FROM meta_deck")
        conn.executemany(
            "INSERT INTO meta_deck (id, site, url, name, tier, format, updated_on, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            deck_rows,
        )
        conn.executemany(
            "INSERT INTO meta_deck_card (deck_id, card_name, count, card_id) VALUES (?, ?, ?, ?)",
            card_rows,
        )
        conn.commit()

        rate = f"{matched}/{total_cards}" + (f" ({matched / total_cards:.0%})" if total_cards else "")
        print(f"[meta] 完了: デッキ{len(deck_rows)}件 / card_idマッチ {rate}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
