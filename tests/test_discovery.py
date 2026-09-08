"""公開入口の往復と、固定資料・合法性・評価境界の回帰テスト。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any

import pytest

from svdeck.db import connect
from svdeck.discovery import packet, report, review, start, submit
from svdeck.discovery_evidence import digest


def make_db(path: Path) -> None:
    conn = connect(path)
    cards = [
        (1, '核', 'ウィッチ', 1, 0, 1, '『小片』を手札に加える。', None, '未登録の別用途'),
        (2, '補助', 'ウィッチ', 1, 0, 1, '味方に潜伏を与える。', None, '効果では進化時を誘発しない'),
        (3, '敵クラス', 'ドラゴン', 1, 0, 1, '効果', None, ''),
        (4, '旧札', 'ウィッチ', 1, 0, 0, '効果', None, ''),
        (5, '小片', 'ウィッチ', 0, 1, 1, '『欠片』を手札に加える。', None, ''),
        (6, '欠片', 'ウィッチ', 0, 1, 1, '1ダメージ。', '参照先で2ダメージ。', ''),
    ]
    for cid, name, cls, cost, token, rot, text, ref, note in cards:
        conn.execute('''INSERT INTO card(card_id,name,class_name,cost,is_token,is_include_rotation,
                     deck_enabled_num,skill_text,evo_json,ref_effect_text,type_category)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                     (cid, name, cls, cost, token, rot, 0 if token else 3, text,
                      json.dumps({'skill_text': '進化後の追加効果'}), ref, 'follower'))
        conn.execute('INSERT INTO card_note VALUES (?,?,?)', (cid, note, '2026-09-08'))
    conn.execute("INSERT INTO atom_tag VALUES (2,'supply','潜伏付与')")
    conn.execute("INSERT INTO anchor_require(card_id,req_type,requirement,req_tag,source,note) "
                 "VALUES (2,'event','進化権','進化権','test','供給側の条件')")
    conn.commit()
    conn.close()


@pytest.fixture
def session(tmp_path: Path) -> Path:
    db = tmp_path / 'cards.db'
    make_db(db)
    folder = tmp_path / 'run'
    start(folder, db, 'ウィッチ', 'rotation', '未登録札の別用途を調べる')
    return folder


def proposal(p: dict[str, Any]) -> dict[str, Any]:
    return {'packet_hash': p['sha256'], 'parent_revision': p['data']['revision'], 'author': 'builder',
            'title': '別用途の途中案', 'hypothesis': '生成した札を別の役割へ回す', 'change': '初回',
            'roles': [{'card_id': 1, 'role': '供給'}],
            'steps': [{'action': '核を使う', 'resources': 'PP1→0、手札から1枚使用、生成1枚',
                       'result': '小片が手札へ', 'evidence': [{'card_id': 1, 'field': 'skill_text',
                                                           'quote': '『小片』を手札に加える。'}]}],
            'plan': {}, 'questions': [{'question': '隠せるか', 'tag': '潜伏付与', 'why': '生存条件を変える'}],
            'uncertainties': ['次の勝ち方が未確認']}


def assessment(p: dict[str, Any]) -> dict[str, Any]:
    return {'packet_hash': p['sha256'], 'author': 'independent', 'procedure': 'conditional',
            'value': 'develop', 'novelty': 'unconfirmed', 'findings': [
                {'axis': a, 'reason': '起動条件と比較価値を確認する必要がある', 'evidence': []}
                for a in ('procedure', 'value', 'novelty')], 'next_questions': ['継続して得るものは何か'],
            'web_checks': []}


def test_unregistered_role_and_recursive_evidence(session: Path) -> None:
    p = packet(session, 0, 'develop')
    cards = {c['card_id']: c for c in p['data']['context']['cards']}
    assert set(cards) == {1, 2, 5, 6}
    assert cards[2]['note'] == '効果では進化時を誘発しない'
    assert cards[2]['requirements'][0]['note'] == '供給側の条件'
    assert cards[6]['ref_effect_text'] == '参照先で2ダメージ。'
    assert cards[5]['related_card_ids'] == [6]
    assert cards[1]['evolution_text'] == '進化後の追加効果'
    assert not cards[5]['deck_eligible']
    assert p['data']['context']['rules']


def test_partial_idea_round_trip_search_revision_review(session: Path) -> None:
    first = proposal(packet(session, 0, 'develop'))
    assert submit(session, first)['value'] == '未評価'
    next_packet = packet(session, 1, 'develop')
    assert next_packet['data']['search'][0]['tag_hits'] == [2]
    judged = assessment(packet(session, 1, 'review'))
    assert review(session, judged)['value'] == 'develop'
    next_packet = packet(session, 1, 'develop')
    assert next_packet['data']['previous_reviews'][0]['value'] == 'develop'
    second = {**first, 'packet_hash': next_packet['sha256'], 'parent_revision': 1,
              'change': '生存条件を補助の採用で変える',
              'roles': first['roles'] + [{'card_id': 2, 'role': '継続のための保護'}]}
    submit(session, second)
    records = report(session)['revisions']
    assert records[1]['parent_revision'] == 1
    assert records[1]['reviews'] == []
    assert records[0]['reviews'][0]['value'] == 'develop'


@pytest.mark.parametrize('cid', [3, 4, 5, 999, True])
def test_illegal_or_invented_role_rejected(session: Path, cid: int) -> None:
    data = proposal(packet(session, 0, 'develop'))
    data['roles'][0]['card_id'] = cid
    with pytest.raises(ValueError, match='採用可能'):
        submit(session, data)
    assert not list(session.glob('revision-*.json'))


def test_false_quote_and_wrong_packet_rejected(session: Path) -> None:
    p = packet(session, 0, 'develop')
    data = proposal(p)
    data['steps'][0]['evidence'][0]['quote'] = '実際には無い効果'
    with pytest.raises(ValueError, match='引用'):
        submit(session, data)
    data = proposal(p)
    data['parent_revision'] = 3
    with pytest.raises(ValueError, match='parent_revision'):
        submit(session, data)
    data = proposal(p)
    data['packet_hash'] = '../context'
    with pytest.raises(ValueError, match='packet_hash'):
        submit(session, data)


def test_no_automatic_recommendation_or_self_review(session: Path) -> None:
    submit(session, proposal(packet(session, 0, 'develop')))
    p = packet(session, 1, 'review')
    data = assessment(p)
    data['author'] = 'builder'
    with pytest.raises(ValueError, match='異なるセッション'):
        review(session, data)
    data = assessment(p)
    data['value'] = 'test'
    with pytest.raises(ValueError, match='推薦前'):
        review(session, data)
    data = assessment(p)
    data['novelty'] = 'differentiated'
    with pytest.raises(ValueError, match='Web照合'):
        review(session, data)
    assert report(session)['revisions'][0]['reviews'] == []


def test_text_only_revision_is_not_a_new_development(session: Path) -> None:
    data = proposal(packet(session, 0, 'develop'))
    submit(session, data)
    p = packet(session, 1, 'develop')
    data.update(packet_hash=p['sha256'], parent_revision=1, change='説明を増やした', title='より詳しい説明')
    with pytest.raises(ValueError, match='理由や題名だけ'):
        submit(session, data)


def test_original_db_changes_do_not_rewrite_experiment(session: Path) -> None:
    before = packet(session, 0, 'develop')
    conn = sqlite3.connect(session.parent / 'cards.db')
    conn.execute("UPDATE card_note SET note='新しい訂正' WHERE card_id=2")
    conn.commit()
    conn.close()
    after = packet(session, 0, 'develop')
    assert before['sha256'] == after['sha256']
    conn = sqlite3.connect(session / 'snapshot.db')
    conn.execute("UPDATE card SET cost=9 WHERE card_id=1")
    conn.commit()
    conn.close()
    with pytest.raises(ValueError, match='DBが変更'):
        packet(session, 0, 'develop')


def test_corrupt_context_and_empty_start_do_not_proceed(tmp_path: Path, session: Path) -> None:
    path = session / 'context.json'
    data = json.loads(path.read_text())
    data['data']['class_name'] = 'ドラゴン'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='識別値'):
        packet(session, 0, 'develop')
    db = tmp_path / 'empty.db'
    connect(db).close()
    dest = tmp_path / 'empty-run'
    with pytest.raises(ValueError, match='採用可能'):
        start(dest, db, 'ウィッチ', 'rotation', 'test')
    assert not dest.exists()


def test_cli_start_packet_submit_report(tmp_path: Path) -> None:
    db = tmp_path / 'cards.db'
    make_db(db)
    dest = tmp_path / 'cli-run'
    base = [sys.executable, '-m', 'svdeck.discovery']
    first = subprocess.run(base + ['start', str(dest), '--db', str(db), '--class', 'ウィッチ',
                                  '--objective', '手順の検証'], capture_output=True, text=True, check=True)
    assert json.loads(first.stdout)['eligible_cards'] == 2
    p = json.loads(subprocess.run(base + ['packet', str(dest)], capture_output=True, text=True, check=True).stdout)
    response = tmp_path / 'answer.json'
    response.write_text(json.dumps(proposal(p), ensure_ascii=False))
    subprocess.run(base + ['submit', str(dest), str(response)], capture_output=True, text=True, check=True)
    actual = json.loads(subprocess.run(base + ['report', str(dest)], capture_output=True, text=True, check=True).stdout)
    assert actual['revisions'][0]['title'] == '別用途の途中案'
    bad = subprocess.run(base + ['submit', str(dest), str(tmp_path / 'missing.json')], capture_output=True, text=True)
    assert bad.returncode == 2
    assert 'Traceback' not in bad.stderr
