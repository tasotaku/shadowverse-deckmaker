"""追加資料の版・引用・保存境界を公開入口と合わせて検証する。"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from svdeck.discovery import attach, packet, report, review, start, submit
from svdeck.discovery_evidence import digest
from svdeck.discovery_read import packet_summary, read_packet
from test_discovery import assessment, make_db, proposal
from test_discovery_read import read_all


@pytest.fixture
def session(tmp_path: Path) -> Path:
    # AI_NOTE: 人工カードで保存の往復だけを検査し、本番DBを変更しない。
    db = tmp_path / "cards.db"
    make_db(db)
    dest = tmp_path / "sources-run"
    start(dest, db, "ウィッチ", "rotation", "比較資料を保持する")
    return dest


def source() -> dict[str, Any]:
    return {"title": "比較時の観察", "kind": "保存した原文", "location": "手元の比較記録",
            "observed_at": None, "content": "開始前に2枚を使った。\n残った手札は3枚。\n",
            "limitations": ["1回の観察"]}


def test_attachment_preserves_old_packet_and_uses_only_its_sources(session: Path) -> None:
    # AI_NOTE: 後で追加した証拠を古い資料への回答へ混ぜず、保存版そのものは使い続けられる。
    old = packet(session, 0, "develop")
    original = (session / "packets" / f"{old['sha256']}.json").read_bytes()
    item = source()
    key = attach(session, {"sources": [item]})["added"][0]
    ref = {"source_hash": key, "quote": "開始前に2枚を使った。"}
    invalid = proposal(old)
    invalid["steps"][0]["evidence"] = [ref]
    with pytest.raises(ValueError, match="資料の引用"):
        submit(session, invalid)
    assert not list(session.glob("revision-*.json"))
    assert json.loads("".join(read_all(session, old["sha256"], "sources", 1))) == []
    assert (session / "packets" / f"{old['sha256']}.json").read_bytes() == original
    submit(session, proposal(old))
    before_review = packet(session, 1, "review")
    changed = {**item, "content": "別の観察結果"}
    attach(session, {"sources": [changed]})
    reviewed = assessment(before_review)
    reviewed["findings"][1]["evidence"] = [ref]
    review(session, reviewed)
    current = packet(session, 1, "develop")
    new = proposal(current)
    new["steps"][0]["evidence"] = [ref]
    submit(session, new)
    result = report(session)
    assert len(result["sources"]) == 2
    assert all("content" not in s for s in result["sources"])
    assert result["revisions"][0]["packet_hash"] == old["sha256"]
    assert result["revisions"][0]["reviews"][0]["packet_hash"] == before_review["sha256"]
    assert result["revisions"][1]["reviews"] == []


def test_duplicate_empty_and_changed_sources(session: Path) -> None:
    # AI_NOTE: 同じ入力は1件、時点や内容が違う観察は別件として保持する。
    item = source()
    key = digest(item)
    assert attach(session, {"sources": []})["total"] == 0
    assert not (session / "sources").exists()
    assert attach(session, {"sources": [item, item]})["added"] == [key]
    original = (session / "sources" / f"{key}.json").read_bytes()
    result = attach(session, {"sources": [item]})
    assert result["added"] == [] and result["existing"] == [key] and result["total"] == 1
    assert (session / "sources" / f"{key}.json").read_bytes() == original
    result = attach(session, {"sources": [{**item, "observed_at": "2026-09-08", "limitations": []}]})
    assert result["total"] == 2
    assert report(session)["revisions"] == []


def test_sources_pages_preserve_long_content_and_metadata(session: Path) -> None:
    # AI_NOTE: 長い1資料も本文の行で小分けにし、全ページから元の本文と属性を復元できる。
    item = {**source(), "content": "\n".join(f"観察 {n}: {n}枚残った。" for n in range(100))}
    attach(session, {"sources": [item]})
    saved = packet(session, 0, "develop")
    key = saved["sha256"]
    summary = packet_summary(session, key)
    assert summary["source_usage"] == saved["data"]["source_usage"]
    assert next(p for p in summary["sections"] if p["section"] == "sources")["total"] > 100
    actual = json.loads("".join(read_all(session, key, "sources", 7)))
    for entry in actual:
        entry["content"] = "".join(entry["content"])
    assert actual == saved["data"]["sources"] == [{"source_hash": digest(item), **item}]


@pytest.mark.parametrize("mutation", [
    {"title": " "}, {"kind": None}, {"location": 0}, {"observed_at": ""},
    {"observed_at": True}, {"content": []}, {"limitations": [""]}, {"limitations": None}, {"extra": "x"},
])
def test_invalid_batch_saves_nothing(session: Path, mutation: dict[str, Any]) -> None:
    # AI_NOTE: 先頭が正しくても後続に不正があれば、追加資料のディレクトリも作らない。
    with pytest.raises(ValueError, match="資料"):
        attach(session, {"sources": [source(), {**source(), **mutation}]})
    assert not (session / "sources").exists()


@pytest.mark.parametrize("payload", [{}, {"sources": {}}, {"sources": [None]}, {"sources": [], "extra": 1}])
def test_missing_or_malformed_source_payload(session: Path, payload: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        attach(session, payload)
    assert not (session / "sources").exists()


@pytest.mark.parametrize("swap", [False, True])
def test_modified_source_is_rejected_without_new_save(session: Path, swap: bool) -> None:
    # AI_NOTE: 本文破損と、別の正常な資料への差し替えの両方を検知する。
    key = attach(session, {"sources": [source()]})["added"][0]
    path = session / "sources" / f"{key}.json"
    envelope = json.loads(path.read_text())
    envelope["data"]["content"] = "書き換え"
    if swap:
        envelope["sha256"] = digest(envelope["data"])
    path.write_text(json.dumps(envelope))
    operations: list[Callable[[], object]] = [lambda: packet(session, 0, "develop"), lambda: report(session),
                                             lambda: attach(session, {"sources": [{**source(), "title": "追加"}]})]
    for operation in operations:
        with pytest.raises(ValueError, match="識別値"):
            operation()
    assert len(list((session / "sources").glob("*.json"))) == 1


def test_attach_requires_an_intact_session(tmp_path: Path, session: Path) -> None:
    with pytest.raises(FileNotFoundError):
        attach(tmp_path / "missing", {"sources": [source()]})
    path = session / "context.json"
    envelope = json.loads(path.read_text())
    envelope["data"]["objective"] = "書き換え"
    path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="識別値"):
        attach(session, {"sources": [source()]})
    assert not (session / "sources").exists()


def test_legacy_packet_without_sources_remains_usable(session: Path) -> None:
    # AI_NOTE: 追加資料機能より前に保存したpacketは、資料0件として読み出し・回答できる。
    legacy = packet(session, 0, "develop")
    del legacy["data"]["sources"]
    del legacy["data"]["source_usage"]
    legacy["sha256"] = digest(legacy["data"])
    (session / "packets" / f"{legacy['sha256']}.json").write_text(json.dumps(legacy))
    attach(session, {"sources": [source()]})
    assert read_packet(session, legacy["sha256"], "sources")["content"] == ["[]"]
    submit(session, proposal(legacy))


@pytest.mark.parametrize("ref", [{"source_hash": "0" * 64, "quote": "開始前に2枚を使った。"},
                                 {"source_hash": "VALID", "quote": "存在しない観察"},
                                 {"source_hash": "VALID", "quote": "比較時の観察"}])
def test_false_source_quote_rejected_for_both_answers(session: Path, ref: dict[str, str]) -> None:
    key = attach(session, {"sources": [source()]})["added"][0]
    citation = {**ref, "source_hash": key if ref["source_hash"] == "VALID" else ref["source_hash"]}
    p = packet(session, 0, "develop")
    invalid = proposal(p)
    invalid["steps"][0]["evidence"] = [citation]
    with pytest.raises(ValueError, match="資料の引用"):
        submit(session, invalid)
    submit(session, proposal(p))
    invalid = assessment(packet(session, 1, "review"))
    invalid["findings"][0]["evidence"] = [citation]
    with pytest.raises(ValueError, match="資料の引用"):
        review(session, invalid)
    assert not list(session.glob("review-*.json"))


def test_public_cli_attach_and_old_packet_round_trip(tmp_path: Path, session: Path) -> None:
    # AI_NOTE: 実際のコマンドから追加、古い資料の回答、新しい資料の引用評価、記録まで通す。
    base = [sys.executable, "-m", "svdeck.discovery"]

    def cli(*args: str) -> dict[str, Any]:
        result = subprocess.run(base + list(args), text=True, capture_output=True, check=True)
        parsed: dict[str, Any] = json.loads(result.stdout)
        return parsed

    old = cli("packet", str(session))
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"sources": [source(), {"title": "不完全"}]}))
    failed = subprocess.run(base + ["attach", str(session), str(path)], text=True, capture_output=True)
    assert failed.returncode == 2 and "Traceback" not in failed.stderr
    assert not (session / "sources").exists()
    path.write_text(json.dumps({"sources": [source()]}))
    key = cli("attach", str(session), str(path))["added"][0]
    assert cli("attach", str(session), str(path))["added"] == []
    assert cli("read", str(session), old["sha256"], "sources")["content"] == ["[]"]
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps(proposal(old)))
    assert cli("submit", str(session), str(answer))["revision"] == 1
    review_packet = cli("packet", str(session), "--stage", "review")
    judged = assessment(review_packet)
    judged["findings"][1]["evidence"] = [{"source_hash": key, "quote": "残った手札は3枚。"}]
    answer.write_text(json.dumps(judged))
    assert cli("review", str(session), str(answer))["value"] == "develop"
    result = cli("report", str(session))
    assert result["sources"][0]["source_hash"] == key
    assert result["revisions"][0]["reviews"][0]["packet_hash"] == review_packet["sha256"]
