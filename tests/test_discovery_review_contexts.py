"""各評価の入力資料と現在との差分を、公開入口・保存版の両方で確認する。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from svdeck.discovery import attach, packet, report, review, start, submit
from svdeck.discovery_evidence import digest
from svdeck.discovery_read import packet_summary, read_packet
from test_discovery import assessment, make_db, proposal
from test_discovery_sources import source


@pytest.fixture
def session(tmp_path: Path) -> Path:
    # AI_NOTE: 値判断は人工のまま保存機能だけを試し、実際の探索結果や本番DBを変えない。
    db = tmp_path / "cards.db"
    make_db(db)
    dest = tmp_path / "review-contexts"
    start(dest, db, "ウィッチ", "rotation", "評価に渡した資料を区別する")
    submit(dest, proposal(packet(dest, 0, "develop")))
    return dest


def cli(*args: str) -> dict[str, Any]:
    # AI_NOTE: 内部関数だけでなく利用者が読むJSON出力で対応情報を確かめる。
    result = subprocess.run([sys.executable, "-m", "svdeck.discovery", *args],
                            capture_output=True, text=True, check=True)
    parsed: dict[str, Any] = json.loads(result.stdout)
    return parsed


def test_versions_disagreement_and_questions_remain_visible(session: Path) -> None:
    # AI_NOTE: 同版の不一致と遅れて届く旧版の評価を保持し、資料の追加を問いの自動解決にしない。
    first_hash = attach(session, {"sources": [source()]})["added"][0]
    first = packet(session, 1, "review")
    second_hash = attach(session, {"sources": [{**source(), "content": "追加の観察"}]})["added"][0]
    second = packet(session, 1, "review")
    for saved, author, value, question in [
        (second, "review-a", "develop", "新資料の条件は何か"),
        (second, "review-b", "drop", "別用途の条件は何か"),
        (first, "review-c", "unknown", "最初の条件は何か"),
    ]:
        answer = assessment(saved)
        answer.update(author=author, value=value, next_questions=["隠せるか", question])
        review(session, answer)
    originals = {p: p.read_bytes() for p in session.glob("review-*.json")}
    prior_packets = {p: p.read_bytes() for p in (session / "packets").glob("*.json")}
    result = cli("report", str(session))["revisions"][0]
    contexts = {c["review_hash"]: c for c in result["review_contexts"]}
    assert len(contexts) == len(result["reviews"]) == 3
    for saved_review in result["reviews"]:
        context = contexts[digest(saved_review)]
        is_first = saved_review["packet_hash"] == first["sha256"]
        assert context == {
            "review_hash": digest(saved_review), "input_packet_hash": saved_review["packet_hash"],
            "input_source_hashes": [first_hash] if is_first else sorted([first_hash, second_hash]),
            "additional_source_hashes": [second_hash] if is_first else [],
            "next_questions": saved_review["next_questions"],
        }
    assert {r["value"] for r in result["reviews"] if r["packet_hash"] == second["sha256"]} == {"develop", "drop"}
    full = cli("packet", str(session))
    summary = cli("packet", str(session), "--summary")
    assert full["data"]["previous_reviews"] == result["reviews"]
    assert full["data"]["review_contexts"] == result["review_contexts"]
    assert summary["sha256"] == full["sha256"]
    assert next(p for p in summary["sections"] if p["section"] == "review_contexts") == {
        "section": "review_contexts", "unit": "reviews", "total": 3, "full_packet_path": "data.review_contexts"}
    pages = [cli("read", str(session), full["sha256"], "review_contexts", "--offset", str(n), "--limit", "1")
             for n in range(3)]
    assert [p["content"][0] for p in pages] == result["review_contexts"]
    assert [p["next_offset"] for p in pages] == [1, 2, None]
    assert {q["question"] for q in full["data"]["search"]} == {
        "隠せるか", "新資料の条件は何か", "別用途の条件は何か", "最初の条件は何か"}
    assert len(full["data"]["search"]) == 4
    assert full["data"]["search"][0]["tag_hits"] == [2]
    third_hash = attach(session, {"sources": [{**source(), "content": "さらに追加した観察"}]})["added"][0]
    current = packet(session, 1, "develop")["data"]["review_contexts"]
    assert all(third_hash in c["additional_source_hashes"] for c in current)
    assert read_packet(session, full["sha256"], "review_contexts")["content"] == result["review_contexts"]
    independent = packet(session, 1, "review")["data"]
    assert independent["previous_reviews"] == independent["review_contexts"] == []
    assert "review-c" not in json.dumps(independent)
    assert all(p.read_bytes() == content for p, content in {**originals, **prior_packets}.items())


def test_legacy_review_without_sources_and_contexts_stays_readable(session: Path) -> None:
    # AI_NOTE: 旧保存版の欠落情報は後から合成せず、当時の入力資料0件としてだけ対応させる。
    legacy = packet(session, 1, "review")["data"]
    del legacy["sources"], legacy["source_usage"], legacy["review_contexts"]
    key = digest(legacy)
    path = session / "packets" / f"{key}.json"
    envelope = {"sha256": key, "data": legacy}
    path.write_text(json.dumps(envelope))
    original = path.read_bytes()
    added = attach(session, {"sources": [source()]})["added"]
    review(session, assessment(envelope))
    assert read_packet(session, key, "review_contexts")["content"] == []
    section = next(s for s in packet_summary(session, key)["sections"] if s["section"] == "review_contexts")
    assert section["full_packet_path"] is None and section["total"] == 0
    context = report(session)["revisions"][0]["review_contexts"][0]
    assert context["input_source_hashes"] == [] and context["additional_source_hashes"] == added
    assert packet(session, 1, "develop")["data"]["review_contexts"] == [context]
    assert path.read_bytes() == original


@pytest.mark.parametrize("corruption", [
    "missing", "tampered", "swapped", "invalid_hash", "stage", "revision", "context", "context_body",
    "proposal", "sources_type", "source_changed", "source_missing", "source_duplicate",
])
def test_broken_review_input_fails_without_output_or_new_packet(session: Path, corruption: str) -> None:
    # AI_NOTE: 正常な別資料への差し替えも拒み、参照の不整合を資料0件や空の差分へ読み替えない。
    attach(session, {"sources": [source()]})
    saved = packet(session, 1, "review")
    review(session, assessment(saved))
    path = session / "packets" / f"{saved['sha256']}.json"
    if corruption == "missing":
        path.unlink()
    elif corruption == "tampered":
        saved["data"]["instruction"] = "変更"
        path.write_text(json.dumps(saved))
    elif corruption == "swapped":
        path.write_text(json.dumps(packet(session, 0, "develop")))
    else:
        data = saved["data"]
        if corruption == "stage":
            data["stage"] = "develop"
        elif corruption == "revision":
            data["revision"] = 2
        elif corruption == "context":
            data["context_hash"] = "0" * 64
        elif corruption == "context_body":
            data["context"]["objective"] = "別の探索"
        elif corruption == "proposal":
            data["proposal"]["title"] = "別の案"
        elif corruption == "sources_type":
            data["sources"] = None
        elif corruption == "source_changed":
            data["sources"][0]["content"] = "異なる本文"
        elif corruption == "source_missing":
            (session / "sources" / f"{data['sources'][0]['source_hash']}.json").unlink()
        elif corruption == "source_duplicate":
            data["sources"] *= 2
        key = digest(data)
        (session / "packets" / f"{key}.json").write_text(json.dumps({"sha256": key, "data": data}))
        review_path = next(session.glob("review-*.json"))
        prior = json.loads(review_path.read_text())["data"]
        prior["packet_hash"] = "../context" if corruption == "invalid_hash" else key
        review_path.write_text(json.dumps({"sha256": digest(prior), "data": prior}))
    before = {p: p.read_bytes() for p in (session / "packets").glob("*.json")}
    for command in ("report", "packet"):
        actual = subprocess.run([sys.executable, "-m", "svdeck.discovery", command, str(session)],
                                capture_output=True, text=True)
        assert actual.returncode == 2, actual.stdout
        assert "探索入力エラー" in actual.stderr and "Traceback" not in actual.stderr
        assert actual.stdout == ""
    assert before == {p: p.read_bytes() for p in (session / "packets").glob("*.json")}
