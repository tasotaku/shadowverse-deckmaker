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
import subprocess
import sys
import time
from types import FrameType


def save_record(path: Path, record: dict[str, object]) -> None:
    # AI_NOTE: 読取り側へ途中のJSONを見せず、前の状態か次の状態を一度に渡す。
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def signal_group(process: subprocess.Popen[bytes], sig: int) -> bool:
    # AI_NOTE: 終了直後の群は親の回収後も一時的にEPERMになり得るため、短い上限内で再確認する。
    for attempt in range(5):
        process.poll()
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
        cwd: Path | None = None, stdin: Path | None = None) -> tuple[int, dict[str, object]]:
    # AI_NOTE: 判定の中身に触れず、実行の期限・終了確認と既存出力の保持だけを担当する。
    if os.name != 'posix':
        raise ValueError('この入口のプロセス群制御はPOSIX専用です')
    if not command or not command[0]:
        raise ValueError('実行コマンドが必要です')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeoutは有限の正の秒数が必要です')
    if not math.isfinite(grace) or grace < 0:
        raise ValueError('graceは有限の0以上の秒数が必要です')
    started = datetime.now(timezone.utc)
    deadline = started + timedelta(seconds=timeout)
    clock_start = time.monotonic()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    events: list[dict[str, object]] = []
    record: dict[str, object] = {
        'status': 'starting', 'command': command, 'cwd': str((cwd or Path.cwd()).resolve()),
        'stdin': str(stdin.resolve()) if stdin else None, 'output': str(output),
        'started_at': started.isoformat(), 'deadline_at': deadline.isoformat(),
        'timeout_seconds': timeout, 'termination_grace_seconds': grace,
        'supervisor_pid': os.getpid(), 'worker_pid': None, 'worker_returncode': None,
        'ended_at': None, 'events': events,
        'limits': 'Elapsed clocks include waiting; not CPU time. Host suspension can delay observation. '
                  'Only descendants remaining in the original process group are controlled. '
                  'Partial output is not a completed proposal or review.'}
    record_path = output / 'run.json'

    def mark(event: str, **fields: object) -> None:
        # AI_NOTE: 終了要求と確認の時点を別々に記録し、欠けた工程時刻を補わない。
        events.append({'event': event, 'at': datetime.now(timezone.utc).isoformat(),
                       'elapsed_seconds': time.monotonic() - clock_start, **fields})
        save_record(record_path, record)

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
        with ExitStack() as stack:
            source = stack.enter_context(stdin.open('rb')) if stdin else subprocess.DEVNULL
            stdout = stack.enter_context((output / 'stdout.log').open('xb'))
            stderr = stack.enter_context((output / 'stderr.log').open('xb'))
            process = subprocess.Popen(command, cwd=cwd, stdin=source, stdout=stdout, stderr=stderr,
                                       start_new_session=True,
                                       env={**os.environ, 'SVDECK_RUN_DIR': str(output),
                                            'SVDECK_DEADLINE_UTC': deadline.isoformat()})
            record.update(status='running', worker_pid=process.pid)
            mark('launched')
            while True:
                if interrupted is not None:
                    record['status'] = 'interrupted'
                    exit_code = 128 + interrupted
                    mark('interruption_observed', signal=interrupted)
                    break
                if time.monotonic() - clock_start >= timeout or datetime.now(timezone.utc) >= deadline:
                    record['status'] = 'timed_out'
                    exit_code = 124
                    mark('deadline_observed')
                    break
                code = process.poll()
                if code is not None:
                    record['status'] = 'completed' if code == 0 else 'failed'
                    exit_code = code if code >= 0 else 128 - code
                    mark('worker_exit_observed', returncode=code)
                    break
                time.sleep(min(0.1, max(0.001, timeout - (time.monotonic() - clock_start))))

            # AI_NOTE: 親が先に終わっても残った子処理を放置せず、猶予後に群全体へ終了を強制する。
            if signal_group(process, signal.SIGTERM):
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
    except OSError as exc:
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
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    record.update(ended_at=datetime.now(timezone.utc).isoformat(),
                  elapsed_seconds=time.monotonic() - clock_start, runner_returncode=exit_code)
    mark('supervisor_finished')
    return exit_code, record


def main(argv: list[str] | None = None) -> int:
    # AI_NOTE: コマンドを引数列のまま渡し、シェル展開と既存の記録先の上書きを避ける。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='新しい実行記録ディレクトリ')
    parser.add_argument('--timeout', type=float, required=True, help='作業の制限秒数')
    parser.add_argument('--grace', type=float, default=2, help='終了要求から強制終了までの猶予秒数')
    parser.add_argument('--cwd', type=Path)
    parser.add_argument('--stdin', type=Path, help='担当へ渡す入力ファイル')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    try:
        code, record = run(command, args.output, args.timeout, args.grace, args.cwd, args.stdin)
    except (OSError, ValueError, OverflowError) as exc:
        print(f'実行入力エラー: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
