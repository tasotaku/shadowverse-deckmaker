"""枝の改訂履歴と、評価の独立性・古い保存版の互換を検査する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from svdeck.discovery import attach, packet, review, start, submit
from svdeck.discovery_evidence import digest
from test_discovery import assessment, make_db, proposal
from test_discovery_read import read_all


@pytest.fixture
def session(tmp_path: Path) -> Path:
    # AI_NOTE: 人工カードで枝の接続を検査し、カードゲームの価値評価を模倣しない。
    db = tmp_path / "cards.db"
    make_db(db)
    dest = tmp_path / "history"
    start(dest, db, "ウィッチ", "rotation", "実施した変更と調査を別評価へ渡す")
    return dest


def test_history_follows_only_ancestors_without_prior_verdicts(session: Path) -> None:
    # AI_NOTE: 別の枝を途中に作っても、先祖とその時点の検索・出典だけを復元する。
    submit(session, proposal(packet(session, 0, "develop")))
    judged = assessment(packet(session, 1, "review"))
    judged["findings"][1]["reason"] = "過去の採否を推測させる秘密の評価理由"
    review(session, judged)
    keys = attach(session, {"sources": [{"title": "検査記録", "kind": "観察", "location": "手元",
        "observed_at": None, "content": "2枚を使った", "limitations": []}]})["added"]
    input_two = packet(session, 1, "develop")
    second = proposal(input_two)
    second["roles"].append({"card_id": 2, "role": "保護"})
    submit(session, second)
    submit(session, proposal(packet(session, 0, "develop")))
    fourth = proposal(packet(session, 2, "develop"))
    fourth["hypothesis"] = "保護を加えた後の勝ち方を確認する"
    submit(session, fourth)
    current = packet(session, 4, "review")
    history = current["data"]["history"]
    assert [entry["proposal"]["revision"] for entry in history] == [1, 2]
    assert history[0]["input_search"] == []
    assert history[0]["input_source_hashes"] == []
    assert history[1]["input_search"] == input_two["data"]["search"]
    assert history[1]["input_source_hashes"] == keys
    assert current["data"]["previous_reviews"] == []
    assert "秘密の評価理由" not in json.dumps(current, ensure_ascii=False)
    assert json.loads("".join(read_all(session, current["sha256"], "history", 3))) == history
    assert packet(session, 3, "review")["data"]["history"] == []


def test_old_packet_history_stays_fixed_and_legacy_input_works(session: Path) -> None:
    # AI_NOTE: 旧形式には空履歴を返し、後の改訂を過去の資料へ足さない。
    legacy = packet(session, 0, "develop")
    del legacy["data"]["history"]
    legacy["sha256"] = digest(legacy["data"])
    path = session / "packets" / f"{legacy['sha256']}.json"
    path.write_text(json.dumps(legacy))
    submit(session, proposal(legacy))
    old = packet(session, 1, "review")
    second = proposal(packet(session, 1, "develop"))
    second["uncertainties"].append("新しく見つかった条件")
    submit(session, second)
    assert len(packet(session, 2, "review")["data"]["history"]) == 1
    assert json.loads("".join(read_all(session, old["sha256"], "history", 1))) == []
    assert json.loads("".join(read_all(session, legacy["sha256"], "history", 1))) == []


@pytest.mark.parametrize("parent", [-1, 1, True, "0"])
def test_invalid_parent_in_saved_revision_is_rejected(session: Path, parent: object) -> None:
    # AI_NOTE: 破損した親番号から循環・別ファイル参照を始めない。
    submit(session, proposal(packet(session, 0, "develop")))
    path = session / "revision-0001.json"
    saved = json.loads(path.read_text())
    saved["data"]["parent_revision"] = parent
    saved["sha256"] = digest(saved["data"])
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="先祖案の番号"):
        packet(session, 1, "review")


def test_swapped_ancestor_packet_is_rejected(session: Path) -> None:
    # AI_NOTE: 内容の識別値が正常な別packetへの差し替えも履歴の根拠として使わない。
    original = packet(session, 0, "develop")
    submit(session, proposal(original))
    next_input = packet(session, 1, "develop")
    revised = proposal(next_input)
    revised["uncertainties"].append("後続条件")
    submit(session, revised)
    path = session / "packets" / f"{original['sha256']}.json"
    path.write_text(json.dumps(next_input))
    with pytest.raises(ValueError, match="先祖案と当時の資料"):
        packet(session, 2, "review")
