"""探索開始時の記事引継ぎと、失敗時に旧資料を守る境界を検査する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from svdeck import discovery, meta
from test_discovery import make_db
from test_discovery_read import read_all


@pytest.fixture
def db(tmp_path: Path) -> Path:
    # AI_NOTE: 架空カードのDBだけを使い、記事取得は各試験で差し替える。
    path = tmp_path / "cards.db"
    make_db(path)
    return path


def test_cli_articles_use_snapshot_and_preserve_text(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    # AI_NOTE: HTTPだけを固定し、実際の記事解析・全40枚検査・保存・公開読出しを接続する。
    html = """<time datetime="2026-09-10"></time>
    <ol class="wd-decklist"><li card-number="40"><icard data-id="1"></icard></li></ol>
    <script>window.wmt.cardDatas=[{id:'1',n:'核'}];</script>
    <div id="article-body"><h2>運用</h2><p>核を残す。画像内の判断は未確認。</p></div>"""
    urls = ["https://gamewith.jp/shadowverse-wb/1", "https://gamewith.jp/shadowverse-wb/2"]
    fetched: list[str] = []
    snapshots: list[Path] = []
    fetch = meta.article_sources

    def get_html(url: str) -> str:
        # AI_NOTE: URLの取得回数を数え、同じURLが再指定されても通信を繰り返さないことを確認する。
        fetched.append(url)
        return html

    def article(snapshot: Path, url: str, fmt: str, with_text: bool = False) -> dict[str, Any]:
        # AI_NOTE: 取得の照合先が元DBでなく、探索と共通の固定DBであることを実値で確かめる。
        snapshots.append(snapshot)
        assert snapshot != db and snapshot.name == "snapshot.db"
        assert with_text and fmt == "rotation"
        return fetch(snapshot, url, fmt, with_text)

    monkeypatch.setattr(meta, "_get_html", get_html)
    monkeypatch.setattr(meta, "REQUEST_INTERVAL_SEC", 0)
    monkeypatch.setattr(discovery, "article_sources", article)
    before = db.read_bytes()
    dest = tmp_path / "new-parent" / "run"
    assert discovery.main(["start", str(dest), "--db", str(db), "--class", "ウィッチ",
                           "--objective", "構築の別用途", "--article", urls[0],
                           "--article", urls[1], "--article", urls[0]]) == 0
    result = json.loads(capsys.readouterr().out)
    assert fetched == urls and len(set(snapshots)) == 1
    assert result["session"] == str(dest.resolve())
    assert result["articles"] == urls and len(result["source_hashes"]) == 6
    assert db.read_bytes() == before
    assert not list(dest.parent.glob(".run-*"))
    saved = discovery.packet(dest, None, "develop")
    assert saved["sha256"] == result["packet_sha256"]
    assert saved["data"]["instruction"] == discovery.DEVELOP
    known = saved["data"]["context"]["known_decks"]
    assert known and all(deck["name"] == "過去の構築" for deck in known)
    sources = json.loads("".join(read_all(dest, saved["sha256"], "sources", 5)))
    for item in sources:
        item["content"] = "".join(item["content"])
    assert sources == saved["data"]["sources"]
    assert all(item["observed_at"] and item["limitations"] for item in sources)
    text = [json.loads(item["content"]) for item in sources if item["kind"] == "公開記事の説明"]
    assert len(text) == 2 and all("核を残す" in json.dumps(item, ensure_ascii=False) for item in text)
    provenance = [json.loads(item["content"]) for item in sources if item["kind"] == "記事から取得した出典情報"]
    assert all(item["article_updated_on"] == "2026-09-10" for item in provenance)


@pytest.mark.parametrize("error", [OSError("取得不能"), ValueError("不正な構築")])
def test_later_article_failure_leaves_no_session(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception,
) -> None:
    # AI_NOTE: 1件目が成功しても、後続の失敗を古い資料だけの成功へ変えない。
    called: list[str] = []

    def article(snapshot: Path, url: str, fmt: str, with_text: bool = False) -> dict[str, Any]:
        # AI_NOTE: 2番目の取得失敗を再現し、全記事が揃う前に公開されないことを調べる。
        called.append(url)
        if len(called) == 2:
            raise error
        return {"sources": [{"title": "記事", "kind": "説明", "location": url,
                             "observed_at": None, "content": "本文", "limitations": []}]}

    monkeypatch.setattr(discovery, "article_sources", article)
    before = db.read_bytes()
    dest = tmp_path / "run"
    with pytest.raises(type(error), match=str(error)):
        discovery.start(dest, db, "ウィッチ", "rotation", "開始", articles=["one", "two"])
    assert called == ["one", "two"]
    assert not dest.exists() and not list(tmp_path.glob(".run-*"))
    assert db.read_bytes() == before


@pytest.mark.parametrize("payload", [
    {"sources": []}, {"sources": "本文"},
    {"sources": [{"title": "記事", "kind": "説明", "location": "url",
                  "observed_at": None, "content": None, "limitations": []}]},
])
def test_invalid_article_data_is_not_published(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any],
) -> None:
    # AI_NOTE: 取得関数から不正資料が返っても、既存の資料検査を飛ばして保存しない。
    monkeypatch.setattr(discovery, "article_sources", lambda *args, **kwargs: payload)
    with pytest.raises(ValueError):
        discovery.start(tmp_path / "run", db, "ウィッチ", "rotation", "開始", articles=["one"])
    assert sorted(path.name for path in tmp_path.iterdir()) == ["cards.db"]


@pytest.mark.parametrize("during_fetch", [False, True])
def test_existing_destination_is_preserved(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, during_fetch: bool,
) -> None:
    # AI_NOTE: 開始前の既存先と取得中に作られた保存先を、どちらも上書きしない。
    dest = tmp_path / "run"
    called: list[str] = []
    if not during_fetch:
        dest.mkdir()
        (dest / "old.txt").write_text("保持")

    def article(snapshot: Path, url: str, fmt: str, with_text: bool = False) -> dict[str, Any]:
        # AI_NOTE: 別操作が取得中に同じ保存先を確保した状況を再現する。
        called.append(url)
        dest.mkdir()
        (dest / "old.txt").write_text("保持")
        return {"sources": [{"title": "記事", "kind": "説明", "location": url,
                             "observed_at": None, "content": "本文", "limitations": []}]}

    monkeypatch.setattr(discovery, "article_sources", article)
    with pytest.raises((ValueError, FileExistsError)):
        discovery.start(dest, db, "ウィッチ", "rotation", "開始", articles=["one"])
    assert called == (["one"] if during_fetch else [])
    assert (dest / "old.txt").read_text() == "保持"
    assert sorted(path.name for path in dest.iterdir()) == ["old.txt"]
    assert not list(tmp_path.glob(".run-*"))


@pytest.mark.parametrize("articles", [None, []])
def test_unspecified_articles_keep_original_api(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, articles: list[str] | None,
) -> None:
    # AI_NOTE: 記事未指定で通信や初回packetの自動作成を増やさず、従来の戻り値を保つ。
    def forbidden(*args: Any, **kwargs: Any) -> dict[str, Any]:
        # AI_NOTE: 呼ばれないはずの通信を検知する。
        raise AssertionError("記事未指定で取得した")

    monkeypatch.setattr(discovery, "article_sources", forbidden)
    dest = tmp_path / "run"
    result = discovery.start(dest, db, "ウィッチ", "rotation", "開始", articles=articles)
    assert set(result) == {"session", "context_sha256", "eligible_cards", "related_cards", "next"}
    assert not list((dest / "packets").iterdir())
    assert discovery.packet(dest, None, "develop")["data"]["sources"] == []


def test_cli_fetch_failure_has_no_success_output(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    # AI_NOTE: 公開コマンドでも失敗を非ゼロ終了で返し、新設した親以外の未完成資料を残さない。
    def failed(*args: Any, **kwargs: Any) -> dict[str, Any]:
        # AI_NOTE: 通信失敗を固定して、API例外からCLIの失敗応答まで確認する。
        raise OSError("取得不能")

    monkeypatch.setattr(discovery, "article_sources", failed)
    dest = tmp_path / "new-parent" / "run"
    assert discovery.main(["start", str(dest), "--db", str(db), "--class", "ウィッチ",
                           "--objective", "開始", "--article", "https://gamewith.jp/example"]) == 2
    output = capsys.readouterr()
    assert output.out == "" and "取得不能" in output.err
    assert dest.parent.is_dir() and not list(dest.parent.iterdir())


def test_publish_failure_cleans_reserved_destination(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AI_NOTE: 入力が完成した後でも公開に失敗したら、予約した空の保存先を成功風に残さない。
    item: dict[str, Any] = {"title": "記事", "kind": "説明", "location": "url", "observed_at": None,
                            "content": "本文", "limitations": []}
    monkeypatch.setattr(discovery, "article_sources", lambda *args, **kwargs: {"sources": [item]})

    def failed_rename(source: Path, target: Path) -> Path:
        # AI_NOTE: 最後のディレクトリ公開だけを失敗させ、予約と一時領域の後始末を検査する。
        raise OSError("公開失敗")

    monkeypatch.setattr(Path, "rename", failed_rename)
    with pytest.raises(OSError, match="公開失敗"):
        discovery.start(tmp_path / "run", db, "ウィッチ", "rotation", "開始", articles=["one"])
    assert sorted(path.name for path in tmp_path.iterdir()) == ["cards.db"]
