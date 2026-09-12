from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any

import pytest

from svdeck import discovery as d, discovery_run as r
from svdeck.discovery_evidence import read_only, search_questions, digest
from svdeck.discovery_read import read_packet
from test_discovery import make_db, proposal, assessment
from test_discovery_sources import source as observation
from test_explicit_finish_temp import prepared, ready
from test_discovery_run_temp import fake_worker, source


@pytest.fixture
def session(tmp_path: Path) -> Path:
    db = tmp_path / 'cards.db'
    make_db(db)
    with sqlite3.connect(db) as conn:
        conn.executemany("INSERT INTO atom_tag VALUES (?,'supply','潜伏付与')", [(3,), (4,), (5,)])
    folder = tmp_path / 'session'
    d.start(folder, db, 'ウィッチ', 'rotation', '人工の検索補助検査')
    return folder


@pytest.mark.parametrize('submitted', [False, True])
@pytest.mark.parametrize('tag', ['潜伏付与', '存在しない検査タグ'])
def test_query_before_submission_and_existing_history(session: Path, submitted: bool, tag: str) -> None:
    if submitted:
        d.submit(session, proposal(d.packet(session, 0, 'develop')))
        d.review(session, assessment(d.packet(session, 1, 'review')))
        d.attach(session, {'sources': [observation()]})
    current = d.packet(session, None, 'develop')
    before = r.manifest(session)
    context = d._context(session)
    with read_only(session / 'snapshot.db') as conn:
        expected = search_questions(conn, context, [{'question': '未提出の人工問', 'tag': tag}])[0]
    result = d.query(session, '未提出の人工問', tag)
    assert result['search'] == expected
    assert result['context_hash'] == digest(context)
    assert result['snapshot_sha256'] == context['snapshot_sha256']
    assert result['search']['tag_hits'] == ([2] if tag == '潜伏付与' else [])
    for ref in result['card_references']:
        card = read_packet(session, current['sha256'], 'cards', ref['offset'], 1)['content'][0]
        assert card['card_id'] == ref['card_id'] == 2
        assert card['note'] == '効果では進化時を誘発しない'
        assert card['skill_text'] == '味方に潜伏を与える。'
    assert len(result['card_references']) == len(expected['tag_hits'])
    assert result['limitations']
    assert r.manifest(session) == before


@pytest.mark.parametrize('question,tag', [('', 'a'), (' ', 'a'), (None, 'a'), ([], 'a'),
                                         ('q', ''), ('q', '\n'), ('q', None), ('q', True), ('q', ['a'])])
def test_invalid_input_is_rejected(session: Path, question: Any, tag: Any) -> None:
    before = r.manifest(session)
    with pytest.raises(ValueError):
        d.query(session, question, tag)
    assert r.manifest(session) == before


@pytest.mark.parametrize('filename', ['snapshot.db', 'context.json'])
def test_changed_fixed_input_is_rejected(session: Path, filename: str) -> None:
    path = session / filename
    path.write_bytes(path.read_bytes() + b'changed')
    before = r.manifest(session)
    with pytest.raises((ValueError, json.JSONDecodeError)):
        d.query(session, 'q', '潜伏付与')
    assert r.manifest(session) == before


@pytest.mark.parametrize('extra', [[], ['--question', 'another'], ['--tag', 'another'],
                                  ['--db', '/tmp/other.db'], ['--revision', '0'],
                                  ['--class', 'ドラゴン'], ['/tmp/other-session']])
def test_cli_and_fixed_public_scope(session: Path, extra: list[str]) -> None:
    before = r.manifest(session)
    command = ['query', '--question', '新しい人工問', '--tag', '潜伏付与', *extra]
    cli = subprocess.run([sys.executable, '-m', 'svdeck.discovery', command[0], str(session), *command[1:]],
                         text=True, capture_output=True)
    assert cli.returncode == (2 if extra else 0)
    if not extra:
        assert json.loads(cli.stdout)['search']['tag_hits'] == [2]
    work = session.parent
    (work / 'public-config.json').write_text(json.dumps({'stage': 'develop', 'revision': 0, 'author': 'test'}))
    assert r.public_main(work, command) == (2 if extra else 0)
    operation = json.loads(next((work / 'operations').glob('*.json')).read_text())
    assert operation['args'] == command and operation['exit_code'] == cli.returncode
    assert operation['started_at'] and operation['ended_at']
    assert r.manifest(session) == before


@pytest.mark.parametrize('stage', ['review', 'inquiry', 'inspect'])
def test_other_stages_do_not_gain_query(session: Path, stage: str) -> None:
    work = session.parent
    (work / 'public-config.json').write_text(json.dumps({'stage': stage, 'revision': 0, 'author': 'test'}))
    before = r.manifest(session)
    assert r.public_main(work, ['query', '--question', 'q', '--tag', '潜伏付与']) == 2
    log = json.loads(next((work / 'operations').glob('*.json')).read_text())
    assert '許可されていない' in log['stderr']
    assert r.manifest(session) == before


def test_query_rejected_after_verified_finish(prepared: Any) -> None:
    work, contract = prepared
    ready(work)
    assert r.public_main(work, ['finish']) == 0
    assert r.check_finish(work, contract)
    before = r.manifest(work / 'session')
    assert r.public_main(work, ['query', '--question', 'q', '--tag', '潜伏付与']) == 2
    assert r.manifest(work / 'session') == before
    assert r.check_finish(work, contract)


def test_original_instructions_and_stage_prompt(session: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base: dict[str, Any] = {'__name__': 'fixed_baseline', '__file__': d.__file__}
    code = subprocess.check_output(['git', 'show', 'c2a5ae073e60386015b2c89d9f99f3a5a22baf40:src/svdeck/discovery.py'], text=True)
    exec(compile(code, str(d.__file__), 'exec'), base)
    for name in ('DEVELOP_RULES', 'DEVELOP', 'REVIEW', 'FINISH'):
        assert getattr(d, name) == base[name]
    original = d.packet(session, 0, 'develop')
    assert original == base['packet'](session, 0, 'develop')
    fake_worker(monkeypatch)
    out = tmp_path / 'run'
    result = r.run(session, out, Path(sys.executable), 10, 10)
    assert result['status'] == 'completed'
    assert 'public.py query --question TEXT --tag TAG' in (out / 'develop/prompt.md').read_text()
    assert 'public.py query' not in (out / 'review/prompt.md').read_text()


def test_query_needs_no_packet_or_proposal(session: Path) -> None:
    before = r.manifest(session)
    assert not list((session / 'packets').iterdir())
    assert not list(session.glob('revision-*.json'))
    assert d.query(session, '未提出の人工問', '潜伏付与')['search']['tag_hits'] == [2]
    assert r.manifest(session) == before
