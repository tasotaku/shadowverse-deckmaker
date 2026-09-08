"""保存分析の任意追加が既存資料・固定DB・採用条件を混同しないことを確認する。"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from svdeck.discovery import effects, packet, start
from test_discovery import make_db


def make_effect_session(tmp_path: Path, malformed: bool = False) -> Path:
    # AI_NOTE: 条件付きの分析と訂正済みタグを別保存し、元DBと固定DBの区別を試す。
    db = tmp_path / 'cards.db'
    make_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS card_vschema '
                     '(card_id INTEGER PRIMARY KEY,schema_json TEXT,model TEXT,extracted_at TEXT)')
        conn.execute('INSERT INTO card_atom VALUES (?,?,?,?)',
                     (1, json.dumps({'deltas': [{'zone': '手札', 'delta': 1}],
                                     'atoms': [{'requires': ['破壊時'], 'effect': '生成'}]}), 'saved-model', '2026-07-05'))
        conn.execute('INSERT INTO card_vschema VALUES (?,?,?,?)',
                     (1, json.dumps({'effects': [{'condition': '破壊時', 'kind': '手札生成'}]}), None, None))
        if malformed:
            conn.execute('INSERT INTO card_atom VALUES (?,?,?,?)', (2, '{invalid', None, None))
    session = tmp_path / 'session'
    start(session, db, 'ウィッチ', 'rotation', '保存分析を照合する')
    return session


def test_cli_effects_uses_snapshot_and_preserves_old_packets(tmp_path: Path) -> None:
    # AI_NOTE: 運用元DBを変更しても固定時点の本文・分析を返し、旧入力版に追加を混ぜない。
    session = make_effect_session(tmp_path)
    before = packet(session, 0, 'develop')
    saved = session / 'packets' / f"{before['sha256']}.json"
    old_bytes = saved.read_bytes()
    with sqlite3.connect(tmp_path / 'cards.db') as conn:
        conn.execute("UPDATE card_atom SET atoms_json='{}'")
        conn.execute("UPDATE card SET skill_text='変更後'")
    result = subprocess.run([sys.executable, '-m', 'svdeck.discovery', 'effects', str(session), '1'],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)['added']) == 1
    after = packet(session, 0, 'develop')
    source = after['data']['sources'][0]
    content = json.loads(source['content'])
    assert content['card']['skill_text'] == '『小片』を手札に加える。'
    assert content['card']['note'] == '未登録の別用途'
    assert content['card']['related_card_ids'] == [5]
    assert content['stored_analyses']['card_atom']['value']['atoms'][0]['requires'] == ['破壊時']
    assert content['stored_analyses']['card_atom']['model'] == 'saved-model'
    assert content['stored_analyses']['card_vschema']['value']['effects'][0]['condition'] == '破壊時'
    assert content['stored_analyses']['card_atom']['source_text_version'] == 'unverified'
    assert source['kind'] == 'stored_effect_analysis' and source['limitations']
    assert source['observed_at'] == before['data']['context']['captured_at']
    assert content['snapshot_sha256'] == before['data']['context']['snapshot_sha256']
    assert before['sha256'] != after['sha256']
    assert saved.read_bytes() == old_bytes
    assert after['data']['instruction'] == before['data']['instruction']


def test_duplicate_selection_missing_analysis_and_related_card(tmp_path: Path) -> None:
    # AI_NOTE: 未保存と効果なしを分け、生成専用札を収録しても採用可能へ変えない。
    session = make_effect_session(tmp_path)
    assert len(effects(session, [5, 1, 5])['added']) == 2
    assert effects(session, [1, 5])['added'] == []
    after = packet(session, 0, 'develop')
    records = [json.loads(s['content']) for s in after['data']['sources']]
    related = next(r for r in records if r['card']['card_id'] == 5)
    assert not related['card']['deck_eligible']
    assert related['stored_analyses']['card_atom']['availability'] == 'not_saved'
    assert related['stored_analyses']['card_atom']['value'] is None


@pytest.mark.parametrize('ids', [[], [1, 3], [1, 4], [True], [999]])
def test_invalid_selection_writes_no_sources(tmp_path: Path, ids: list[int]) -> None:
    # AI_NOTE: 対象外クラス・ローテ外・架空IDを一括で拒み、有効な先頭分も残さない。
    session = make_effect_session(tmp_path)
    with pytest.raises(ValueError, match='固定資料'):
        effects(session, ids)
    assert not (session / 'sources').exists()


def test_malformed_analysis_writes_no_partial_sources(tmp_path: Path) -> None:
    # AI_NOTE: 後続札の分析JSONが壊れていても、先頭札だけが追記されることを防ぐ。
    session = make_effect_session(tmp_path, malformed=True)
    with pytest.raises(ValueError):
        effects(session, [1, 2])
    assert not (session / 'sources').exists()


def test_changed_snapshot_is_rejected(tmp_path: Path) -> None:
    # AI_NOTE: 保存分析だけの参照でも、探索用DBと固定本文の版の不一致を拒む。
    session = make_effect_session(tmp_path)
    with sqlite3.connect(session / 'snapshot.db') as conn:
        conn.execute("UPDATE card_atom SET atoms_json='{}'")
    with pytest.raises(ValueError, match='探索用DBが変更'):
        effects(session, [1])
    assert not (session / 'sources').exists()
