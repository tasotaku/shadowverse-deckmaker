import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from svdeck import worker


def invoke(tmp_path, code, *, timeout=2, grace=.15, extra=()):
    out = tmp_path / 'run'
    cmd = [sys.executable, '-m', 'svdeck.worker', '--output', str(out),
           '--timeout', str(timeout), '--grace', str(grace), *extra,
           '--', sys.executable, '-c', code]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    return result, json.loads((out / 'run.json').read_text()), out


def alive(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    return bool(result.stdout.strip()) and not result.stdout.strip().startswith('Z')


def test_success_stdin_output_and_partial(tmp_path):
    source = tmp_path / '入力.txt'
    source.write_text('未確認の案\n')
    result, record, out = invoke(tmp_path,
        "import sys,os;from pathlib import Path;print(sys.stdin.read(),end='');"
        "print('補助情報',file=sys.stderr);Path(os.environ['SVDECK_RUN_DIR'],'draft.txt').write_text('途中成果')",
        extra=('--stdin', str(source)))
    assert result.returncode == 0
    assert record['status'] == 'completed' and record['worker_returncode'] == 0
    assert (out / 'stdout.log').read_text() == '未確認の案\n'
    assert (out / 'stderr.log').read_text() == '補助情報\n'
    assert (out / 'draft.txt').read_text() == '途中成果'
    assert datetime.fromisoformat(record['ended_at']) >= datetime.fromisoformat(record['started_at'])


def test_worker_failure_is_preserved(tmp_path):
    result, record, out = invoke(tmp_path, "import sys;print('incomplete',flush=True);sys.exit(7)")
    assert result.returncode == record['worker_returncode'] == 7
    assert record['status'] == 'failed' and (out / 'stdout.log').read_text() == 'incomplete\n'


def test_timeout_grace_keeps_partial_and_stays_timeout(tmp_path):
    code = """import os,signal,time,sys
from pathlib import Path
out=Path(os.environ['SVDECK_RUN_DIR'])
def stop(signum,frame):
    (out/'cleanup.txt').write_text('保存済み')
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
(out/'draft.txt').write_text('途中の仮説')
print('started',flush=True)
time.sleep(20)
"""
    result, record, out = invoke(tmp_path, code, timeout=.5, grace=.5)
    assert result.returncode == 124 and record['status'] == 'timed_out'
    assert record['worker_returncode'] == 0
    assert (out / 'draft.txt').read_text() == '途中の仮説'
    assert (out / 'cleanup.txt').read_text() == '保存済み'
    assert 'deadline_observed' in [e['event'] for e in record['events']]
    assert record['elapsed_seconds'] < 3


def test_stubborn_group_is_killed_without_touching_other_process(tmp_path):
    outsider = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)'])
    code = """import os,signal,subprocess,sys,time,json
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(20)'])
Path(os.environ['SVDECK_RUN_DIR'],'pids.json').write_text(json.dumps([os.getpid(),child.pid]))
time.sleep(20)
"""
    try:
        result, record, out = invoke(tmp_path, code, timeout=1)
        assert result.returncode == 124 and record['worker_returncode'] == -signal.SIGKILL
        assert all(not alive(pid) for pid in json.loads((out / 'pids.json').read_text()))
        assert outsider.poll() is None
        assert 'kill_requested' in [e['event'] for e in record['events']]
    finally:
        outsider.terminate()
        outsider.wait(timeout=2)


def test_parent_exit_does_not_leave_child_running(tmp_path):
    code = """import os,subprocess,sys
from pathlib import Path
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])
Path(os.environ['SVDECK_RUN_DIR'],'child.pid').write_text(str(child.pid))
"""
    result, record, out = invoke(tmp_path, code)
    assert result.returncode == 0 and record['status'] == 'completed'
    assert not alive(int((out / 'child.pid').read_text()))


def test_supervisor_interruption_cleans_worker(tmp_path):
    out = tmp_path / 'run'
    code = "import os,time;from pathlib import Path;Path(os.environ['SVDECK_RUN_DIR'],'ready').write_text(str(os.getpid()));time.sleep(20)"
    cmd = [sys.executable, '-m', 'svdeck.worker', '--output', str(out), '--timeout', '10',
           '--grace', '.1', '--', sys.executable, '-c', code]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        until = time.monotonic() + 4
        while not (out / 'ready').exists() and time.monotonic() < until:
            time.sleep(.02)
        assert (out / 'ready').exists()
        p.send_signal(signal.SIGTERM)
        assert p.wait(timeout=4) == 143
        record = json.loads((out / 'run.json').read_text())
        assert record['status'] == 'interrupted'
        assert not alive(int((out / 'ready').read_text()))
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=2)


@pytest.mark.parametrize('timeout,grace', [(0,0),(-1,0),(float('nan'),0),(float('inf'),0),(1,-1),(1,float('nan'))])
def test_bad_time_rejected_before_output(tmp_path, timeout, grace):
    with pytest.raises(ValueError):
        worker.run([sys.executable, '-c', 'pass'], tmp_path/'run', timeout, grace)
    assert not (tmp_path/'run').exists()


def test_existing_output_is_not_overwritten(tmp_path):
    out = tmp_path/'run'
    out.mkdir()
    (out/'run.json').write_text('previous result')
    with pytest.raises(FileExistsError):
        worker.run([sys.executable, '-c', 'pass'], out, 1, 0)
    assert (out/'run.json').read_text() == 'previous result'


def test_launch_failure_does_not_claim_worker_exit(tmp_path):
    code, result = worker.run([str(tmp_path/'missing-command')], tmp_path/'run', 1, 0)
    assert code == 127 and result['status'] == 'launch_failed'
    assert result['worker_pid'] is None and result['worker_returncode'] is None


def test_arguments_are_not_shell_expanded(tmp_path):
    literal = '$(touch shell-expansion); *'
    code, record = worker.run([sys.executable, '-c', 'import sys;print(sys.argv[1])', literal],
                              tmp_path/'run', 2, 0, cwd=tmp_path)
    assert code == 0 and (tmp_path/'run/stdout.log').read_text() == literal + '\n'
    assert not (tmp_path/'shell-expansion').exists()


def test_denied_termination_is_recorded(tmp_path, monkeypatch):
    def denied(process, sig):
        raise PermissionError('simulated signal refusal')
    monkeypatch.setattr(worker, 'signal_group', denied)
    record = None
    try:
        code, record = worker.run([sys.executable,'-c','import time;time.sleep(20)'],
                                  tmp_path/'run', .15, 0)
        assert code == 125 and record['status'] == 'termination_unconfirmed'
        assert record['worker_returncode'] is None and record['ended_at'] is not None
        assert json.loads((tmp_path/'run/run.json').read_text()) == record
    finally:
        if record and record['worker_pid']:
            os.kill(record['worker_pid'], signal.SIGKILL)
            os.waitpid(record['worker_pid'], 0)


def test_delayed_group_disappearance_is_observed(tmp_path, monkeypatch):
    original = os.killpg
    errors = 0
    def delayed(pid, sig):
        nonlocal errors
        if sig == 0 and errors < 3:
            errors += 1
            raise PermissionError('group disappearance has not settled')
        return original(pid, sig)
    monkeypatch.setattr(worker.os, 'killpg', delayed)
    code, record = worker.run([sys.executable, '-c', 'import time;time.sleep(20)'],
                              tmp_path/'run', .2, .5)
    assert errors == 3 and code == 124
    assert record['worker_returncode'] == -signal.SIGTERM
    assert record['status'] == 'timed_out' and record['elapsed_seconds'] < 2


def test_persistent_group_permission_error_is_bounded(tmp_path, monkeypatch):
    class Process:
        pid = 0
        def poll(self):
            return 0
    calls = []
    def denied(pid, sig):
        calls.append((pid, sig))
        raise PermissionError('not evidence that group vanished')
    monkeypatch.setattr(worker.os, 'killpg', denied)
    start = time.monotonic()
    with pytest.raises(PermissionError):
        worker.signal_group(Process(), 0)
    assert len(calls) == 5 and .18 <= time.monotonic() - start < 1


@pytest.mark.parametrize('shift', [3600, -3600])
def test_clock_shift_does_not_extend_deadline(tmp_path, monkeypatch, shift):
    class Clock:
        offset = 0
        @classmethod
        def now(cls, zone):
            return datetime.now(zone) + timedelta(seconds=cls.offset)
    real_popen = subprocess.Popen
    def launch(*args, **kwargs):
        p = real_popen(*args, **kwargs)
        Clock.offset = shift
        return p
    monkeypatch.setattr(worker, 'datetime', Clock)
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    begin = time.monotonic()
    code, record = worker.run([sys.executable,'-c','import time;time.sleep(20)'],tmp_path/'run',.3,0)
    assert code == 124 and record['status'] == 'timed_out'
    assert time.monotonic() - begin < 2
