"""Run one local exploration worker with a recorded deadline (POSIX only)."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
from types import FrameType
from typing import Any, Callable, Literal

from svdeck.worker_journal import JOURNAL_ERRORS, RunJournal


class JournalStartExpired(RuntimeError):
    """The optional start write exhausted the budget before the child was launched."""


def save_record(path: Path, record: dict[str, object]) -> None:
    # AI_NOTE: 読取り側へ途中のJSONを見せず、前の状態か次の状態を一度に渡す。
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def signal_group(process: subprocess.Popen[bytes], sig: int, require_running: bool = False) -> bool:
    # AI_NOTE: 終了直後の群は親の回収後も一時的にEPERMになり得るため、短い上限内で再確認する。
    for attempt in range(5):
        code = process.poll()
        if require_running and code is not None:
            return False
        try:
            os.killpg(process.pid, sig)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)
    raise AssertionError("signal retry loop did not return")


def run(command: list[str], output: Path, timeout: float, grace: float,
        cwd: Path | None = None, stdin: Path | None = None,
        clock: Literal['deadline', 'elapsed'] = 'deadline',
        journal: RunJournal | None = None,
        finish_check: Callable[[], dict[str, Any] | None] | None = None) -> tuple[int, dict[str, object]]:
    # AI_NOTE: 判定の中身に触れず、実行の期限・終了確認と既存出力の保持だけを担当する。
    if os.name != 'posix':
        raise ValueError('この入口のプロセス群制御はPOSIX専用です')
    if not command or not command[0]:
        raise ValueError('実行コマンドが必要です')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeoutは有限の正の秒数が必要です')
    if not math.isfinite(grace) or grace < 0:
        raise ValueError('graceは有限の0以上の秒数が必要です')
    if clock not in ('deadline', 'elapsed'):
        raise ValueError('clockはdeadlineまたはelapsedが必要です')
    started = datetime.now(timezone.utc)
    deadline = started + timedelta(seconds=timeout)
    clock_start = time.monotonic()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    events: list[dict[str, object]] = []
    record: dict[str, object] = {
        'status': 'starting', 'command': command, 'cwd': str((cwd or Path.cwd()).resolve()),
        'stdin': str(stdin.resolve()) if stdin else None, 'output': str(output),
        'started_at': started.isoformat(),
        'deadline_at': deadline.isoformat() if clock == 'deadline' else None,
        'budget_clock': clock, 'deadline_monotonic': clock_start + timeout,
        'explicit_finish': finish_check is not None,
        'timeout_seconds': timeout, 'termination_grace_seconds': grace,
        'supervisor_pid': os.getpid(), 'worker_pid': None, 'worker_returncode': None,
        'ended_at': None, 'events': events,
        'limits': 'Elapsed clocks include waiting; not CPU time. Suspension handling depends on the OS. '
                  'Host suspension can delay observation. elapsed mode does not enforce a UTC deadline. '
                  'Only descendants remaining in the original process group are controlled. '
                  'Partial output is not a completed proposal or review.'}
    record_path = output / 'run.json'

    def mark(event: str, **fields: object) -> None:
        # AI_NOTE: 終了要求と確認の時点を別々に記録し、欠けた工程時刻を補わない。
        events.append({'event': event, 'at': datetime.now(timezone.utc).isoformat(),
                       'elapsed_seconds': time.monotonic() - clock_start, **fields})
        save_record(record_path, record)

    finish_evidence: dict[str, Any] | None = None
    own_termination = False
    interrupted: int | None = None

    def request_stop(signum: int, frame: FrameType | None) -> None:
        # AI_NOTE: シグナル処理中は保存や待機をせず、監視ループが安全に終了させる。
        nonlocal interrupted
        interrupted = signum

    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    process: subprocess.Popen[bytes] | None = None
    exit_code = 125
    try:
        mark('started')
        if journal is not None:
            record['journal_sync'] = {**journal.identity(), 'status': 'starting'}
            mark('journal_starting')
            try:
                record['journal_sync'] = journal.begin(record)
            except JOURNAL_ERRORS as exc:
                link = record['journal_sync']
                assert isinstance(link, dict)
                record.update(status='journal_start_failed', ended_at=datetime.now(timezone.utc).isoformat(),
                              elapsed_seconds=time.monotonic() - clock_start, runner_returncode=125,
                              journal_sync={**link, 'status': 'start_failed', 'error': str(exc)})
                mark('journal_start_failed', error=str(exc))
                return 125, record
        with ExitStack() as stack:
            source = stack.enter_context(stdin.open('rb')) if stdin else subprocess.DEVNULL
            stdout = stack.enter_context((output / 'stdout.log').open('xb'))
            stderr = stack.enter_context((output / 'stderr.log').open('xb'))
            # AI_NOTE: 担当も同じ時計で残り時間を確認できるようにし、親から古いUTC期限を継承しない。
            environment = {**os.environ, 'SVDECK_RUN_DIR': str(output),
                           'SVDECK_BUDGET_CLOCK': clock,
                           'SVDECK_DEADLINE_MONOTONIC': str(clock_start + timeout)}
            environment.pop('SVDECK_DEADLINE_UTC', None)
            if clock == 'deadline':
                environment['SVDECK_DEADLINE_UTC'] = deadline.isoformat()
            if journal is not None and (interrupted is not None or time.monotonic() - clock_start >= timeout
                                       or (clock == 'deadline' and datetime.now(timezone.utc) >= deadline)):
                raise JournalStartExpired('開始記録中に実行期限または停止要求へ到達したため担当は未起動')
            process = subprocess.Popen(command, cwd=cwd, stdin=source, stdout=stdout, stderr=stderr,
                                       start_new_session=True, env=environment)
            record.update(status='running', worker_pid=process.pid)
            mark('launched')
            while True:
                if interrupted is not None:
                    record['status'] = 'interrupted'
                    exit_code = 128 + interrupted
                    mark('interruption_observed', signal=interrupted)
                    break
                elapsed_expired = time.monotonic() - clock_start >= timeout
                utc_expired = clock == 'deadline' and datetime.now(timezone.utc) >= deadline
                if elapsed_expired or utc_expired:
                    record['status'] = 'timed_out'
                    exit_code = 124
                    mark('deadline_observed', elapsed_expired=elapsed_expired, utc_expired=utc_expired)
                    break
                code = process.poll()
                if code is not None:
                    record['status'] = 'completed' if code == 0 else 'failed'
                    exit_code = code if code >= 0 else 128 - code
                    mark('worker_exit_observed', returncode=code)
                    break
                if finish_check is not None:
                    try:
                        candidate = finish_check()
                    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                        record['finish_error'] = str(exc)
                        if interrupted is not None or time.monotonic() - clock_start >= timeout or (clock == 'deadline' and datetime.now(timezone.utc) >= deadline):
                            continue
                        if process.poll() is not None:
                            continue
                        raise
                    if candidate is not None:
                        # AI_NOTE: 検査中の期限・中断・自然終了を先に裁き、要求の時刻だけで成功にしない。
                        if interrupted is not None or time.monotonic() - clock_start >= timeout or (clock == 'deadline' and datetime.now(timezone.utc) >= deadline):
                            continue
                        if process.poll() is not None:
                            continue
                        finish_evidence = candidate
                        record.update(status='finish_requested', finish_evidence=candidate)
                        mark('finish_request_verified', **candidate)
                        exit_code = 0
                        break
                time.sleep(min(0.1, max(0.001, timeout - (time.monotonic() - clock_start))))

            # AI_NOTE: 親が先に終わっても残った子処理を放置せず、猶予後に群全体へ終了を強制する。
            if finish_evidence is not None:
                # AI_NOTE: 終了要求の直前にも競合を確認し、先に起きた自然終了を保持する。
                if interrupted is not None:
                    record['status'], exit_code = 'interrupted', 128 + interrupted
                elif time.monotonic() - clock_start >= timeout or (clock == 'deadline' and datetime.now(timezone.utc) >= deadline):
                    record['status'], exit_code = 'timed_out', 124
                elif process.poll() is not None:
                    natural_code = process.returncode
                    assert natural_code is not None
                    record['status'] = 'completed' if natural_code == 0 else 'failed'
                    exit_code = natural_code if natural_code >= 0 else 128 - natural_code
                    mark('worker_exit_observed', returncode=natural_code)
            if record['status'] == 'finish_requested':
                own_termination = signal_group(process, signal.SIGTERM, require_running=True)
                # AI_NOTE: 送信内部で先に見えた自然終了を、自分の信号の結果へ読み替えない。
                if process.returncode is not None:
                    natural_code = process.returncode
                    record['status'] = 'completed' if natural_code == 0 else 'failed'
                    exit_code = natural_code if natural_code >= 0 else 128 - natural_code
                    mark('worker_exit_observed', returncode=natural_code)
                sent = own_termination
            else:
                sent = signal_group(process, signal.SIGTERM)
            if sent:
                mark('termination_requested', signal=int(signal.SIGTERM))
                stop_clock = time.monotonic()
                stop_deadline = datetime.now(timezone.utc) + timedelta(seconds=grace)
                while (time.monotonic() - stop_clock < grace
                       and datetime.now(timezone.utc) < stop_deadline):
                    process.poll()
                    if not signal_group(process, 0):
                        break
                    time.sleep(0.05)
                if signal_group(process, signal.SIGKILL):
                    mark('kill_requested', signal=int(signal.SIGKILL))
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                record['status'] = 'termination_unconfirmed'
                exit_code = 125
            record['worker_returncode'] = process.returncode
    except JournalStartExpired as exc:
        record.update(status='interrupted' if interrupted is not None else 'timed_out', error=str(exc))
        exit_code = 128 + interrupted if interrupted is not None else 124
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        record.update(status='launch_failed' if process is None else 'supervisor_failed', error=str(exc))
        exit_code = 127 if process is None else 125
    finally:
        if process is not None:
            # AI_NOTE: 保存失敗等で通常経路を抜けても、起動した処理群への停止要求を残す。
            try:
                signal_group(process, signal.SIGKILL)
            except OSError as exc:
                record.update(status='termination_unconfirmed', termination_error=str(exc))
                exit_code = 125
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                record['status'] = 'termination_unconfirmed'
                exit_code = 125
            record['worker_returncode'] = process.returncode
            if finish_check is not None:
                # AI_NOTE: 主PIDだけでなく元の群の消滅を確認し、残留を完了へ渡さない。
                try:
                    stop_clock = time.monotonic()
                    stop_utc = datetime.now(timezone.utc) + timedelta(seconds=1)
                    while signal_group(process, 0):
                        if time.monotonic() - stop_clock >= 1 or datetime.now(timezone.utc) >= stop_utc:
                            raise OSError('同じプロセス群の終了を確認できません')
                        time.sleep(0.05)
                    mark('process_group_gone')
                except OSError as exc:
                    record.update(status='termination_unconfirmed', termination_error=str(exc))
                    exit_code = 125
        if finish_evidence is not None and exit_code == 0:
            # AI_NOTE: 停止後の同一内容と期限内の最終確認でだけ明示完了を確定する。
            try:
                assert finish_check is not None
                if finish_check() != finish_evidence:
                    raise ValueError('停止後の完了要求が一致しません')
                if record['status'] == 'finish_requested':
                    if not own_termination or (process is not None and process.returncode not in (0, -signal.SIGTERM, -signal.SIGKILL)):
                        record['status'], exit_code = 'failed', 125
                    else:
                        record['status'] = 'finished_by_request'
                if interrupted is not None:
                    record['status'], exit_code = 'interrupted', 128 + interrupted
                elif time.monotonic() - clock_start >= timeout or (clock == 'deadline' and datetime.now(timezone.utc) >= deadline):
                    record['status'], exit_code = 'timed_out', 124
                if exit_code == 0:
                    mark('finish_confirmed', **finish_evidence)
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                record.update(status='finish_invalid', error=str(exc))
                exit_code = 125
                if interrupted is not None:
                    record['status'], exit_code = 'interrupted', 128 + interrupted
                elif time.monotonic() - clock_start >= timeout or (clock == 'deadline' and datetime.now(timezone.utc) >= deadline):
                    record['status'], exit_code = 'timed_out', 124
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    record.update(ended_at=datetime.now(timezone.utc).isoformat(),
                  elapsed_seconds=time.monotonic() - clock_start, runner_returncode=exit_code)
    mark('supervisor_finished')
    if journal is not None:
        record['execution_returncode'] = exit_code
        try:
            record['journal_sync'] = journal.finish(record)
            mark('journal_finished')
        except JOURNAL_ERRORS as exc:
            link = record['journal_sync']
            assert isinstance(link, dict)
            record['journal_sync'] = {**link, 'status': 'finish_failed', 'error': str(exc)}
            if exit_code == 0:
                exit_code = 125
            record['runner_returncode'] = exit_code
            mark('journal_finish_failed', error=str(exc))
    return exit_code, record


def main(argv: list[str] | None = None) -> int:
    # AI_NOTE: コマンドを引数列のまま渡し、シェル展開と既存の記録先の上書きを避ける。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='新しい実行記録ディレクトリ')
    parser.add_argument('--timeout', type=float, required=True, help='作業の制限秒数')
    parser.add_argument('--grace', type=float, default=2, help='終了要求から強制終了までの猶予秒数')
    parser.add_argument('--cwd', type=Path)
    parser.add_argument('--stdin', type=Path, help='担当へ渡す入力ファイル')
    parser.add_argument('--clock', choices=('deadline', 'elapsed'), default='deadline',
                        help='deadline: UTCと経過時計の早い期限 / elapsed: 経過時計だけで制限')
    parser.add_argument('--journal-root', type=Path, help='工程を反映する本体リポジトリ')
    parser.add_argument('--experiment-id', help='登録済み試行のID（台帳接続時は必須）')
    parser.add_argument('--stage-id', help='登録済み未着手工程のID（実行ごとに新しいID）')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    try:
        target = (args.journal_root, args.experiment_id, args.stage_id)
        if any(v is not None for v in target) and not all(target):
            raise ValueError('台帳接続は --journal-root / --experiment-id / --stage-id の3つを指定してください')
        journal = RunJournal(*target) if all(target) else None
        code, record = run(command, args.output, args.timeout, args.grace, args.cwd, args.stdin, args.clock, journal)
    except (OSError, ValueError, OverflowError) as exc:
        print(f'実行入力エラー: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(record, ensure_ascii=False, indent=2))
    sync = record.get('journal_sync')
    if isinstance(sync, dict) and sync.get('error'):
        print('台帳反映に失敗しました。run.jsonを確認し、停止済みなら svdeck.worker_journal で再反映できます。', file=sys.stderr)
    return code


if __name__ == '__main__':
    sys.exit(main())
