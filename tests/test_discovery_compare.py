"""構築の種類純増と、実際の交換枚数を取り違えないことを検査する。"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any

import pytest

from svdeck.db import connect
from svdeck.discovery import attach, compare, start
from svdeck.discovery_sources import load_sources
from test_discovery import assessment, proposal


@pytest.fixture
def db(tmp_path: Path) -> Path:
    # AI_NOTE: 最大3枚までの人工札50種で作り、実際の構築や本番DBには触れない。
    path = tmp_path / "cards.db"
    conn = connect(path)
    for cid in range(1, 51):
        kind = "spell" if cid == 40 or 41 <= cid <= 48 else "follower"
        cost = cid % 5 if cid <= 40 else 5 if cid <= 48 else 6
        conn.execute("INSERT INTO card(card_id,name,cost,type_category,class_name,is_token,"
                     "is_include_rotation,deck_enabled_num,skill_text) VALUES (?,?,?,?,?,0,1,3,?)",
                     (cid, f"保存DBの札{cid}", cost, kind, "ウィッチ", "人工の効果"))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def session(db: Path) -> Path:
    folder = db.parent / "comparison"
    start(folder, db, "ウィッチ", "rotation", "採用配分の変更を確認する")
    return folder


def deck(first: int, last: int) -> list[dict[str, Any]]:
    return [{"card_id": cid, "count": 1} for cid in range(first, last + 1)]


def source(content: object, title: str) -> dict[str, Any]:
    return {"title": title, "kind": "構築の全リスト", "location": "人工の検査資料", "observed_at": None,
            "content": json.dumps(content, ensure_ascii=False), "limitations": ["実デッキではない"]}


def test_type_net_gain_is_not_exchanged_count(session: Path) -> None:
    # AI_NOTE: スペル純増8枚に同種同士の交換2枚が加わるため、交換総数は10枚になる。
    before, after = deck(1, 40), deck(11, 50)
    before[0]["name"] = "原資料に書かれた別名"
    keys = attach(session, {"sources": [source(before, "変更前"), source(after, "変更後")]})["added"]
    result = compare(session, *keys)
    assert result["before"]["total_count"] == result["after"]["total_count"] == 40
    assert result["delta"]["type_net_change"] == {"follower": -8, "spell": 8}
    assert result["delta"]["exchanged_count"] == result["delta"]["added_count"] == result["delta"]["removed_count"] == 10
    assert [row["card_id"] for row in result["delta"]["added"]] == list(range(41, 51))
    assert [row["card_id"] for row in result["delta"]["removed"]] == list(range(1, 11))
    assert result["before"]["cost_counts"] == {str(i): 8 for i in range(5)}
    assert result["after"]["cost_counts"] == {**{str(i): 6 for i in range(5)}, "5": 8, "6": 2}
    first = result["before"]["cards"][0]
    assert first["name"] == "保存DBの札1" and first["recorded_name"] == "原資料に書かれた別名"
    assert all(not row["eligibility_issues"] for row in result["before"]["cards"] + result["after"]["cards"])
    saved = next(row for row in load_sources(session) if row["source_hash"] == result["source_hash"])
    contents = json.loads(saved["content"])
    assert contents["before_source_hash"] == keys[0] and contents["after_source_hash"] == keys[1]
    assert contents["snapshot_sha256"] == result["snapshot_sha256"]
    assert contents["delta"] == result["delta"]
    repeated = compare(session, *keys)
    assert repeated["source_hash"] == result["source_hash"] and repeated["saved_new"] is False
    assert len(load_sources(session)) == 3


def test_identical_decks_and_count_only_changes(session: Path) -> None:
    # AI_NOTE: 同じ札が両側にあっても枚数差を数え、同一構築なら交換を0とする。
    before = deck(1, 40)
    key = attach(session, {"sources": [source(before, "元の構築")]})["added"][0]
    identical = compare(session, key, key)
    assert identical["delta"]["added"] == identical["delta"]["removed"] == []
    assert identical["delta"]["exchanged_count"] == 0
    assert all(value == 0 for value in identical["delta"]["type_net_change"].values())
    after = deck(1, 39)
    after[0]["count"] = 2
    changed_key = attach(session, {"sources": [source(after, "1枚の差し替え")]})["added"][0]
    changed = compare(session, key, changed_key)
    assert changed["delta"]["added"] == [{"card_id": 1, "name": "保存DBの札1", "count": 1}]
    assert changed["delta"]["removed"] == [{"card_id": 40, "name": "保存DBの札40", "count": 1}]
    assert changed["delta"]["exchanged_count"] == 1


@pytest.mark.parametrize("bad", [[], {"follower": 28, "spell": 9, "amulet": 3}, deck(1, 39),
                                  deck(1, 41), [1], [{"card_id": 1}], [{"card_id": 1, "count": 40, "extra": 0}]])
def test_incomplete_or_wrong_shape_saves_no_result(session: Path, bad: object) -> None:
    keys = attach(session, {"sources": [source(deck(1, 40), "変更前"), source(bad, "不正な変更後")]})["added"]
    existing = {path.name: path.read_bytes() for path in (session / "sources").iterdir()}
    with pytest.raises(ValueError):
        compare(session, *keys)
    assert {path.name: path.read_bytes() for path in (session / "sources").iterdir()} == existing


@pytest.mark.parametrize("mutation", [{"card_id": True}, {"card_id": 1.0}, {"card_id": 999}, {"card_id": 2},
                                       {"count": 0}, {"count": -1}, {"count": True}, {"count": 1.0}, {"name": 1}])
def test_invalid_card_entry_saves_no_result(session: Path, mutation: dict[str, Any]) -> None:
    bad = deck(1, 40)
    bad[0].update(mutation)
    keys = attach(session, {"sources": [source(deck(1, 40), "変更前"), source(bad, "不正な変更後")]})["added"]
    with pytest.raises(ValueError):
        compare(session, *keys)
    assert len(load_sources(session)) == 2


def test_non_json_and_unknown_source_are_rejected(session: Path) -> None:
    item = {**source([], "合計だけの記録"), "content": "フォロワー28枚、スペル9枚、アミュレット3枚"}
    keys = attach(session, {"sources": [source(deck(1, 40), "変更前"), item]})["added"]
    with pytest.raises(ValueError, match="JSON配列"):
        compare(session, *keys)
    with pytest.raises(ValueError, match="attach"):
        compare(session, keys[0], "0" * 64)
    assert len(load_sources(session)) == 2


def test_current_legality_does_not_erase_historical_comparison(db: Path) -> None:
    # AI_NOTE: 対象クラス外・旧札・生成札・上限超過も記録し、事実の差分は計算する。
    conn = sqlite3.connect(db)
    conn.execute("UPDATE card SET class_name='ドラゴン' WHERE card_id=1")
    conn.execute("UPDATE card SET is_include_rotation=0 WHERE card_id=2")
    conn.execute("UPDATE card SET is_token=1,deck_enabled_num=0 WHERE card_id=3")
    conn.execute("UPDATE card SET deck_enabled_num=0 WHERE card_id=4")
    conn.commit()
    conn.close()
    session = db.parent / "historical"
    start(session, db, "ウィッチ", "rotation", "昔の構築を比較する")
    keys = attach(session, {"sources": [source(deck(1, 40), "変更前"), source(deck(11, 50), "変更後")]})["added"]
    result = compare(session, *keys)
    cards = {card["card_id"]: card for card in result["before"]["cards"]}
    assert "対象クラス外" in cards[1]["eligibility_issues"]
    assert "保存DBではローテーション対象外" in cards[2]["eligibility_issues"]
    assert "生成専用カード" in cards[3]["eligibility_issues"]
    assert "保存DBの採用上限0枚を超過" in cards[4]["eligibility_issues"]
    assert result["delta"]["exchanged_count"] == 10


def test_changed_snapshot_is_rejected_before_saving(session: Path) -> None:
    keys = attach(session, {"sources": [source(deck(1, 40), "変更前"), source(deck(11, 50), "変更後")]})["added"]
    conn = sqlite3.connect(session / "snapshot.db")
    conn.execute("UPDATE card SET cost=10 WHERE card_id=1")
    conn.commit()
    conn.close()
    with pytest.raises(ValueError, match="DBが変更"):
        compare(session, *keys)
    assert len(load_sources(session)) == 2


def test_public_compare_packet_citation_and_report(tmp_path: Path, session: Path) -> None:
    # AI_NOTE: 公開CLIから計算結果を追加し、次の提案・別評価が引用して記録へ戻るまで通す。
    base = [sys.executable, "-m", "svdeck.discovery"]

    def cli(*args: str) -> dict[str, Any]:
        result = subprocess.run(base + list(args), text=True, capture_output=True, check=True)
        parsed: dict[str, Any] = json.loads(result.stdout)
        return parsed

    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"sources": [source(deck(1, 40), "変更前"), source(deck(11, 50), "変更後")]}))
    keys = cli("attach", str(session), str(path))["added"]
    result = cli("compare", str(session), *keys)
    assert result["delta"]["exchanged_count"] == 10
    assert cli("compare", str(session), *keys)["saved_new"] is False
    saved = cli("packet", str(session))
    answer = proposal(saved)
    citation = {"source_hash": result["source_hash"], "quote": '"exchanged_count": 10'}
    answer["steps"][0]["evidence"] = [citation]
    answer_path = tmp_path / "answer.json"
    answer_path.write_text(json.dumps(answer))
    assert cli("submit", str(session), str(answer_path))["revision"] == 1
    reviewed = assessment(cli("packet", str(session), "--stage", "review"))
    reviewed["findings"][1]["evidence"] = [citation]
    answer_path.write_text(json.dumps(reviewed))
    cli("review", str(session), str(answer_path))
    report = cli("report", str(session))
    assert len(report["sources"]) == 3
    assert report["revisions"][0]["reviews"][0]["findings"][1]["evidence"] == [citation]
    failed = subprocess.run(base + ["compare", str(session), keys[0], "missing"], text=True, capture_output=True)
    assert failed.returncode == 2 and "Traceback" not in failed.stderr
    assert len(load_sources(session)) == 3
