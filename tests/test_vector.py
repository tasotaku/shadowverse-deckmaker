"""vector.py(B3=効果スキーマの集計)のテスト。

純粋関数(classify/_overlay/_hits/_xnum)はDBなしで検証し、evaluate_cardの結合テストは
card_vschemaの保存済みカード(ドラクラ/サンダルフォン/オルトロス)で検算する。
worktreeのdata/cards.dbは空(gitignore)なので、結合テストはデータ欠落時にskipする。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from svdeck.db import connect  # noqa: E402
from svdeck.strength import load_token_stats  # noqa: E402
from svdeck.vector import _hits, _overlay, _xnum, classify, evaluate_card  # noqa: E402

# AI_NOTE: 検算対象(ユーザー指定): ドラクラ=変化2→4 / サンダルフォン=登場モード / オルトロス=繰り返し×N
# 追加(2026-07-15): 花園の導き=リソースの変化+融合素材 / 繚乱の庭=トークン別軸 / クオン=体リスト
DRAGONEWT_CRUSH = 10041310
SANDALPHON = 10404110
ORTHROS = 10153120
HANAZONO = 10213310
RYOURAN = 10011210
KUON = 10134110


def test_classify_priority_and_residual() -> None:
    # 超進化>進化>エンハンス>登場の順で拾い、モードトリガとFFを除いた残りが天井条件になる
    assert classify(["超進化時"]) == ("sevo", [])
    assert classify(["進化時", "ネクロマンス4"]) == ("evo", ["ネクロマンス4"])
    assert classify(["エンハンス10"]) == (("enh", 10), [])  # 括弧なし表記も拾う
    assert classify(["直接召喚された時"]) == ("entry", [])
    assert classify(["ファンファーレ"]) == ("base", [])
    assert classify(["ファンファーレ", "解放奥義"]) == ("base", ["解放奥義"])


def test_xnum_keeps_x_as_condition() -> None:
    # X型("X:…")は数値にせず条件へ(§11.10)
    assert _xnum(3) == (3, None)
    assert _xnum("X:スペルブーストで増やしたカウント") == (0, "X:スペルブーストで増やしたカウント")


def test_hits_multiplies_repeat() -> None:
    # 範囲ランダム1×繰り返し5=命中5(サンダルフォン型)。全体/割り振りは記号のまま
    assert _hits({"範囲": {"型": "ランダム", "数": 1}, "繰り返し": 5}) == (5, [])
    assert _hits({"範囲": {"型": "全体"}}) == ("全体", [])
    assert _hits({"範囲": {"型": "割り振り", "総量": 6}}) == ("割振", [])


def test_overlay_merges_only_written_fields() -> None:
    # 変化=書かれたフィールドだけ差し替え・効果はキー単位マージ・条件は合流(ドラクラ2→4)
    base = {"対象": ["相手フォロワー"], "範囲": {"型": "選択", "数": 1}, "効果": {"ダメージ": 2}}
    changed, conds = _overlay(base, {"条件": ["覚醒"], "効果": {"ダメージ": 4}})
    assert changed["効果"] == {"ダメージ": 4}
    assert changed["範囲"] == {"型": "選択", "数": 1}
    assert conds == ["覚醒"]


def _db_has_vschema() -> bool:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='card_vschema'"
        ).fetchone()
        return bool(row[0]) and conn.execute("SELECT count(*) FROM card_vschema").fetchone()[0] > 0
    finally:
        conn.close()


needs_db = pytest.mark.skipif(not _db_has_vschema(), reason="card_vschema未取り込み(worktreeのDBは空)")


@needs_db
def test_dragonewt_crush_removal_span() -> None:
    # 変化(覚醒)が除去を2→4の幅1エントリに畳み(加算しない)、天井ターンが覚醒=7に開く
    conn = connect()
    try:
        _, modes = evaluate_card(conn, DRAGONEWT_CRUSH, load_token_stats(conn))
    finally:
        conn.close()
    (mode,) = modes
    (removal,) = mode.removals
    assert (removal.kill, removal.kill_max, removal.conds) == (2, 4, ["覚醒"])
    assert (mode.turn_floor, mode.turn_ceiling) == (1, 7)


@needs_db
def test_sandalphon_entry_mode_and_repeat() -> None:
    # 登場(直接召喚)=コスト0・手札-1なし・自身バウンスで手札+1。素モードは繰り返し5が
    # リーダーダメージ天井10と除去到達5に効く
    conn = connect()
    try:
        _, modes = evaluate_card(conn, SANDALPHON, load_token_stats(conn))
    finally:
        conn.close()
    by_label = {m.label: m for m in modes}
    entry = by_label["登場"]
    assert entry.cost == 0
    assert entry.floor.get("カード枚数", 0) == 1  # 手札を使わず、戻って手札+1
    assert "このバトル中に自分のフォロワーが進化した回数が6以上" in entry.conds
    base = by_label["素"]
    assert base.floor.get("リーダーダメージ", 0) == 0
    assert base.ceiling["リーダーダメージ"] == 10  # 2ダメージ×5回の全弾顔想定
    (removal,) = base.removals
    assert (removal.kill, removal.reach) == (2, 5)


@needs_db
def test_hanazono_resource_henka_and_fusion_material() -> None:
    # リソースの変化=置き換え(1枚→2枚・加算しない)＋融合素材の手札-1が天井に効き、収支は0→0
    conn = connect()
    try:
        _, modes = evaluate_card(conn, HANAZONO, load_token_stats(conn))
    finally:
        conn.close()
    (mode,) = modes
    assert mode.floor["カード枚数"] == 0  # プレイ-1+ドロー1
    assert mode.ceiling["カード枚数"] == 0  # プレイ-1+2枚(置き換え)-融合素材1
    assert "融合" in mode.conds


@needs_db
def test_ryouran_token_axis_is_separate() -> None:
    # 生成=トークンは実カード(カード枚数)と混ぜず別軸に載る
    conn = connect()
    try:
        _, modes = evaluate_card(conn, RYOURAN, load_token_stats(conn))
    finally:
        conn.close()
    (mode,) = modes
    assert mode.floor["カード枚数"] == -1  # プレイ消費のみ(トークンで相殺しない)
    assert mode.floor["トークン生成"] == 1
    assert "生成:フェアリー" in mode.supplies


@needs_db
def test_kuon_bodies_keep_shape() -> None:
    # 盤面の形は体リストで保持(合計12/12だけでは分布が消える)
    conn = connect()
    try:
        _, modes = evaluate_card(conn, KUON, load_token_stats(conn))
    finally:
        conn.close()
    base = {m.label: m for m in modes}["素"]
    assert [(b.name, b.atk, b.life) for b in base.bodies] == [
        ("自身", 3, 3), ("式神・天后", 4, 5), ("式神・暴鬼", 3, 3), ("式神・形代", 2, 1)
    ]
    assert (base.body_count, base.max_body) == (4, 9)


@needs_db
def test_orthros_repeat_in_evo_mode() -> None:
    # 進化時+ネクロマンス4の繰り返し2=進化モードの条件付き除去(殺傷2×到達2)
    conn = connect()
    try:
        _, modes = evaluate_card(conn, ORTHROS, load_token_stats(conn))
    finally:
        conn.close()
    evo = {m.label: m for m in modes}["進化"]
    (removal,) = evo.removals
    assert (removal.kill, removal.reach, removal.conds) == (2, 2, ["ネクロマンス4"])
    assert evo.turn_floor == 5  # 進化=先攻T5
