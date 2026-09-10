"""攻略サイト(gamewith/game8)のTier表とデッキ詳細ページから環境デッキを収集し、
外部メタ層(meta_deck / meta_deck_card)へミラーする。

対象はローテーション/アンリミテッド両フォーマットのTier表とそこからリンクされるデッキ詳細ページ。
外部メタ層は鮮度が命なので、毎回 DELETE→全INSERT で作り直す(ミラー層の作り直し方式)。

実行: python -m svdeck.meta
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.request
from urllib.parse import parse_qs, urlparse
from typing import NamedTuple
from typing import Any

from svdeck.db import DB_PATH, connect
from svdeck.article_text import article_text

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
    variant: str = ""
    anchor: str = ""
    copy_url: str = ""


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

    missing = [card_id for _, card_id in entries if card_id not in id_to_name]
    if missing:
        raise ValueError(f"GameWithのカード名辞書にIDがありません: {missing}。該当札を省いて更新しません")
    cards = [(id_to_name[card_id], int(count)) for count, card_id in entries]
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


def parse_game8_decks(html_text: str) -> list[DeckDetail]:
    # AI_NOTE: 主レシピ節の小見出しごとに分離し、表示表と同じ見出しのコピー先を対応付ける。
    updated_match = re.search(r'"dateModified":"([^"]+)"', html_text)
    updated_on = updated_match.group(1) if updated_match else None
    start = re.search(r'<h2\b[^>]*\bid="hl_1"[^>]*>', html_text)
    if start is None:
        raise ValueError("Game8の主レシピ節hl_1が見つかりません")
    segment = re.split(r'<h2\b', html_text[start.end():], maxsplit=1)[0]
    headings = list(re.finditer(r'<h3\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</h3>', segment, re.DOTALL))
    pattern = re.compile(
        r'<td width="20%" class="center">\s*<span class="js-detail-tooltip.*?alt="([^"]+?)画像".*?</span>\s*'
        r'<b class="a-bold">×(\d+)</b>',
        re.DOTALL,
    )
    details = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(segment)
        block = segment[heading.end():end]
        if not re.search(r'<th\b[^>]*\bcolspan="5"[^>]*>\s*デッキレシピ\s*</th>', block):
            continue
        links = list(dict.fromkeys(html.unescape(url) for url in re.findall(r'href="([^"]+)"', block)
                                   if urlparse(html.unescape(url)).hostname == "shadowverse-wb.com"
                                   and urlparse(html.unescape(url)).path.endswith("/deck/detail/")))
        if len(links) > 1:
            raise ValueError("1つのレシピ見出しに複数のコピー先があります。対応を確認してください")
        cards = [(html.unescape(name), int(count)) for name, count in pattern.findall(block)]
        variant = html.unescape(re.sub(r'<[^>]+>', '', heading.group(2))).strip()
        details.append(DeckDetail(updated_on, cards, variant, heading.group(1), links[0] if links else ""))
    if not details:
        raise ValueError("Game8の主レシピ節から独立したデッキレシピを読めません")
    return details


def parse_game8_deck(html_text: str) -> DeckDetail:
    # AI_NOTE: 単一レシピ用の既存入口で複数構築を混ぜたり、黙って1件だけ落としたりしない。
    details = parse_game8_decks(html_text)
    if len(details) != 1:
        raise ValueError("複数レシピがあります。parse_game8_decksを使って別々に取得してください")
    return details[0]


def validate_deck(cards: list[tuple[str, int]], label: str) -> None:
    # AI_NOTE: 不完全なリストをミラーへ入れず、同名の重複も合算で隠さない。
    names = set()
    for name, count in cards:
        if not isinstance(name, str) or not name.strip() or type(count) is not int or count <= 0:
            raise ValueError(f"{label}: 空でないカード名と正の整数枚数が必要です")
        normalized = _normalize_name(name)
        if normalized in names:
            raise ValueError(f"{label}: カード名が重複しています: {name}")
        names.add(normalized)
    total = sum(count for _, count in cards)
    if total != 40:
        raise ValueError(f"{label}: 全40枚が必要ですが{total}枚です。欠けた札は推測しません")


def _recipe_cards(conn: sqlite3.Connection, detail: DeckDetail, label: str,
                  deck_format: str | None = None) -> list[tuple[str, int, int | None]]:
    # AI_NOTE: コピーURLが明示するカードIDを直接使う。表示表との不一致は報告し、欠落を推測しない。
    if not detail.copy_url:
        validate_deck(detail.cards, label)
        return [(name, count, _resolve_card_id(conn, name)) for name, count in detail.cards]
    values = parse_qs(urlparse(detail.copy_url).query).get("hash", [])
    if len(values) != 1 or not re.fullmatch(r'[12]\.[1-7](?:\.[0-9A-Za-z_-]+){40}', values[0]):
        raise ValueError(f"{label}: コピーURLの40枚形式を読めません")
    if deck_format is not None and values[0][0] != {"rotation": "1", "unlimited": "2"}[deck_format]:
        raise ValueError(f"{label}: コピーURLとTier表のフォーマットが一致しません")
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
    counts: Counter[int] = Counter()
    for token in values[0].split(".")[2:]:
        cid = 0
        for character in token:
            cid = cid * 64 + alphabet.index(character)
        counts[cid] += 1
    result: list[tuple[str, int, int | None]] = []
    for cid, count in counts.items():
        row = conn.execute("SELECT name FROM card WHERE card_id=?", (cid,)).fetchone()
        if row is None:
            raise ValueError(f"{label}: コピー先のカードID{cid}が保存DBにありません")
        result.append((str(row[0]), count, cid))
    cards = [(name, count) for name, count, _ in result]
    validate_deck(cards, label)
    return result


def _recipe_source(link: DeckLink, detail: DeckDetail, cards: list[tuple[str, int, int | None]]) -> dict[str, Any]:
    # AI_NOTE: 取得対象・元見出し・表との差分をDBへ残し、次の探索担当にも同じ根拠を渡す。
    shown: Counter[str] = Counter()
    for name, count in detail.cards:
        shown[_normalize_name(name)] += count
    copied = Counter({_normalize_name(name): count for name, count, _ in cards})
    copied_names = {_normalize_name(name): name for name, _, _ in cards}
    shown_names = {_normalize_name(name): name for name, _ in detail.cards}
    difference = {"copy_only_or_extra": [{"name": copied_names[name], "count": count} for name, count in (copied - shown).items()],
                  "display_only_or_extra": [{"name": shown_names[name], "count": count} for name, count in (shown - copied).items()]}
    return {"article_url": link.url, "heading": detail.variant or None, "heading_id": detail.anchor or None,
            "selected_list": "copy_url" if detail.copy_url else "display_table", "copy_url": detail.copy_url or None,
            "display_total": sum(shown.values()), "selected_total": sum(count for _, count, _ in cards),
            "display_matches_copy": shown == copied if detail.copy_url else None,
            "display_copy_difference": difference if detail.copy_url else None}


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
        found = parser(html_text, deck_format)
        if not found:
            raise ValueError(f"{url}: Tier表にデッキが見つかりません。既存ミラーを維持します")
        links.extend(found)
        time.sleep(REQUEST_INTERVAL_SEC)
    return links


def collect_deck_details(link: DeckLink) -> list[DeckDetail]:
    time.sleep(REQUEST_INTERVAL_SEC)
    html_text = _get_html(link.url)
    if link.site == "gamewith":
        return [parse_gamewith_deck(html_text)]
    return parse_game8_decks(html_text)


def run(db: Path = DB_PATH) -> None:
    # AI_NOTE: 指定した保存先の外部メタ層だけを、全取得が終わってから置き換える。
    conn = connect(db)
    try:
        links = collect_deck_links()
        if not links:
            raise ValueError("取得したデッキが0件です。既存ミラーを維持します")
        print(f"[meta] Tier表からデッキ{len(links)}件を検出")

        deck_rows: list[tuple[int, str, str, str, str, str, str | None, str]] = []
        card_rows: list[tuple[int, str, int, int | None]] = []
        matched, total_cards = 0, 0
        for i, link in enumerate(links):
            details = collect_deck_details(link)
            if not details:
                raise ValueError(f"{link.url}: デッキリストが0件です")
            for detail in details:
                name = f"{link.name}（{detail.variant}）" if len(details) > 1 else link.name
                url = f"{link.url}#{detail.anchor}" if len(details) > 1 else link.url
                resolved = _recipe_cards(conn, detail, f"{name} {url}", link.format)
                source = _recipe_source(link, detail, resolved)
                if source["display_matches_copy"] is False:
                    print(f"[meta] 表示表とコピー先が不一致: {name} {url} 表{source['display_total']}枚/コピー40枚。"
                          f"差分={source['display_copy_difference']} コピー先={detail.copy_url}")
                deck_id = len(deck_rows) + 1
                deck_rows.append((deck_id, link.site, url, name, link.tier, link.format, detail.updated_on,
                                  json.dumps(source, ensure_ascii=False)))
                for card_name, count, card_id in resolved:
                    total_cards += 1
                    matched += card_id is not None
                    card_rows.append((deck_id, card_name, count, card_id))
                origin = "記事のコピー対象リスト" if detail.copy_url else "記事の表示リスト"
                print(f"[meta] {i + 1}/{len(links)}: [{link.site}/{link.format}] {name} "
                      f"カード{len(resolved)}種/40枚 取得対象={origin}")

        conn.execute("DELETE FROM meta_deck_card")
        conn.execute("DELETE FROM meta_deck")
        conn.executemany(
            "INSERT INTO meta_deck (id, site, url, name, tier, format, updated_on, source_json, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
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


def article_sources(db: Path, url: str, deck_format: str, with_text: bool = False) -> dict[str, Any]:
    # AI_NOTE: 必要な記事だけを読み、リストと取得根拠を既存の資料形式へ出す。保存DBは変更しない。
    parsed = urlparse(url)
    sites = {"gamewith.jp": "gamewith", "game8.jp": "game8"}
    if parsed.scheme != "https" or parsed.hostname not in sites:
        raise ValueError("記事URLはGameWithまたはGame8のHTTPS URLを指定してください")
    link = DeckLink(sites[parsed.hostname], url, "指定記事", "", deck_format)
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        explanation = None
        if with_text:
            time.sleep(REQUEST_INTERVAL_SEC)
            html_text = _get_html(url)
            details = [parse_gamewith_deck(html_text)] if link.site == "gamewith" else parse_game8_decks(html_text)
            explanation = article_text(html_text, link.site)
        else:
            details = collect_deck_details(link)
        if not details:
            raise ValueError("記事のデッキリストが0件です")
        observed = datetime.now(timezone.utc).isoformat()
        sources = []
        for detail in details:
            cards = _recipe_cards(conn, detail, url, deck_format)
            if any(cid is None for _, _, cid in cards):
                raise ValueError("保存DBと照合できないカードがあります。IDを推測せず取得を中止します")
            location = url.split("#", 1)[0] + (f"#{detail.anchor}" if detail.anchor else "")
            title = detail.variant or "記事の構築"
            limits = ["指定したフォーマットの資料。カード本文・合法性・現在のTier・勝率はこの取得では確認しない。",
                      "記事の表示表とコピー先の相違、記事更新日時は同じ出典の取得情報を参照。"]
            entries = [{"card_id": cid, "count": count, "name": name} for name, count, cid in cards]
            provenance = {**_recipe_source(link, detail, cards), "format": deck_format,
                          "article_updated_on": detail.updated_on, "current_tier": None}
            sources.extend([
                {"title": title, "kind": "公開記事の全40枚リスト", "location": location,
                 "observed_at": observed, "content": json.dumps(entries, ensure_ascii=False, indent=2), "limitations": limits},
                {"title": title + "の取得情報", "kind": "記事から取得した出典情報", "location": location,
                 "observed_at": observed, "content": json.dumps(provenance, ensure_ascii=False, indent=2), "limitations": limits},
            ])
        if explanation is not None:
            sources.append({"title": "記事の説明本文", "kind": "公開記事の説明", "location": url.split("#", 1)[0],
                            "observed_at": observed, "content": json.dumps(explanation, ensure_ascii=False, indent=2),
                            "limitations": [explanation["scope"], "記事内の記述は出典の主張であり、公式能力・実戦の強さ・普及をこの取得で認定しない。"]})
        return {"sources": sources}
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    # AI_NOTE: 記事の読取出力と一覧更新を引数で分け、形式指定の誤りでは取得前に止める。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH, help="取得結果を保存するカードDB")
    parser.add_argument("--article", help="指定記事だけを読み、discovery attach用の資料JSONを標準出力へ返す。DBは変更しない")
    parser.add_argument("--format", choices=("rotation", "unlimited"), help="記事取得時の対象フォーマット")
    parser.add_argument("--with-article-text", action="store_true", help="同じ取得から記事の説明も資料として追加する（任意）")
    args = parser.parse_args(argv)
    if bool(args.article) != bool(args.format):
        parser.error("--articleと--formatは一緒に指定してください")
    if args.with_article_text and not args.article:
        parser.error("--with-article-textには--articleと--formatが必要です")
    try:
        if args.article:
            print(json.dumps(article_sources(args.db, args.article, args.format, args.with_article_text), ensure_ascii=False, indent=2))
        else:
            run(args.db)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"[meta] 取得中止: {exc}。保存済みの環境デッキ一覧は変更していません", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
