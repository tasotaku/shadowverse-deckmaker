"""元記事の複数レシピ・表示不一致と、更新前の全件検査を検証する。"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from svdeck import meta
from svdeck.db import connect
from svdeck.discovery import packet, start
from test_discovery import make_db

FIXTURES = Path(__file__).parent / "fixtures" / "meta"


@pytest.fixture
def official() -> dict[str, Any]:
    # AI_NOTE: 公式コピー先の読み取り結果から保存したID別枚数を、HTML解析とは独立した期待値にする。
    value: dict[str, Any] = json.loads((FIXTURES / "game8-copy-counts.json").read_text())
    return value


@pytest.fixture
def db(tmp_path: Path, official: dict[str, Any]) -> Path:
    path = tmp_path / "cards.db"
    make_db(path)
    conn = connect(path)
    for recipes in official.values():
        for recipe in recipes:
            for key, name in recipe["card_names"].items():
                conn.execute("INSERT OR IGNORE INTO card(card_id,name) VALUES (?,?)", (int(key), name))
    conn.commit()
    conn.close()
    return path


def mirror(path: Path) -> tuple[list[Any], list[Any]]:
    conn = sqlite3.connect(path)
    try:
        return (conn.execute("SELECT * FROM meta_deck ORDER BY id").fetchall(),
                conn.execute("SELECT * FROM meta_deck_card ORDER BY deck_id,card_name").fetchall())
    finally:
        conn.close()


@pytest.mark.parametrize("code,shown_totals", [("698337", [37]), ("781940", [40, 41])])
def test_actual_recipe_copies_match_official_counts(
    db: Path, official: dict[str, Any], code: str, shown_totals: list[int],
) -> None:
    # AI_NOTE: 表の欠落や過剰を切り詰めず、同じ見出しにあるコピー先の全40枚を照合する。
    recipes = meta.parse_game8_decks((FIXTURES / f"game8-{code}.html").read_text())
    assert [sum(count for _, count in detail.cards) for detail in recipes] == shown_totals
    conn = connect(db)
    mismatches = []
    try:
        for detail, expected in zip(recipes, official[code], strict=True):
            assert detail.anchor == expected["anchor"] and detail.variant == expected["heading"]
            cards = meta._recipe_cards(conn, detail, code)
            assert {str(cid): count for _, count, cid in cards} == expected["card_counts"]
            assert {str(cid): name for name, _, cid in cards} == expected["card_names"]
            link = meta.DeckLink("game8", f"https://game8.jp/shadowverse-beyond/{code}", code, "2", "rotation")
            mismatches.append(meta._recipe_source(link, detail, cards)["display_matches_copy"])
    finally:
        conn.close()
    assert mismatches == ([False] if code == "698337" else [True, False])


def test_single_recipe_api_does_not_merge_or_drop_variants() -> None:
    assert len(meta.parse_game8_deck((FIXTURES / "game8-698337.html").read_text()).cards) == 13
    with pytest.raises(ValueError, match="複数レシピ"):
        meta.parse_game8_deck((FIXTURES / "game8-781940.html").read_text())


def test_recipe_selection_stops_at_next_main_heading() -> None:
    text = (FIXTURES / "game8-698337.html").read_text()
    later = text[text.index('<h3'):text.index('<h2 id="hl_2"')]
    recipes = meta.parse_game8_decks(text + later)
    assert len(recipes) == 1
    with pytest.raises(ValueError, match="主レシピ"):
        meta.parse_game8_decks('<h2 id="hl_1">レシピ</h2><h3 id="hm_1">評価</h3>')


def test_recipe_column_in_tournament_index_is_not_a_main_recipe() -> None:
    # AI_NOTE: 実ページの大会紹介表にも「デッキレシピ」列があるが、主リストの5列見出しとは違う。
    text = (FIXTURES / "game8-698337.html").read_text()
    index = '<h3 id="hm_3">大会上位デッキ</h3><table><tr><th width="25%">日付</th>' \
            '<th width="25%">プレイヤー名</th><th width="50%">デッキレシピ</th></tr></table>'
    text = text.replace('<h2 id="hl_2">', index + '<h2 id="hl_2">')
    assert len(meta.parse_game8_decks(text)) == 1


def test_multiple_recipes_keep_real_heading_links(
    db: Path, monkeypatch: pytest.MonkeyPatch, official: dict[str, Any],
) -> None:
    url = "https://game8.jp/shadowverse-beyond/781940"
    monkeypatch.setattr(meta, "collect_deck_links", lambda: [meta.DeckLink("game8", url, "連携ロイヤル", "2", "rotation")])
    monkeypatch.setattr(meta, "collect_deck_details", lambda link: meta.parse_game8_decks((FIXTURES / "game8-781940.html").read_text()))
    assert meta.main(["--db", str(db)]) == 0
    conn = connect(db)
    try:
        rows = conn.execute("SELECT id,name,url FROM meta_deck ORDER BY id").fetchall()
        assert [row[1:] for row in rows] == [("連携ロイヤル（前寄せデッキリスト）", url + "#hm_1"),
                                           ("連携ロイヤル（後ろ寄せデッキリスト）", url + "#hm_2")]
        for row, expected in zip(rows, official["781940"], strict=True):
            actual = conn.execute("SELECT card_id,count FROM meta_deck_card WHERE deck_id=?", (row[0],)).fetchall()
            assert {str(cid): count for cid, count in actual} == expected["card_counts"]
        provenance = json.loads(conn.execute("SELECT source_json FROM meta_deck WHERE id=2").fetchone()[0])
        assert provenance["article_url"] == url and provenance["heading_id"] == "hm_2"
        assert provenance["copy_url"] == official["781940"][1]["copy_url"]
        assert provenance["display_matches_copy"] is False
        assert provenance["display_copy_difference"]["display_only_or_extra"] == [{"name": "凄烈の剣王・ロードノエル四世", "count": 1}]
    finally:
        conn.close()


@pytest.mark.parametrize("cards", [[], [("核", 37)], [("核", 41)], [("核", 20), ("核", 20)],
                                   [("核", 20), ("核・", 20)], [("核", 40), ("補助", 0)],
                                   [("核", 41), ("補助", -1)], [("核", 39), ("補助", True)],
                                   [("核", 39), ("補助", 1.0)], [("", 40)]])
def test_invalid_deck_leaves_previous_mirror(
    db: Path, monkeypatch: pytest.MonkeyPatch, cards: list[tuple[str, int]], capsys: pytest.CaptureFixture[str],
) -> None:
    # AI_NOTE: 先行する取得が成功しても、後続の不正入力でDELETEに到達しない。
    before = mirror(db)
    links = [meta.DeckLink("gamewith", f"test://{i}", str(i), "1", "rotation") for i in (1, 2)]
    monkeypatch.setattr(meta, "collect_deck_links", lambda: links)
    monkeypatch.setattr(meta, "collect_deck_details",
                        lambda link: [meta.DeckDetail(None, [("核", 40)] if link.name == "1" else cards)])
    assert meta.main(["--db", str(db)]) == 2
    assert mirror(db) == before
    assert "取得中止" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["network", "empty_links", "empty_details", "insert_failure"])
def test_fetch_or_write_failure_leaves_previous_mirror(db: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    # AI_NOTE: ネットワーク失敗、構造変更による0件、書込み失敗でも既存2表を維持する。
    before = mirror(db)
    link = meta.DeckLink("gamewith", "test://same", "test", "1", "rotation")
    links = [] if mode == "empty_links" else [link, link] if mode == "insert_failure" else [link]
    monkeypatch.setattr(meta, "collect_deck_links", lambda: links)

    def detail(_: meta.DeckLink) -> list[meta.DeckDetail]:
        if mode == "network":
            raise OSError("取得失敗の検査")
        return [] if mode == "empty_details" else [meta.DeckDetail(None, [("核", 40)])]

    monkeypatch.setattr(meta, "collect_deck_details", detail)
    assert meta.main(["--db", str(db)]) == 2
    assert mirror(db) == before


def test_one_empty_tier_source_aborts_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(meta, "_get_html", lambda url: "<html>表示形式が変わった</html>")
    with pytest.raises(ValueError, match="Tier表にデッキが見つかりません"):
        meta.collect_deck_links()


def test_gamewith_unresolved_entry_is_not_silently_dropped() -> None:
    text = '<ol class="wd-decklist"><li card-number="40"><icard data-id="1"></icard></li>' \
           '<li card-number="3"><icard data-id="2"></icard></li></ol>window.wmt.cardDatas=[{id:\'1\',n:\'核\'}];'
    with pytest.raises(ValueError, match="カード名辞書"):
        meta.parse_gamewith_deck(text)


@pytest.mark.parametrize("url", ["https://shadowverse-wb.com/ja/deck/detail/?hash=1.4.flAs",
                                 "https://shadowverse-wb.com/ja/deck/detail/",
                                 "https://shadowverse-wb.com/ja/deck/detail/?hash=" + "1.4" + ".0" * 40])
def test_bad_copy_data_is_not_replaced_with_the_display_table(db: Path, url: str) -> None:
    # AI_NOTE: コピー先が解析できない時、表示表へ黙って切り替えて成功扱いしない。
    conn = connect(db)
    try:
        with pytest.raises(ValueError, match="コピー"):
            meta._recipe_cards(conn, meta.DeckDetail(None, [("核", 40)], copy_url=url), "検査")
    finally:
        conn.close()


def test_copy_format_matches_the_tier_label(db: Path) -> None:
    detail = meta.parse_game8_deck((FIXTURES / "game8-698337.html").read_text())
    conn = connect(db)
    try:
        with pytest.raises(ValueError, match="フォーマット"):
            meta._recipe_cards(conn, detail, "検査", "unlimited")
        unlimited = detail._replace(copy_url=detail.copy_url.replace("hash=1.", "hash=2."))
        assert sum(count for _, count, _ in meta._recipe_cards(conn, unlimited, "検査", "unlimited")) == 40
    finally:
        conn.close()


def test_provenance_reaches_discovery_without_reconstruction(db: Path, tmp_path: Path) -> None:
    # AI_NOTE: 来歴を次の探索へそのまま渡し、当時保存していない行はnullのまま区別する。
    source = {"article_url": "test://article", "heading_id": "hm_2", "selected_list": "copy_url",
              "copy_url": "test://copy", "display_total": 40, "selected_total": 40,
              "display_matches_copy": False, "display_copy_difference": {"copy_only_or_extra": [{"name": "核", "count": 1}],
              "display_only_or_extra": [{"name": "旧札", "count": 1}]}}
    conn = connect(db)
    conn.execute("UPDATE meta_deck SET source_json=? WHERE id=1", (json.dumps(source),))
    conn.commit()
    conn.close()
    folder = tmp_path / "run"
    start(folder, db, "ウィッチ", "rotation", "取得対象を確認する")
    known = packet(folder, 0, "develop")["data"]["context"]["known_decks"]
    assert known[0]["source"] == source


def test_legacy_schema_migrates_without_inventing_provenance(db: Path, tmp_path: Path) -> None:
    # AI_NOTE: 旧DBの読取りだけでは移行せず、通常接続で列追加しても元の値を変更しない。
    conn = sqlite3.connect(db)
    conn.execute("ALTER TABLE meta_deck DROP COLUMN source_json")
    before = conn.execute("SELECT * FROM meta_deck ORDER BY id").fetchall()
    conn.commit()
    conn.close()
    folder = tmp_path / "legacy"
    start(folder, db, "ウィッチ", "rotation", "旧資料の来歴を推測しない")
    assert packet(folder, 0, "develop")["data"]["context"]["known_decks"][0]["source"] is None
    conn = sqlite3.connect(db)
    assert "source_json" not in {row[1] for row in conn.execute("PRAGMA table_info(meta_deck)")}
    conn.close()
    conn = connect(db)
    after = conn.execute("SELECT * FROM meta_deck ORDER BY id").fetchall()
    assert [row[:-1] for row in after] == before and all(row[-1] is None for row in after)
    conn.close()
