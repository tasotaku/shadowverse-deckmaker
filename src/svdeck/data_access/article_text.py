"""取得済みHTMLから記事の説明を取り出す。カードの意味や記事の真偽は判定しない。"""

import hashlib
from html.parser import HTMLParser
import re
from typing import Any


class ArticleText(HTMLParser):
    def __init__(self, site: str, names: dict[str, str]) -> None:
        # AI_NOTE: サイトの本文領域だけを対象にし、見出し・表行の区切りを残す。
        super().__init__(convert_charrefs=True)
        self.site = site
        self.names = names
        self.stack: list[tuple[str, bool]] = []
        self.root: int | None = None
        self.roots = 0
        self.closed = False
        self.stopped = False
        self.started = False
        self.parts: list[str] = []
        self.lines: list[str] = []
        self.images = 0
        self.missing_names: set[str] = set()

    def flush(self) -> None:
        # AI_NOTE: 空白だけを正規化し、表内の改行は同じ行の理由として保持する。
        text = re.sub(r"\s+", " ", "".join(self.parts)).strip(" |")
        self.parts = []
        if text.startswith("## ") and "関連記事" in text:
            self.stopped = True
        if text and self.started and not self.stopped:
            self.lines.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # AI_NOTE: 非表示コードとサイト内導線を除き、画像だけのカード名も同じ表行へ入れる。
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        is_root = (self.site == "gamewith" and values.get("id") == "article-body"
                   or self.site == "game8" and "archive-style-wrapper" in classes)
        if is_root:
            self.roots += 1
            self.root = len(self.stack)
        excluded = {"article_outline", "a-outline", "wd-decklist", "w-tier-table-ui", "browsi-atf",
                    "ad-wrapper", "premium-plan-link", "react-user_rating-wrapper", "card_in_the_deck"}
        skipped = (bool(not is_root and self.stack and self.stack[-1][1]) or self.root is None or self.stopped
                   or tag in {"script", "style", "noscript", "template", "svg", "nav", "iframe", "button", "gds-walkthrough-vote"}
                   or bool(classes & excluded) or "hidden" in values or values.get("aria-hidden") == "true")
        if not skipped:
            in_row = any(item[0] == "tr" for item in self.stack)
            if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                self.flush()
                if tag == "h2":
                    self.started = True
                self.parts.append("#" * int(tag[1]) + " ")
            elif tag in {"tr", "p", "div", "ul", "ol", "li"} and not in_row:
                self.flush()
            elif tag in {"td", "th"}:
                self.parts.append(" | ")
            elif tag in {"br", "hr"}:
                self.parts.append(" / " if in_row else "\n")
            if tag == "icard":
                key = values.get("data-id") or "?"
                name = self.names.get(key)
                self.parts.append(f"［{name or 'カード名不明: ' + key}］")
                if name is None:
                    self.missing_names.add(key)
            if tag == "img":
                self.images += 1
                if not any(item[0] == "icard" for item in self.stack) and values.get("alt"):
                    self.parts.append(f"［{values['alt']}］")
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, skipped))

    def handle_endtag(self, tag: str) -> None:
        # AI_NOTE: 対応する開始要素まで閉じ、本文外へ出た後のコメント等を読み込まない。
        positions = [i for i, item in enumerate(self.stack) if item[0] == tag]
        if not positions:
            return
        index = positions[-1]
        if not self.stack[-1][1] and tag in {"h1", "h2", "h3", "h4", "h5", "h6", "tr", "p", "div", "li"}:
            if tag == "tr" or not any(item[0] == "tr" for item in self.stack[:index]):
                self.flush()
        self.stack = self.stack[:index]
        if self.root is not None and index <= self.root:
            self.flush()
            self.root = None
            self.closed = True

    def handle_data(self, data: str) -> None:
        # AI_NOTE: 本文領域の可視テキストだけを前後のラベル・理由と同じ順で残す。
        if self.stack and not self.stack[-1][1] and not self.stopped:
            self.parts.append(data)


def article_text(html_text: str, site: str) -> dict[str, Any]:
    # AI_NOTE: 欠落を空の成功結果にしない。抽出元の識別値と未読の画像範囲を常に返す。
    names = dict(re.findall(r"id:'(\d+)',[^}]*?n:'([^']+)'", html_text)) if site == "gamewith" else {}
    parser = ArticleText(site, names)
    parser.feed(html_text)
    parser.close()
    available = parser.roots == 1 and parser.closed and bool(parser.lines)
    return {"status": ("partial" if parser.missing_names else "extracted") if available else "unavailable", "site": site,
            "html_sha256": hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
            "reason": None if available else "記事本文領域が一意に閉じた形で見つからないか、本文が空です。",
            "text": "\n".join(parser.lines) if available else "", "image_count": parser.images,
            "unresolved_card_image_ids": sorted(parser.missing_names),
            "scope": "記事本文の最初のh2見出しから関連記事の前までのテキストと画像alt・カード名辞書。目次・広告要素・非表示templateを除外。画像内の文字・動画・動的表示は未確認。"}
