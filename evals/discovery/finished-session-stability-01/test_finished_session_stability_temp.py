import json
import sys
from pathlib import Path

import pytest
from svdeck import discovery as d, discovery_run as r
from test_discovery_run_temp import source, fake_worker
from test_explicit_finish_current_temp import synthetic


@pytest.mark.parametrize('review_only', [False, True])
def test_completed_stages_remain_verifiable(source, tmp_path, review_only):
    out = tmp_path / 'completed'
    result = r.run(source, out, synthetic(tmp_path), None if review_only else 10, 10,
                   revision=1 if review_only else None, review_only=review_only, explicit_finish=True)
    assert result['status'] == 'completed', result
    for entry in result['stages']:
        work = out / entry['stage']
        contract = json.loads((work / 'finish-config.json').read_text())
        request = json.loads((work / 'finish-request.json').read_text())
        assert r.manifest(work / 'session') == request['session_manifest']
        assert r.check_finish(work, contract)
    latest = d.report(out / 'session')['revisions'][-1]
    final_review = latest['reviews'][-1]
    packet = d._read_envelope(out / 'session/packets' / (final_review['packet_hash'] + '.json'))
    assert packet['proposal'] == d._revision(out / 'session', latest['revision'])
    assert packet['previous_reviews'] == []


@pytest.mark.parametrize('changed', ['develop/session', 'review-input'])
def test_review_cannot_change_completed_or_prepared_data(source, tmp_path, monkeypatch, changed):
    fake_worker(monkeypatch)
    execute = r.worker.run
    def tamper(*args):
        code, record = execute(*args)
        work = args[4]
        if work.name == 'review':
            (work.parent / changed / 'extra.json').write_text('{}')
        return code, record
    monkeypatch.setattr(r.worker, 'run', tamper)
    result = r.run(source, tmp_path / 'tampered', Path(sys.executable), 10, 10)
    assert result['status'] == 'failed', result
    assert '固定ファイルが変更' in result['failure']
    assert not (tmp_path / 'tampered/session').exists()
