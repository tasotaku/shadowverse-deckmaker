from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from test_discovery import assessment, make_db, proposal
from svdeck.discovery import main, packet, report, review, start, submit
from svdeck.discovery_evidence import read_object


def setup(tmp_path: Path, sql: str = '') -> Path:
    db = tmp_path / 'cards.db'
    make_db(db)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE card SET skill_text='『敵生成』を手札に加える。' WHERE card_id=3")
        c.execute("UPDATE card_note SET note='相手側の発動条件を保持する' WHERE card_id=3")
        for cid in range(10, 23):
            c.execute("INSERT INTO card(card_id,name,class_name,cost,is_token,is_include_rotation,deck_enabled_num,skill_text,type_category) VALUES (?,?,?,3,0,1,3,?,?)",
                      (cid, f'相手札{cid}', 'ドラゴン', '相手に3ダメージ。', 'follower'))
        c.execute("INSERT INTO card(card_id,name,class_name,cost,is_token,is_include_rotation,deck_enabled_num,skill_text,type_category) VALUES (50,'敵生成','ドラゴン',0,1,1,0,'生成先の本文','spell')")
        c.execute("INSERT INTO meta_deck(id,name,format) VALUES (7,'相手40枚','rotation')")
        c.executemany("INSERT INTO meta_deck_card(deck_id,card_id,card_name,count) VALUES (7,?,?,?)",
                      [(3, '敵クラス', 1)] + [(cid, f'相手札{cid}', 3) for cid in range(10, 23)])
        if sql:
            c.executescript(sql)
    session = tmp_path / 'session'
    start(session, db, 'ウィッチ', 'rotation', '相手の返しを比較')
    return session


def manifest(p: Path) -> dict[str, str]:
    return {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file()}


def test_public_preview_attach_idempotence_and_old_review(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = setup(tmp_path)
    submit(session, proposal(packet(session, 0, 'develop')))
    review(session, assessment(packet(session, 1, 'review')))
    old = manifest(session)
    db_before = hashlib.sha256((tmp_path / 'cards.db').read_bytes()).hexdigest()
    assert main(['opponents', str(session), '--deck-id', '7', '--preview']) == 0
    preview = json.loads(capsys.readouterr().out)
    assert manifest(session) == old
    payload = json.loads(preview['sources'][0]['content'])
    cards = {c['card_id']: c for c in payload['cards']}
    assert sum(c['count'] for c in cards.values()) == 40
    assert set(cards) == {3, 50, *range(10, 23)}
    assert cards[3]['note'] == '相手側の発動条件を保持する'
    assert cards[50]['skill_text'] == '生成先の本文'
    assert cards[50]['count'] == 0 and not cards[50]['in_reference_deck']
    assert payload['opponent_class'] == 'ドラゴン'
    assert main(['opponents', str(session), '--deck-id', '7']) == 0
    added = json.loads(capsys.readouterr().out)['added']
    assert len(added) == 1
    assert main(['opponents', str(session), '--deck-id', '7']) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated['added'] == [] and repeated['existing'] == added
    assert all(manifest(session)[path] == sha for path, sha in old.items())
    context = read_object(session / 'context.json')['data']
    assert 3 not in {c['card_id'] for c in context['cards']}
    current = packet(session, 1, 'review')
    assert len(current['data']['sources']) == 1
    new_review = assessment(current)
    new_review['author'] = 'opponent-inspector'
    new_review['findings'][0]['evidence'] = [{'source_hash': added[0], 'quote': '相手側の発動条件を保持する'}]
    review(session, new_review)
    history = report(session)['revisions'][0]['review_contexts']
    assert sorted(len(r['additional_source_hashes']) for r in history) == [0, 1]
    assert hashlib.sha256((tmp_path / 'cards.db').read_bytes()).hexdigest() == db_before


@pytest.mark.parametrize('sql', [
    "UPDATE meta_deck SET format='unlimited' WHERE id=7",
    'UPDATE meta_deck_card SET count=2 WHERE deck_id=7 AND card_id=3',
    'UPDATE meta_deck_card SET card_id=999 WHERE deck_id=7 AND card_id=3',
    'UPDATE card SET is_include_rotation=0 WHERE card_id=10',
    'UPDATE card SET is_token=1 WHERE card_id=10',
    'UPDATE card SET deck_enabled_num=2 WHERE card_id=10',
    "UPDATE card SET class_name='ロイヤル' WHERE card_id=10",
    "UPDATE card SET name='相手札10' WHERE card_id=11",
    'UPDATE meta_deck_card SET count=-1 WHERE deck_id=7 AND card_id=3',
])
def test_reject_invalid_opponent_without_mutation(tmp_path: Path, capsys: pytest.CaptureFixture[str], sql: str) -> None:
    session = setup(tmp_path, sql)
    before = manifest(session)
    assert main(['opponents', str(session), '--deck-id', '7']) == 2
    assert '探索入力エラー' in capsys.readouterr().err
    assert manifest(session) == before


@pytest.mark.parametrize('ids', [['7', '999'], ['7', '7'], ['0'], ['-1']])
def test_invalid_or_missing_second_deck_is_atomic(tmp_path: Path, capsys: pytest.CaptureFixture[str], ids: list[str]) -> None:
    session = setup(tmp_path)
    before = manifest(session)
    args = ['opponents', str(session)]
    for did in ids:
        args += ['--deck-id', did]
    assert main(args) == 2
    assert capsys.readouterr().err
    assert manifest(session) == before


def test_changed_snapshot_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = setup(tmp_path)
    with sqlite3.connect(session / 'snapshot.db') as c:
        c.execute("UPDATE card SET skill_text='改変' WHERE card_id=3")
    before = manifest(session)
    assert main(['opponents', str(session), '--deck-id', '7']) == 2
    assert capsys.readouterr().err
    assert manifest(session) == before
