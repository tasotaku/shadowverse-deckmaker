import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timedelta

import pytest
from svdeck import worker


def test_elapsed_child_receives_matching_clock_and_no_inherited_utc(tmp_path, monkeypatch):
    monkeypatch.setenv('SVDECK_DEADLINE_UTC', 'stale-parent-deadline')
    code, record = worker.run([sys.executable, '-c',
        "import os,time,json;print(json.dumps({'clock':os.environ['SVDECK_BUDGET_CLOCK'],'utc':os.environ.get('SVDECK_DEADLINE_UTC'),'remaining':float(os.environ['SVDECK_DEADLINE_MONOTONIC'])-time.monotonic()}))"],
        tmp_path/'run', 2, .1, clock='elapsed')
    child = json.loads((tmp_path/'run/stdout.log').read_text())
    assert code == 0 and record['budget_clock'] == child['clock'] == 'elapsed'
    assert record['deadline_at'] is None and child['utc'] is None
    assert 0 < child['remaining'] <= 2
    assert record['started_at'] and record['ended_at']


@pytest.mark.parametrize('mode', ['deadline', 'elapsed'])
def test_forward_utc_change_selects_the_requested_budget(tmp_path, monkeypatch, mode):
    class Clock:
        offset = 0
        @classmethod
        def now(cls, zone):
            return datetime.now(zone) + timedelta(seconds=cls.offset)
    original = subprocess.Popen
    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        Clock.offset = 3600
        return process
    monkeypatch.setattr(worker, 'datetime', Clock)
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    out = tmp_path/'run'
    code, record = worker.run([sys.executable, '-c', "import time;time.sleep(.2);print('work completed')"],
                             out, 2, .1, clock=mode)
    if mode == 'elapsed':
        assert code == 0 and record['status'] == 'completed'
        assert (out/'stdout.log').read_text() == 'work completed\n'
        assert record['elapsed_seconds'] < 2
    else:
        assert code == 124 and record['status'] == 'timed_out'
        event = next(e for e in record['events'] if e['event'] == 'deadline_observed')
        assert event['utc_expired'] and not event['elapsed_expired']
    assert (datetime.fromisoformat(record['ended_at'])-datetime.fromisoformat(record['started_at'])).total_seconds() > 3600


def test_elapsed_timeout_still_stops_and_keeps_output(tmp_path):
    out = tmp_path/'run'
    command = [sys.executable, '-m', 'svdeck.worker', '--output', str(out), '--timeout', '.3',
               '--grace', '.1', '--clock', 'elapsed', '--', sys.executable, '-c',
               "import time;print('partial',flush=True);time.sleep(30)"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=4)
    record = json.loads((out/'run.json').read_text())
    assert result.returncode == 124 and record['status'] == 'timed_out'
    assert .3 <= record['elapsed_seconds'] < 2
    event = next(e for e in record['events'] if e['event'] == 'deadline_observed')
    assert event['elapsed_expired'] and not event['utc_expired']
    assert (out/'stdout.log').read_text() == 'partial\n'


def test_bad_clock_fails_before_creating_output(tmp_path):
    with pytest.raises(ValueError, match='clock'):
        worker.run([sys.executable, '-c', 'pass'], tmp_path/'run', 1, 0, clock='unknown')
    assert not (tmp_path/'run').exists()


def test_default_child_retains_utc_and_monotonic_deadlines(tmp_path):
    out = tmp_path/'run'
    code, record = worker.run([sys.executable, '-c',
        "import os,json;print(json.dumps({k:os.environ[k] for k in ['SVDECK_BUDGET_CLOCK','SVDECK_DEADLINE_UTC','SVDECK_DEADLINE_MONOTONIC']}))"],out,2,.1)
    child = json.loads((out/'stdout.log').read_text())
    assert code == 0 and child['SVDECK_BUDGET_CLOCK'] == 'deadline'
    assert child['SVDECK_DEADLINE_UTC'] == record['deadline_at']
    assert float(child['SVDECK_DEADLINE_MONOTONIC']) == record['deadline_monotonic']
