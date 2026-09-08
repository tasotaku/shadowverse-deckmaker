"""探索結果の証拠範囲を、実カードに依存しない人工データで検証する。"""

import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from svdeck.bench import CategoryLookup, MeasuredRates, load_fulfillment_map, parse_tag  # noqa: E402
from svdeck.db import _SCHEMA, connect  # noqa: E402
from svdeck.explore import (  # noqa: E402
    ArithmeticResult,
    Candidate,
    RequireRow,
    RequirementReport,
    check_novelty,
    compute_arithmetic,
    find_closures,
    format_arithmetic,
    format_closures,
    format_report,
    format_scan_pack,
    tag_search,
)


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    # AI_NOTE: DBはメモリ内だけに作り、人工カードの組を実カードの発見として扱わない。
    connection = sqlite3.connect(":memory:")
    connection.executescript(_SCHEMA)
    connection.executemany(
        "INSERT INTO card(card_id,name,class_name,type_category,cost,is_token,is_include_rotation) "
        "VALUES(?, ?, ?, 'spell', 20, 0, 1)",
        [(1, "人工アンカー", "ニュートラル"), (2, "人工供給A", "ウィッチ"), (3, "人工供給B", "ロイヤル")],
    )
    yield connection
    connection.close()


def report(
    index: int, candidates: list[int], *, active: bool = True, arithmetic: ArithmeticResult | None = None
) -> RequirementReport:
    # AI_NOTE: 候補の有無と数量概算を独立に設定し、数量不足が型一致の候補を消さないことも検証する。
    require = RequireRow(index, "accumulate" if arithmetic else "event", "人工要求", "ネクロマンス(1)",
                         1, "active" if active else "dead", None)
    return RequirementReport(require, [Candidate(cid, f"人工供給{cid}", 20, "人工タグ") for cid in candidates],
                             False, arithmetic)


@pytest.mark.parametrize("candidate_lists", [[[2], []], [[], [2]], [[], []]])
def test_unmatched_active_requirement_prevents_complete_set(
    conn: sqlite3.Connection, candidate_lists: list[list[int]]
) -> None:
    # AI_NOTE: 以前は候補ゼロの要求を除き、片方だけ合う集合を返していた失敗を固定する。
    reports = [report(i, candidates) for i, candidates in enumerate(candidate_lists)]
    closures = find_closures(conn, reports, CategoryLookup(conn))
    assert closures == []
    rendered = format_closures(reports, closures)
    assert "未充足" in rendered
    assert "全要求を覆う集合は出しません" in rendered
    assert "対象外" not in rendered


def test_shared_candidate_covers_all_active_requirements(conn: sqlite3.Connection) -> None:
    # AI_NOTE: 1枚で両方に型が合う正常系を保持し、不要な上位集合を出さないことも確認する。
    reports = [report(1, [2]), report(2, [2, 3])]
    closures = find_closures(conn, reports, CategoryLookup(conn))
    assert [item.card_ids for item in closures] == [(2,)]
    assert closures[0].covered_require_indices == frozenset({0, 1})
    assert "手順成立は未検証" in format_closures(reports, closures)


def test_dead_requirement_does_not_block_active_set(conn: sqlite3.Connection) -> None:
    # AI_NOTE: 見送り済みの要求だけは集合の必須条件に戻さない。
    closures = find_closures(conn, [report(1, [2]), report(2, [], active=False)], CategoryLookup(conn))
    assert [item.card_ids for item in closures] == [(2,)]


@pytest.mark.parametrize("reports", [[], [report(1, [], active=False)]])
def test_no_active_requirements_produces_no_set(
    conn: sqlite3.Connection, reports: list[RequirementReport]
) -> None:
    # AI_NOTE: active要求がない状態を、全条件成立の空集合として昇格させない。
    assert find_closures(conn, reports, CategoryLookup(conn)) == []
    assert "active要求なし" in format_closures(reports, [])


def test_cross_class_set_is_not_returned(conn: sqlite3.Connection) -> None:
    # AI_NOTE: ニュートラルを起点にしても異なるクラスの2枚を混ぜた集合は返さない。
    reports = [report(1, [2]), report(2, [3])]
    assert find_closures(conn, reports, CategoryLookup(conn)) == []


@pytest.mark.parametrize("threshold, reached", [(1, True), (100, False)])
def test_quantity_estimate_does_not_claim_pp_feasibility_or_reject_candidates(
    conn: sqlite3.Connection, threshold: int, reached: bool
) -> None:
    # AI_NOTE: T1に20PP必要な札でも数量比較はできるが、旧PP収支PASSや不足による棄却は許さない。
    lookup = CategoryLookup(conn)
    arithmetic = compute_arithmetic(
        conn, parse_tag("ネクロマンス(1)"), threshold, 1, [Candidate(2, "人工供給A", 20, "人工タグ")],
        MeasuredRates({"graveyard": 0.0}, {"graveyard": 0.0}), load_fulfillment_map(), lookup,
    )
    assert arithmetic is not None
    assert arithmetic.quantity_reached is reached
    assert arithmetic.topup_schedule[0].pp_spent > arithmetic.cum_pp
    reports = [report(1, [2], arithmetic=arithmetic)]
    closures = find_closures(conn, reports, lookup)
    assert len(closures) == 1
    rendered = "\n".join(format_arithmetic(arithmetic)) + format_closures(reports, closures)
    assert "PASS" not in rendered
    assert "FAIL" not in rendered
    assert "数量概算" in rendered
    for limitation in ("PP総支出", "PPの重複", "各ターンの使用順", "数量の上限", "不足だけで候補を棄却しません"):
        assert limitation in rendered


def test_unknown_counter_has_no_quantity_estimate(conn: sqlite3.Connection) -> None:
    # AI_NOTE: 対応していない量を既知の計数へ読み替えず、未算出として残す。
    assert compute_arithmetic(conn, parse_tag("未知の計数(3)"), 3, 1, [], None,
                              load_fulfillment_map(), CategoryLookup(conn)) is None


def test_novelty_only_uses_selected_format(conn: sqlite3.Connection) -> None:
    # AI_NOTE: 同じペアのローテ・アンリミ・形式不明を混ぜ、指定形式の根拠だけが残ることを検証する。
    for deck_id, format_name in enumerate(["rotation", "unlimited", None], start=1):
        conn.execute("INSERT INTO meta_deck(id,name,tier,format) VALUES(?, ?, '3', ?)",
                     (deck_id, f"人工デッキ{deck_id}", format_name))
        conn.executemany("INSERT INTO meta_deck_card(deck_id,card_id,count) VALUES(?, ?, 1)",
                         [(deck_id, 1), (deck_id, 2)])
    assert [h.deck_name for h in check_novelty(conn, 1, 2, "rotation")] == ["人工デッキ1"]
    assert [h.deck_name for h in check_novelty(conn, 1, 2, "unlimited")] == ["人工デッキ2"]
    assert check_novelty(conn, 1, 3, "rotation") == []


def test_candidate_and_requirement_feedback_are_returned(conn: sqlite3.Connection) -> None:
    # AI_NOTE: 両側のカード注記と要求固有の注記を検索結果からLLM用出力まで追跡する。
    conn.execute("INSERT INTO atom_tag(card_id,kind,tag) VALUES(2, 'supply', '墓場+(1)')")
    conn.execute("INSERT INTO card_note(card_id,note) VALUES(2, '供給側の過去の見送り理由')")
    hits = tag_search(conn, parse_tag("ネクロマンス(1)"), load_fulfillment_map(), CategoryLookup(conn),
                      "ニュートラル", "rotation", 1)
    assert len(hits) == 1
    assert hits[0].note == "供給側の過去の見送り理由"
    requirement = RequireRow(1, "accumulate", "人工要求", "ネクロマンス(1)", 1, "active", "要求固有の見送り理由")
    reports = [RequirementReport(requirement, hits, False, None)]
    rendered = format_report(1, "人工アンカー", "ニュートラル", "アンカー注記", reports)
    for note in ("アンカー注記", "供給側の過去の見送り理由", "要求固有の見送り理由"):
        assert note in rendered
    assert "要求固有の見送り理由" in format_scan_pack(1, "ニュートラル", reports)


@pytest.mark.parametrize("invalid_format", [False, True])
def test_public_module_cli_uses_artificial_db(tmp_path: Path, invalid_format: bool) -> None:
    # AI_NOTE: コピーしたパッケージと人工DBでpython -mを実行し、公開入口の配線と不正形式を確かめる。
    shutil.copytree(REPO_ROOT / "src" / "svdeck", tmp_path / "src" / "svdeck",
                    ignore=shutil.ignore_patterns("__pycache__"))
    connection = connect(tmp_path / "data" / "cards.db")
    try:
        connection.executemany(
            "INSERT INTO card(card_id,name,class_name,type_category,cost,is_token,is_include_rotation) "
            "VALUES(?, ?, 'ニュートラル', 'spell', 20, 0, 1)", [(1, "人工アンカー"), (2, "人工供給")],
        )
        connection.execute("INSERT INTO card_tag(card_id,tag) VALUES(1,'anchor')")
        connection.execute("INSERT INTO atom_tag(card_id,kind,tag) VALUES(2,'supply','墓場+(1)')")
        connection.executemany("INSERT INTO card_note(card_id,note) VALUES(?,?)", [(1, "主役注記"), (2, "供給注記")])
        connection.execute(
            "INSERT INTO anchor_require(card_id,req_type,requirement,req_tag,deadline_turn,source,note) "
            "VALUES(1,'accumulate','人工要求','ネクロマンス(100)',1,'fixture','要求注記')"
        )
        connection.execute("INSERT INTO meta_deck(id,name,format) VALUES(1,'アンリミ専用の人工デッキ','unlimited')")
        connection.executemany("INSERT INTO meta_deck_card(deck_id,card_id,count) VALUES(1,?,1)", [(1,), (2,)])
        connection.commit()
    finally:
        connection.close()
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "svdeck.explore", "1", "--format", "typo" if invalid_format else "rotation"],
        cwd=tmp_path, env=env, check=False, capture_output=True, text=True,
    )
    if invalid_format:
        assert result.returncode == 1
        assert "usage:" in result.stdout
        assert "Traceback" not in result.stderr
        return
    assert result.returncode == 0, result.stderr
    for expected in ("主役注記", "供給注記", "要求注記", "手順成立は未検証", "数量概算は未達", "既出照合(rotation)", "meta_deck共起なし"):
        assert expected in result.stdout
    assert "アンリミ専用の人工デッキ" not in result.stdout
    assert "PASS" not in result.stdout
    assert "FAIL" not in result.stdout
