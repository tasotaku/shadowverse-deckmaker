"""適用範囲の任意追加と保存互換性のみを合成カードで検査する。"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import pytest

import svdeck.discovery as discovery
from svdeck.discovery_evidence import digest
from svdeck.discovery_read import packet_summary, read_packet
from test_discovery import assessment, make_db, proposal
from test_discovery_read import read_all


@pytest.fixture
def inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    class FixedTime:
        @staticmethod
        def now(tz: object = None) -> datetime:
            return datetime(2026, 9, 9, tzinfo=timezone.utc)
    monkeypatch.setattr(discovery, 'datetime', FixedTime)
    db = tmp_path / 'cards.db'
    make_db(db)
    docs = tmp_path / 'docs'
    docs.mkdir()
    # 実際の抽出を使い、追加する開発文書で原則を変えていないことも照合する。
    for name in ('design.md', 'rules.md'):
        (docs / name).write_bytes((discovery.DOCS / name).read_bytes())
    return db, docs


def begin(path: Path, inputs: tuple[Path, Path], scope: str | None = None) -> dict[str, Any]:
    db, docs = inputs
    if scope is None:
        return discovery.start(path, db, 'ウィッチ', 'rotation', '合成資料の保存互換性', docs)
    return discovery.start(path, db, 'ウィッチ', 'rotation', '合成資料の保存互換性', docs,
                           principles_scope=scope)


def test_default_and_explicit_legacy_are_identical(tmp_path: Path, inputs: tuple[Path, Path]) -> None:
    implicit, explicit = tmp_path / 'default', tmp_path / 'legacy'
    a = begin(implicit, inputs)
    b = begin(explicit, inputs, 'legacy')
    assert {k: v for k, v in a.items() if k != 'session'} == {k: v for k, v in b.items() if k != 'session'}
    assert (implicit / 'context.json').read_bytes() == (explicit / 'context.json').read_bytes()
    first = discovery.packet(implicit, 0, 'develop')
    assert first == discovery.packet(explicit, 0, 'develop')
    assert first['data']['instruction'] == discovery.DEVELOP
    context = first['data']['context']
    assert not any(k.startswith('principles_scope') for k in context)
    assert 'principles_scope_guide' not in {p['section'] for p in packet_summary(implicit, first['sha256'])['sections']}
    with pytest.raises(ValueError, match='未知の区分'):
        read_packet(implicit, first['sha256'], 'principles_scope_guide')
    for folder in (implicit, explicit):
        discovery.submit(folder, proposal(discovery.packet(folder, 0, 'develop')))
    left = discovery.packet(implicit, 1, 'review')
    assert left == discovery.packet(explicit, 1, 'review')
    assert left['data']['instruction'] == discovery.REVIEW


def test_scoped_adds_only_guide_and_version(tmp_path: Path, inputs: tuple[Path, Path]) -> None:
    legacy, scoped = tmp_path / 'legacy', tmp_path / 'scoped'
    begin(legacy, inputs)
    begin(scoped, inputs, 'scoped')
    a = discovery.packet(legacy, 0, 'develop')['data']['context']
    b = discovery.packet(scoped, 0, 'develop')['data']['context']
    assert set(b) - set(a) == {'principles_scope_version', 'principles_scope_guide'}
    assert {k: b[k] for k in a} == a
    assert b['principles'].encode('utf-8') == a['principles'].encode('utf-8')
    assert b['principles_scope_version'] == 'scoped-v1'
    assert re.findall(r'^R\d{2}｜', b['principles_scope_guide'], re.MULTILINE) == [f'R{i:02d}｜' for i in range(1, 28)]
    assert b['principles_scope_guide'] not in b['principles']


@pytest.mark.parametrize('stage', ['develop', 'review'])
def test_guide_is_reachable_and_exact_in_both_stages(
    tmp_path: Path, inputs: tuple[Path, Path], stage: str,
) -> None:
    folder = tmp_path / stage
    begin(folder, inputs, 'scoped')
    if stage == 'review':
        discovery.submit(folder, proposal(discovery.packet(folder, 0, 'develop')))
    p = discovery.packet(folder, None, stage)
    summary = packet_summary(folder, p['sha256'])
    section = next(s for s in summary['sections'] if s['section'] == 'principles_scope_guide')
    assert section['full_packet_path'] == 'data.context.principles_scope_guide'
    assert section['unit'] == 'lines'
    assert ''.join(read_all(folder, p['sha256'], 'principles_scope_guide', 7)) == p['data']['context']['principles_scope_guide']
    assert ''.join(read_all(folder, p['sha256'], 'principles', 7)) == p['data']['context']['principles']
    metadata = json.loads(''.join(read_all(folder, p['sha256'], 'context_metadata', 3)))
    assert metadata['principles_scope_version'] == 'scoped-v1'
    assert 'principles_scope_guide' not in metadata
    expected = discovery.REVIEW if stage == 'review' else discovery.DEVELOP
    assert p['data']['instruction'] == discovery.SCOPE_INSTRUCTION + expected
    assert summary['instruction'] == p['data']['instruction']
    assert p['sha256'] == digest(p['data'])


def test_saved_scope_survives_guide_and_docs_update(
    tmp_path: Path, inputs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / 'old'
    begin(folder, inputs, 'scoped')
    p = discovery.packet(folder, 0, 'develop')
    old_files = {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()}
    monkeypatch.setattr(discovery, 'SCOPE_GUIDE', '変更後の検査用ガイド\n')
    monkeypatch.setattr(discovery, 'SCOPE_VERSION', 'scoped-test-version')
    (inputs[1] / 'design.md').write_text('## 1. 検査用の変更\n', encoding='utf-8')
    assert discovery.packet(folder, 0, 'develop') == p
    assert ''.join(read_all(folder, p['sha256'], 'principles_scope_guide', 2)) == p['data']['context']['principles_scope_guide']
    assert all(path.read_bytes() == before for path, before in old_files.items())
    new = tmp_path / 'new'
    begin(new, inputs, 'scoped')
    current = discovery.packet(new, 0, 'develop')['data']['context']
    assert current['principles_scope_version'] == 'scoped-test-version'
    assert current['principles_scope_guide'] == '変更後の検査用ガイド\n'
    assert current['principles'] != p['data']['context']['principles']
    # 保存packetのreadは現在contextやDBにも依存しない。
    (folder / 'context.json').rename(folder / 'context.saved')
    (folder / 'snapshot.db').rename(folder / 'snapshot.saved')
    assert ''.join(read_all(folder, p['sha256'], 'principles_scope_guide', 5)) == p['data']['context']['principles_scope_guide']


@pytest.mark.parametrize('scope', ['', 'unknown', 'SCOPED'])
def test_bad_scope_is_rejected_before_io(tmp_path: Path, scope: str) -> None:
    folder = tmp_path / 'no-session'
    with pytest.raises(ValueError, match='principles_scope'):
        discovery.start(folder, tmp_path / 'missing.db', 'ウィッチ', 'rotation', '合成検査', principles_scope=scope)
    assert not folder.exists()
    run = subprocess.run([sys.executable, '-m', 'svdeck.discovery', 'start', str(folder), '--db', str(tmp_path / 'missing.db'),
                          '--class', 'ウィッチ', '--objective', '合成検査', '--principles-scope', scope],
                         capture_output=True, text=True)
    assert run.returncode == 2
    assert 'invalid choice' in run.stderr
    assert not folder.exists()


@pytest.mark.parametrize('failure', ['class', 'rotation', 'token', 'quote', 'recommendation'])
def test_scoped_keeps_existing_rejection_boundaries(
    tmp_path: Path, inputs: tuple[Path, Path], failure: str,
) -> None:
    folder = tmp_path / failure
    begin(folder, inputs, 'scoped')
    p = discovery.packet(folder, 0, 'develop')
    response = proposal(p)
    if failure == 'recommendation':
        response.update(steps=[], plan={})
        discovery.submit(folder, response)
        judgement = assessment(discovery.packet(folder, 1, 'review'))
        judgement['value'] = 'test'
        with pytest.raises(ValueError, match='未確認'):
            discovery.review(folder, judgement)
        assert not list(folder.glob('review-*.json'))
        return
    if failure == 'quote':
        response['steps'][0]['evidence'][0]['quote'] = '存在しない引用'
    else:
        response['roles'][0]['card_id'] = {'class': 3, 'rotation': 4, 'token': 5}[failure]
    with pytest.raises(ValueError, match='採用可能|引用'):
        discovery.submit(folder, response)
    assert not list(folder.glob('revision-*.json'))


@pytest.mark.parametrize('scope', ['legacy', 'scoped'])
def test_public_cli_round_trip(tmp_path: Path, scope: str) -> None:
    db = tmp_path / 'cards.db'
    make_db(db)
    folder = tmp_path / scope
    records: list[dict[str, Any]] = []
    def run(*args: str) -> dict[str, Any]:
        command = [sys.executable, '-m', 'svdeck.discovery', *args]
        started = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(command, capture_output=True, text=True)
        records.append({'command': command, 'started_at_utc': started, 'returncode': result.returncode,
                        'stdout': result.stdout, 'stderr': result.stderr})
        (tmp_path / 'public-commands.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    result = run('start', str(folder), '--db', str(db), '--class', 'ウィッチ', '--objective', '合成資料の公開往復',
                 '--principles-scope', scope)
    assert result['eligible_cards'] == 2
    p = run('packet', str(folder))
    summary = run('packet', str(folder), '--summary')
    assert p['sha256'] == summary['sha256']
    section = 'principles_scope_guide' if scope == 'scoped' else 'principles'
    assert section in {s['section'] for s in summary['sections']}
    parts = []
    offset = 0
    while True:
        page = run('read', str(folder), p['sha256'], section, '--offset', str(offset), '--limit', '19')
        parts.extend(page['content'])
        if page['next_offset'] is None:
            break
        offset = page['next_offset']
    assert ''.join(parts) == p['data']['context'][section]
    response = proposal(p)
    response.update(steps=[], plan={})
    answer = tmp_path / 'proposal.json'
    answer.write_text(json.dumps(response, ensure_ascii=False))
    assert run('submit', str(folder), str(answer))['revision'] == 1
    review_packet = run('packet', str(folder), '--stage', 'review')
    answer = tmp_path / 'assessment.json'
    answer.write_text(json.dumps(assessment(review_packet), ensure_ascii=False))
    assert run('review', str(folder), str(answer))['value'] == 'develop'
    report = run('report', str(folder))
    assert report['revisions'][0]['packet_hash'] == p['sha256']
    assert report['revisions'][0]['reviews'][0]['packet_hash'] == review_packet['sha256']
    assert report['revisions'][0]['reviews'][0]['procedure'] == 'conditional'
