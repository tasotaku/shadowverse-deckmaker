"""長い固定資料の分割読出しと、全文出力との後方互換を検証する。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from svdeck.discovery import packet, review, start, submit
from svdeck.discovery_read import packet_summary, read_packet
from test_discovery import assessment, make_db, proposal


@pytest.fixture
def session(tmp_path: Path) -> Path:
    # AI_NOTE: 既存の往復テストと同じ人工カードを使い、本番DBや実際の探索結果には触れない。
    db = tmp_path / "cards.db"
    make_db(db)
    dest = tmp_path / "reading"
    start(dest, db, "ウィッチ", "rotation", "資料を読み落とさず確認する")
    return dest


def read_all(session: Path, packet_hash: str, section: str, limit: int) -> list[Any]:
    # AI_NOTE: 次の位置だけを頼りに全ページを読み、同じ資料を重複・欠落なく辿れるか確認する。
    result: list[Any] = []
    offset = 0
    while True:
        page = read_packet(session, packet_hash, section, offset, limit)
        assert page["sha256"] == packet_hash
        assert page["offset"] == offset
        assert len(page["content"]) <= limit
        result.extend(page["content"])
        if page["next_offset"] is None:
            assert len(result) == page["total"]
            return result
        assert page["next_offset"] == len(result) > offset
        offset = page["next_offset"]


def test_cli_summary_keeps_original_packet_and_full_output(session: Path) -> None:
    # AI_NOTE: --summary追加後も、標準出力の形と保存される全文の識別値が変わらないことを公開CLIで検査する。
    base = [sys.executable, "-m", "svdeck.discovery", "packet", str(session)]
    full_output = subprocess.run(base, capture_output=True, text=True, check=True).stdout
    full = json.loads(full_output)
    summary_output = subprocess.run(base + ["--summary"], capture_output=True, text=True, check=True).stdout
    summary = json.loads(summary_output)
    assert set(full) == {"sha256", "data"}
    assert summary["sha256"] == full["sha256"]
    assert summary["instruction"] == full["data"]["instruction"]
    assert summary["response_example"] == full["data"]["response_example"]
    assert json.loads(Path(summary["packet_path"]).read_text()) == full
    assert len(summary_output) < len(full_output) / 2
    counts = {part["section"]: part["total"] for part in summary["sections"]}
    assert counts["cards"] == len(full["data"]["context"]["cards"])
    assert counts["rules"] == len(full["data"]["context"]["rules"].splitlines())
    assert counts["proposal"] == counts["previous_reviews"] == 0
    actual = subprocess.run(
        [sys.executable, "-m", "svdeck.discovery", "read", str(session), summary["sha256"],
         "cards", "--offset", "1", "--limit", "2"], capture_output=True, text=True, check=True,
    )
    page = json.loads(actual.stdout)
    assert page["sha256"] == full["sha256"]
    assert page["content"] == full["data"]["context"]["cards"][1:3]
    assert page["next_offset"] == 3


def test_all_sections_reassemble_the_saved_data(session: Path) -> None:
    # AI_NOTE: 本文だけでなく、案・評価・資料の残りの属性まで分割読出しで失わないことを確認する。
    submit(session, proposal(packet(session, 0, "develop")))
    review(session, assessment(packet(session, 1, "review")))
    saved = packet(session, 1, "develop")
    key, data = saved["sha256"], saved["data"]
    context = data["context"]
    for section, expected in {
        "cards": context["cards"], "known_decks": context["known_decks"],
        "search": data["search"], "previous_reviews": data["previous_reviews"],
    }.items():
        assert read_all(session, key, section, 1) == expected
    for section in ("rules", "principles"):
        assert "".join(read_all(session, key, section, 7)) == context[section]
    for section in ("proposal", "response_example"):
        assert json.loads("".join(read_all(session, key, section, 3))) == data[section]
    assert "".join(read_all(session, key, "instruction", 2)) == data["instruction"]
    assert {item["keyword"]: item["text"] for item in read_all(session, key, "keywords", 1)} == context["ability_keywords"]
    assert json.loads("".join(read_all(session, key, "fulfillment_map", 11))) == context["fulfillment_map"]
    meta = json.loads("".join(read_all(session, key, "context_metadata", 3)))
    assert meta == {k: v for k, v in context.items()
                    if k not in {"cards", "rules", "principles", "known_decks", "ability_keywords", "fulfillment_map"}}
    packet_meta = json.loads("".join(read_all(session, key, "packet_metadata", 2)))
    assert packet_meta == {k: v for k, v in data.items()
                           if k not in {"context", "instruction", "response_example", "search", "proposal", "previous_reviews"}}


def test_empty_and_exact_end_pages_report_completion(session: Path) -> None:
    # AI_NOTE: 空区分と末尾の位置を区別しつつ、どちらも次ページが無いことを明示する。
    key = packet(session, 0, "develop")["sha256"]
    empty = read_packet(session, key, "proposal")
    assert empty["total"] == 0 and empty["content"] == [] and empty["next_offset"] is None
    first = read_packet(session, key, "cards")
    end = read_packet(session, key, "cards", first["total"], 1)
    assert end["content"] == [] and end["total"] == first["total"] and end["next_offset"] is None


@pytest.mark.parametrize("offset,limit", [(-1, 1), (0, 0), (0, -1), (999, 1)])
def test_invalid_paging_is_rejected(session: Path, offset: int, limit: int) -> None:
    # AI_NOTE: 位置の指定ミスを空の成功結果で隠さない。
    key = packet(session, 0, "develop")["sha256"]
    with pytest.raises(ValueError, match="offset|limit"):
        read_packet(session, key, "cards", offset, limit)


@pytest.mark.parametrize("bad_hash", ["../context", "g" * 64, "a" * 63, "A" * 64])
def test_invalid_packet_hash_is_rejected(session: Path, bad_hash: str) -> None:
    # AI_NOTE: 資料の識別値以外をファイル名として使わせない。
    with pytest.raises(ValueError, match="packet_hash"):
        read_packet(session, bad_hash, "cards")


def test_unknown_section_and_missing_packet_are_rejected(session: Path) -> None:
    # AI_NOTE: 区分名の誤りと未保存資料の参照を明示的な失敗として返す。
    key = packet(session, 0, "develop")["sha256"]
    with pytest.raises(ValueError, match="未知の区分"):
        read_packet(session, key, "cardz")
    with pytest.raises(FileNotFoundError):
        read_packet(session, "0" * 64, "cards")


def test_reads_stay_on_old_packet_after_new_assessment(session: Path) -> None:
    # AI_NOTE: 別評価追加で新packetの内容が変わっても、指定済みhashの読出しは古い版を保つ。
    submit(session, proposal(packet(session, 0, "develop")))
    before = packet(session, 1, "develop")
    review(session, assessment(packet(session, 1, "review")))
    after = packet(session, 1, "develop")
    assert before["sha256"] != after["sha256"]
    packet_files = {p.name: p.read_bytes() for p in (session / "packets").iterdir()}
    assert read_packet(session, before["sha256"], "previous_reviews")["content"] == []
    assert len(read_packet(session, after["sha256"], "previous_reviews")["content"]) == 1
    assert packet_summary(session, before["sha256"])["sha256"] == before["sha256"]
    assert packet_files == {p.name: p.read_bytes() for p in (session / "packets").iterdir()}


@pytest.mark.parametrize("swap", [False, True])
def test_modified_or_swapped_packet_is_rejected(session: Path, swap: bool) -> None:
    # AI_NOTE: 内容だけの破損も、別の正常な資料を同じファイル名に置く取り違えも拒否する。
    first = packet(session, 0, "develop")
    path = session / "packets" / f"{first['sha256']}.json"
    if swap:
        submit(session, proposal(first))
        replacement = packet(session, 1, "develop")
    else:
        replacement = first
        replacement["data"]["instruction"] = "書き換え"
    path.write_text(json.dumps(replacement, ensure_ascii=False))
    with pytest.raises(ValueError, match="識別値"):
        read_packet(session, first["sha256"], "cards")


@pytest.mark.parametrize("section,extra", [("cards", ["--offset", "-1"]), ("cards", ["--limit", "0"]), ("bad", [])])
def test_cli_read_errors_have_no_traceback(session: Path, section: str, extra: list[str]) -> None:
    # AI_NOTE: 公開CLIでも入力ミスを終了値2と短い説明に揃える。
    key = packet(session, 0, "develop")["sha256"]
    actual = subprocess.run([sys.executable, "-m", "svdeck.discovery", "read", str(session), key, section, *extra],
                             capture_output=True, text=True)
    assert actual.returncode == 2
    assert "探索入力エラー" in actual.stderr
    assert "Traceback" not in actual.stderr
