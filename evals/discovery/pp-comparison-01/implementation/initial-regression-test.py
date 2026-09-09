"""PPの残量と未使用追加分を混ぜず、公開保存まで維持する回帰検査。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any

import pytest

from svdeck.discovery import attach, pp, start
from svdeck.discovery_evidence import digest
from svdeck.discovery_sources import load_sources
from test_discovery import make_db


@pytest.fixture
def session(tmp_path: Path) -> Path:
    # AI_NOTE: 人工DBから新しい探索を作り、本番や自然試行へ書き込まない。
    db = tmp_path / "synthetic.db"
    make_db(db)
    folder = tmp_path / "pp-session"
    start(folder, db, "ウィッチ", "rotation", "宣言したPP算術の試作検査")
    return folder


def plan(actions: list[dict[str, Any]], *, turn: int = 6, amount: int = 6,
         extra: str = "available", side: str = "second", name: str = "検査案") -> dict[str, Any]:
    # AI_NOTE: 期待値は各検査で手計算し、この補助は宣言の組立てだけに使う。
    return {"name": name, "side": side, "start": {"turn": turn, "pp": amount, "extra_pp": extra}, "actions": actions}


def pair(first: dict[str, Any], second: dict[str, Any] | None = None) -> dict[str, Any]:
    # AI_NOTE: 比較相手を省略した検査は同一開始状態の無行動案を使う。
    return {"source_hashes": [], "plans": [first, second or {**first, "name": "比較相手", "actions": []}]}


def files(session: Path) -> dict[str, bytes]:
    # AI_NOTE: 入力拒否で既存探索が一切変わらないことをファイル全体で照合する。
    return {str(path.relative_to(session)): path.read_bytes() for path in session.rglob("*") if path.is_file()}


def test_current_difference_and_total_difference(session: Path) -> None:
    # AI_NOTE: 通常案に残る追加1PPを忘れる元の誤算を固定例で防ぐ。
    payload = pair(plan([{"kind": "use_extra"}, {"kind": "pay", "amount": 5}]),
                   plan([{"kind": "pay", "amount": 6}], name="通常"))
    result = pp(session, payload)
    a, b = result["plans"]
    assert (a["end"]["pp"], b["end"]["pp"]) == (2, 0)
    assert (a["end"]["available_pp"], b["end"]["available_pp"]) == (2, 1)
    assert result["difference"]["current_pp"] == 2
    assert result["difference"]["available_pp"] == 1
    assert a["rows"][0]["before"]["pp"] == 6 and a["rows"][0]["after"]["pp"] == 7
    assert result["input"] == payload and result["input_hash"] == digest(payload)
    assert result["source_count"] == 0 and result["source_hashes_declared"] is True
    assert "資料は0件" in " ".join(result["limitations"])


@pytest.mark.parametrize("extra", ["available", "used", "unknown"])
def test_t6_reset_has_one_use_only(session: Path, extra: str) -> None:
    # AI_NOTE: 前半未使用でも累積せず、使用済み・不明でもT6開始後の権利は一つだけ。
    payload = pair(plan([{"kind": "next_turn", "turn": 6, "pp": 6},
                         {"kind": "use_extra"}, {"kind": "use_extra"}], turn=5, amount=3, extra=extra))
    result = pp(session, payload)["plans"][0]
    assert result["rows"][0]["after"]["pp"] == 6
    assert result["rows"][0]["after"]["extra_pp"] == "available"
    assert result["last_state"]["pp"] == 7 and result["last_state"]["extra_pp"] == "used"
    assert result["status"] == "invalid" and result["end"] is None
    assert result["rows"][2]["after"] is None


def test_early_use_then_late_use_and_late_carry(session: Path) -> None:
    # AI_NOTE: 前半使用→T6再使用と、後半を翌ターンへ温存する別案を比較する。
    result = pp(session, pair(
        plan([{"kind": "use_extra"}, {"kind": "pay", "amount": 6},
              {"kind": "next_turn", "turn": 6, "pp": 6}, {"kind": "use_extra"},
              {"kind": "next_turn", "turn": 7, "pp": 7}], turn=5, amount=5),
        plan([{"kind": "next_turn", "turn": 6, "pp": 6},
              {"kind": "next_turn", "turn": 7, "pp": 7}], turn=5, amount=5)))
    a, b = result["plans"]
    assert (a["end"]["available_pp"], b["end"]["available_pp"]) == (7, 8)
    assert result["difference"]["current_pp"] == 0 and result["difference"]["available_pp"] == -1
    use_late = plan([{"kind": "next_turn", "turn": 7, "pp": 7},
                     {"kind": "use_extra"}, {"kind": "pay", "amount": 8}])
    assert pp(session, pair(use_late))["plans"][0]["end"]["pp"] == 0


@pytest.mark.parametrize("turn,extra,side", [(3, "available", "second"), (5, "used", "second"),
                                            (6, "used", "second"), (5, "unknown", "first")])
def test_no_extra_reset_on_other_boundaries(session: Path, turn: int, extra: str, side: str) -> None:
    # AI_NOTE: T5→T6の後攻だけが更新例外で、それ以外では入力した状態を保持する。
    result = pp(session, pair(plan([{"kind": "next_turn", "turn": turn + 1, "pp": 0}],
                                  turn=turn, amount=20, extra=extra, side=side)))["plans"][0]
    expected = "available" if side == "second" and turn == 5 else extra
    assert result["end"]["extra_pp"] == expected and result["end"]["pp"] == 0
    if side == "first":
        assert result["end"]["unused_extra_range"] == [0, 0]


@pytest.mark.parametrize("extra,amount,status", [("available", 7, "needs_extra"), ("unknown", 7, "unknown"),
                                                ("used", 7, "insufficient"), ("available", 8, "insufficient"),
                                                ("unknown", 8, "insufficient")])
def test_short_payment_stops_before_spending(session: Path, extra: str, amount: int, status: str) -> None:
    # AI_NOTE: 将来のgainや未宣言use_extraを支払いの救済に使わず、不足行で止める。
    result = pp(session, pair(plan([{"kind": "pay", "amount": 1},
                                   {"kind": "pay", "amount": amount}, {"kind": "gain", "amount": 10}],
                                  amount=7, extra=extra)))
    first = result["plans"][0]
    assert first["status"] == status and first["issue"]["shortage"] == amount - 6
    assert first["last_state"]["pp"] == 6 and first["end"] is None
    assert len(first["rows"]) == 2 and first["skipped_actions"] == 1
    assert first["rows"][-1]["after"] is None
    assert result["difference"]["status"] == "not_comparable" and result["difference"]["current_pp"] is None


@pytest.mark.parametrize("extra,side,status", [("unknown", "second", "unknown"), ("used", "second", "invalid"),
                                              ("used", "first", "invalid"), ("unknown", "first", "invalid")])
def test_unknown_and_invalid_extra_use(session: Path, extra: str, side: str, status: str) -> None:
    # AI_NOTE: 不明な権利と不正な使用を区別し、どちらも+1済みとは表示しない。
    result = pp(session, pair(plan([{"kind": "use_extra"}], extra=extra, side=side)))["plans"][0]
    assert result["status"] == status and result["last_state"]["pp"] == 6 and result["end"] is None


@pytest.mark.parametrize("turn", [4, 6, 8])
def test_nonconsecutive_turn_is_saved_as_problem(session: Path, turn: int) -> None:
    # AI_NOTE: 同じ・過去・飛び越しターンはいずれも後続の資源消費を推測できない。
    result = pp(session, pair(plan([{"kind": "next_turn", "turn": turn, "pp": 8},
                                   {"kind": "pay", "amount": 1}])))["plans"][0]
    assert result["status"] == "invalid" and result["last_state"]["turn"] == 6
    assert result["end"] is None and result["skipped_actions"] == 1


def test_unknown_total_is_a_range_not_an_exact_difference(session: Path) -> None:
    # AI_NOTE: 現在値の差が確定しても、未使用分が不明なら込みの差は確定させない。
    result = pp(session, pair(plan([], amount=2, extra="unknown"), plan([], amount=0, extra="available")))
    assert result["difference"]["current_pp"] == 2
    assert result["difference"]["status"] == "unknown_extra"
    assert result["difference"]["available_pp"] is None
    assert result["difference"]["available_pp_range"] == [1, 2]
    both = pp(session, pair(plan([], extra="unknown")))
    assert both["difference"]["available_pp_range"] == [-1, 1]


def test_gain_is_declared_actual_amount_without_a_cap(session: Path) -> None:
    # AI_NOTE: 最大PPや効果本文を入力していないので、gainの上限を勝手に補完しない。
    result = pp(session, pair(plan([{"kind": "pay", "amount": 0}, {"kind": "gain", "amount": 0},
                                   {"kind": "gain", "amount": 11}, {"kind": "pay", "amount": 10}],
                                  amount=0)))["plans"][0]
    assert result["status"] == "completed" and result["end"]["pp"] == 1
    assert result["rows"][2]["after"]["pp"] == 11


@pytest.mark.parametrize("other", [plan([], turn=7), plan([], extra="used", side="first")])
def test_different_endpoints_are_not_compared(session: Path, other: dict[str, Any]) -> None:
    # AI_NOTE: 先後またはターンの違う完了案は別状態なので差を出さない。
    result = pp(session, pair(plan([]), other))
    assert all(item["status"] == "completed" for item in result["plans"])
    assert result["difference"]["status"] == "not_comparable"


@pytest.mark.parametrize("bad", [-1, True, 1.0, "1", None])
@pytest.mark.parametrize("field", ["start.pp", "start.turn", "pay", "gain", "next_turn.pp", "next_turn.turn"])
def test_invalid_numbers_save_nothing(session: Path, field: str, bad: object) -> None:
    # AI_NOTE: Pythonのboolも含め、量とターン番号のすべての入力境界を同じ基準で確認する。
    value = plan([])
    if field.startswith("start."):
        value["start"][field.split(".")[1]] = bad
    elif field.startswith("next_turn."):
        value["actions"] = [{"kind": "next_turn", "turn": 7, "pp": 7, field.split(".")[1]: bad}]
    else:
        value["actions"] = [{"kind": field, "amount": bad}]
    before = files(session)
    with pytest.raises(ValueError):
        pp(session, pair(value))
    assert files(session) == before


@pytest.mark.parametrize("bad", [None, [], {}, {"plans": []}, {"plans": [plan([])]},
                                  {"plans": [plan([])] * 3}, {"plans": [plan([])] * 2, "extra": 1},
                                  pair(plan([], turn=0)), pair(plan([], side="first")),
                                  pair(plan([], side="other")), pair(plan([], extra="other")),
                                  pair(plan([], name=" ")), pair(plan([{"kind": "other"}])),
                                  pair(plan([{"kind": "pay"}])), pair(plan([{"kind": "pay", "amount": 0, "pp": 1}])),
                                  pair(plan([{"kind": "use_extra", "amount": 1}])),
                                  pair(plan([{"kind": "next_turn", "turn": 7}])),
                                  pair(plan([{"kind": "gain", "amount": 1, "label": 1}])),
                                  pair(plan([{"kind": "gain", "amount": 1, "label": ""}])),
                                  pair(plan([1])), pair({**plan([]), "actions": "none"})])
def test_invalid_shape_saves_nothing(session: Path, bad: Any) -> None:
    # AI_NOTE: 計画や行動の誤記を途中まで有効な計算として保存しない。
    before = files(session)
    with pytest.raises(ValueError):
        pp(session, bad)
    assert files(session) == before


def test_input_and_sources_are_preserved_and_repeated_result_is_stable(session: Path) -> None:
    # AI_NOTE: 入力と元資料の意味を自動認定せず、同一内容を照合できる証拠だけ残す。
    source = {"title": "人工の開始状態", "kind": "申告", "location": "検査", "observed_at": None,
              "content": "後攻T6に現在6PP、追加分未使用", "limitations": ["人工データ"]}
    key = attach(session, {"sources": [source]})["added"][0]
    payload = {**pair(plan([{"kind": "pay", "amount": 1, "label": "1PP支払う"}])), "source_hashes": [key]}
    original = copy.deepcopy(payload)
    result = pp(session, payload)
    assert payload == original and result["source_count"] == 1
    saved = next(row for row in load_sources(session) if row["source_hash"] == result["source_hash"])
    data = json.loads(saved["content"])
    assert data["input"] == original and data["input_hash"] == digest(original)
    assert data["source_hashes"] == [key]
    assert data["context_hash"] == json.loads((session / "context.json").read_text())["sha256"]
    repeated = pp(session, payload)
    assert repeated["source_hash"] == result["source_hash"] and repeated["saved_new"] is False
    reordered = pp(session, json.loads(json.dumps(payload, sort_keys=True)))
    assert reordered["source_hash"] == result["source_hash"] and reordered["saved_new"] is False
    payload["plans"][0]["actions"][0]["label"] = "別の説明"
    changed = pp(session, payload)
    assert changed["input_hash"] != result["input_hash"] and changed["source_hash"] != result["source_hash"]
    assert changed["difference"] == result["difference"]
    assert len(load_sources(session)) == 3


def test_omitted_sources_are_explicit_zero_evidence(session: Path) -> None:
    # AI_NOTE: 欄を省略しても資料があることにせず、元入力の省略自体は保持する。
    payload = pair(plan([]))
    declared = pp(session, payload)
    del payload["source_hashes"]
    omitted = pp(session, payload)
    assert omitted["source_hashes"] == [] and omitted["source_count"] == 0
    assert omitted["source_hashes_declared"] is False and "source_hashes" not in omitted["input"]
    assert omitted["input_hash"] != declared["input_hash"]


@pytest.mark.parametrize("keys", ["missing", ["missing"], [""], [True], [None], ["same", "same"]])
def test_bad_source_references_save_nothing(session: Path, keys: object) -> None:
    # AI_NOTE: 資料の識別値をこの探索内で照合し、未知や重複を黙って受け入れない。
    before = files(session)
    with pytest.raises(ValueError):
        pp(session, {**pair(plan([])), "source_hashes": keys})
    assert files(session) == before


@pytest.mark.parametrize("target", ["snapshot", "context", "source"])
def test_tampered_saved_evidence_is_rejected(session: Path, target: str) -> None:
    # AI_NOTE: 保存済み証拠の破損時は、新しい算術結果を作らず既存の整合検査に従う。
    result = pp(session, pair(plan([])))
    if target == "snapshot":
        conn = sqlite3.connect(session / "snapshot.db")
        conn.execute("UPDATE card SET cost=9 WHERE card_id=1")
        conn.commit()
        conn.close()
    else:
        path = session / "context.json" if target == "context" else session / "sources" / f"{result['source_hash']}.json"
        envelope = json.loads(path.read_text())
        envelope["data"]["objective" if target == "context" else "title"] = "改変"
        path.write_text(json.dumps(envelope))
    before = files(session)
    with pytest.raises(ValueError):
        pp(session, pair(plan([])))
    assert files(session) == before


def test_public_pp_packet_read_report_and_errors(tmp_path: Path) -> None:
    # AI_NOTE: 依頼された公開入口と保存版の読出しを、人工DBの新sessionだけで往復する。
    db, session = tmp_path / "synthetic.db", tmp_path / "public-session"
    make_db(db)
    base = [sys.executable, "-m", "svdeck.discovery"]

    def cli(*args: str) -> dict[str, Any]:
        # AI_NOTE: 実プロセスの公開CLI出力を読み、内部関数だけの成功に留めない。
        result = subprocess.run(base + list(args), capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    cli("start", str(session), "--db", str(db), "--class", "ウィッチ", "--objective", "PP公開検査")
    path = tmp_path / "input.json"
    path.write_text(json.dumps(pair(plan([{"kind": "use_extra"}, {"kind": "pay", "amount": 5}]),
                                   plan([{"kind": "pay", "amount": 6}]))))
    result = cli("pp", str(session), str(path))
    assert result["difference"]["available_pp"] == 1
    assert cli("pp", str(session), str(path))["saved_new"] is False
    packet = cli("packet", str(session))
    assert json.loads(packet["data"]["sources"][0]["content"])["input_hash"] == result["input_hash"]
    read = cli("read", str(session), packet["sha256"], "sources", "--limit", "1000")
    decoded = json.loads("".join(read["content"]))
    assert json.loads("".join(decoded[0]["content"]))["difference"] == result["difference"]
    assert cli("report", str(session))["sources"][0]["source_hash"] == result["source_hash"]
    path.write_text(json.dumps(pair(plan([{"kind": "pay", "amount": 7}]))))
    stopped = cli("pp", str(session), str(path))
    assert stopped["plans"][0]["status"] == "needs_extra" and stopped["plans"][0]["end"] is None
    for text in ("{", json.dumps(pair(plan([], side="first")))):
        path.write_text(text)
        before = files(session)
        failed = subprocess.run(base + ["pp", str(session), str(path)], capture_output=True, text=True)
        assert failed.returncode == 2 and "探索入力エラー" in failed.stderr and "Traceback" not in failed.stderr
        assert files(session) == before
