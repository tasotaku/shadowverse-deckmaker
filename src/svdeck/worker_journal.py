"""Persist worker stage boundaries without performing journal I/O in its watchdog loop."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Callable
import uuid

from svdeck.journal_store import Conflict, Journal, instant

JOURNAL_ERRORS = (OSError, ValueError, KeyError, sqlite3.Error)


class RunJournal:
    def __init__(self, root: Path, experiment_id: str, stage_id: str) -> None:
        # AI_NOTE: 接続先だけ保持し、実行入力の検査前にDBを新設しない。
        self.root = root.resolve()
        self.experiment_id = experiment_id
        self.stage_id = stage_id

    def identity(self) -> dict[str, Any]:
        # AI_NOTE: 終了反映の再試行を、元の実行と同じ台帳・工程だけへ向ける。
        return {'root': str(self.root), 'experiment_id': self.experiment_id,
                'stage_id': self.stage_id}

    def change(self, amend: Callable[[dict[str, Any]], bool], reason: str) -> dict[str, Any]:
        # AI_NOTE: 他工程の更新は最新版へ合わせ、同じ工程への変更はamend側で拒否する。
        journal = Journal(self.root)
        for attempt in range(3):
            item = journal.get(self.experiment_id)
            if not amend(item['record']):
                return item
            try:
                return journal.save(item['record'], item['revision'], '担当の実行監視', reason)
            except Conflict:
                if attempt == 2:
                    raise
        raise AssertionError('journal retry loop did not return')

    def stage(self, record: dict[str, Any]) -> dict[str, Any]:
        # AI_NOTE: 意図しない工程を新設せず、利用者が登録した未着手の工程だけを使う。
        for stage in record['stages']:
            if stage['id'] == self.stage_id:
                result: dict[str, Any] = stage
                return result
        raise ValueError(f'指定した工程がありません: {self.stage_id}')

    def begin(self, run: dict[str, object]) -> dict[str, Any]:
        # AI_NOTE: 起動より先に工程を確保し、二重起動が同じ工程へ入るのを拒否する。
        def amend(record: dict[str, Any]) -> bool:
            # AI_NOTE: 開始時は結果や他工程を維持して、予定済みの担当区間だけを確保する。
            stage = self.stage(record)
            if record['status'] in {'completed', 'interrupted'}:
                raise ValueError('終了済み試行には担当を起動できません')
            if stage['status'] != 'planned' or stage['started_at'] or stage['ended_at']:
                raise ValueError('担当実行ごとに未着手の新しい工程IDを使ってください')
            stage.update(status='running', started_at=run['started_at'],
                         note=stage['note'] + '\n起動処理を開始。実行記録: ' + str(run['output']))
            was_planned = record['status'] == 'planned'
            record['status'] = 'running'
            observed = instant(run['started_at'])
            overall = instant(record['started_at'])
            # AI_NOTE: 同時起動の保存順が逆でも、実際に先に始まった工程を全体期間へ含める。
            if (overall is None and was_planned) or (overall is not None and observed is not None and observed < overall):
                record['started_at'] = run['started_at']
            # AI_NOTE: 保存確定後の応答だけ失敗しても、未起動の工程を同じ内容で後から閉じられるよう残す。
            run['journal_sync'] = {**self.identity(), 'status': 'starting',
                                   'claimed_stage': deepcopy(stage)}
            return True

        item = self.change(amend, '担当の起動処理を開始。結果・採否は変更しない')
        return {**self.identity(), 'status': 'running', 'begin_revision': item['revision'],
                'claimed_stage': deepcopy(self.stage(item['record']))}

    def finish(self, run: dict[str, object]) -> dict[str, Any]:
        # AI_NOTE: 実行結果を工程状態へ写すだけで、提出や探索成果の合格を作らない。
        link = run['journal_sync']
        if not isinstance(link, dict) or not isinstance(link.get('claimed_stage'), dict):
            raise ValueError('開始時の工程記録がなく、終了を反映できません')
        if run.get('ended_at') is None or run.get('status') in {'starting', 'running'}:
            raise ValueError('停止処理を終えた実行記録だけを反映できます')
        claimed = link['claimed_stage']
        desired = deepcopy(claimed)
        state = 'completed' if run['status'] in {'completed', 'finished_by_request'} else 'interrupted'
        detail = ('監視終了・子の停止未確認' if run['status'] == 'termination_unconfirmed'
                  else '担当の明示要求による停止と保存再検査を確認' if run['status'] == 'finished_by_request'
                  else '担当の停止処理を終了')
        desired.update(status=state, ended_at=run['ended_at'],
                       note=claimed['note'] + f"\n{detail}。実行状態: {run['status']}、"
                       f"担当終了番号: {run.get('worker_returncode')}。"
                       '提出の成否・有用性・採否は別途確認する。')

        def amend(record: dict[str, Any]) -> bool:
            # AI_NOTE: 終了の再反映は同じ結果なら無操作とし、手動訂正には追従しない。
            stage = self.stage(record)
            if stage == desired:
                return False
            if stage != claimed:
                raise ValueError('開始後に同じ工程が変更されています。訂正を上書きしません')
            stage.update(desired)
            return True

        item = self.change(amend, '担当の停止処理を終え、工程の実行結果と終了時刻を反映')
        return {**link, 'status': 'completed', 'end_revision': item['revision'],
                'synced_at': datetime.now(timezone.utc).isoformat()}


def main(argv: list[str] | None = None) -> int:
    # AI_NOTE: 再反映は保存済みの停止記録だけを使い、担当のコマンドは再実行しない。
    parser = argparse.ArgumentParser(description='停止済み担当の台帳反映だけを再試行する')
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args(argv)
    try:
        run = json.loads((args.run_dir / 'run.json').read_text())
        link = run['journal_sync']
        target = RunJournal(Path(link['root']), link['experiment_id'], link['stage_id'])
        result = target.finish(run)
        recovery = args.run_dir / f'journal-recovery-{uuid.uuid4().hex}.json'
        with recovery.open('x') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'record': str(recovery), 'journal_sync': result}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(f'台帳へ再反映できませんでした: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
