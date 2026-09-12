"""固定版と実際の保存入力を比較する、隔離実験用の境界検査。"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from svdeck import discovery
from svdeck.discovery_read import packet_summary
from test_discovery import assessment, proposal, session
from test_discovery_sources import source

BASE = "ec1dea5fdb45cc1f8fa2d34c5367f6e3f9cf4ad5"


@pytest.fixture
def baseline() -> ModuleType:
    code = subprocess.check_output(["git", "show", f"{BASE}:src/svdeck/discovery.py"], text=True)
    module = ModuleType("resource_use_baseline")
    module.__file__ = discovery.__file__
    exec(compile(code, str(discovery.__file__), "exec"), module.__dict__)
    return module


@pytest.mark.parametrize("revision,stage,finish,changed", [
    (0, "develop", False, False),
    (1, "develop", False, True),
    (None, "develop", False, True),
    (1, "review", False, False),
    (None, "review", False, False),
    (0, "develop", True, False),
    (1, "develop", True, False),
    (None, "develop", True, False),
])
def test_fixed_base_packet_boundary(session: Path, baseline: ModuleType,
                                    revision: int | None, stage: str,
                                    finish: bool, changed: bool) -> None:
    # AI_NOTE: 実際の提出・別評価・追加資料を持つ保存先で、指示以外の資料と初回枝の保持を照合する。
    initial = baseline.packet(session, 0, "develop")
    discovery.submit(session, proposal(initial))
    discovery.review(session, assessment(baseline.packet(session, 1, "review")))
    key = discovery.attach(session, {"sources": [source()]})["added"][0]
    reference = baseline.packet(session, revision, stage, key if finish else None)
    actual = discovery.packet(session, revision, stage, key if finish else None)
    before = dict(reference["data"])
    after = dict(actual["data"])
    expected_instruction = before.pop("instruction")
    actual_instruction = after.pop("instruction")
    assert after == before
    if changed:
        assert actual_instruction == expected_instruction + "\n" + discovery.RESOURCE_USE
        assert actual["sha256"] != reference["sha256"]
    else:
        assert actual == reference
    assert packet_summary(session, actual["sha256"])["instruction"] == actual_instruction
    assert json.loads((session / "packets" / f"{actual['sha256']}.json").read_text()) == actual
    public = subprocess.run([sys.executable, "-m", "svdeck.discovery", "read", str(session),
                             actual["sha256"], "instruction", "--limit", "100"],
                            text=True, capture_output=True, check=True)
    page = json.loads(public.stdout)
    assert page["next_offset"] is None
    assert "".join(page["content"]) == actual_instruction


def test_empty_latest_and_rejected_targets(session: Path, baseline: ModuleType) -> None:
    # AI_NOTE: 最新案が無い時と無効な工程は、既存の開始指示・拒否境界を保つ。
    assert discovery.packet(session, None, "develop") == baseline.packet(session, None, "develop")
    cases: list[tuple[int, str, str | None, type[Exception]]] = [
        (0, "review", None, ValueError), (1, "develop", None, FileNotFoundError),
        (0, "other", None, ValueError), (0, "develop", "missing", ValueError)]
    for revision, stage, finish, error in cases:
        with pytest.raises(error) as previous:
            baseline.packet(session, revision, stage, finish)
        with pytest.raises(error) as current:
            discovery.packet(session, revision, stage, finish)
        assert str(current.value) == str(previous.value)
