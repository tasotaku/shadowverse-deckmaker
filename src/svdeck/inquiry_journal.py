"""Record an inquiry's terminal submission check separately from its workers."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from svdeck.worker_journal import RunJournal


class InquiryJournal(RunJournal):
    def finish(self, run: dict[str, object]) -> dict[str, Any]:
        # AI_NOTE: 担当の終了と最終提出検査を分け、全実行停止後も結果・採否を自動認定しない。
        link = run['journal_sync']
        if not isinstance(link, dict) or not isinstance(link.get('claimed_stage'), dict):
            raise ValueError('開始時の工程記録がなく、終了を反映できません')
        if not run.get('ended_at') or run.get('status') in {'preparing', 'inquiry', 'inspect'}:
            raise ValueError('全実行が終端状態になった記録だけを反映できます')
        executions = run.get('stages', [])
        stopped = isinstance(executions, list) and all(
            entry.get('run', {}).get('status') != 'termination_unconfirmed' for entry in executions)
        claimed = link['claimed_stage']
        desired = deepcopy(claimed)
        state = 'completed' if run['status'] == 'completed' else 'interrupted'
        summary = '調査・照合は提出確認まで完了。' if state == 'completed' else '調査・照合が途中で停止。'
        detail = summary + f"全実行の終了状態: {run['status']}。"
        if run.get('failure'):
            reason = f"停止理由: {run['failure']}。"
            detail += reason
            summary += reason
        if not stopped:
            detail += '担当または子処理の停止は未確認。'
        desired.update(status=state, ended_at=run['ended_at'],
                       note=claimed['note'] + '\n' + detail + '結果・採否は別途確認する。')

        def amend(record: dict[str, Any]) -> bool:
            # AI_NOTE: 同工程・終了済み記録の訂正を守り、別工程の変更だけ最新版へ合わせる。
            stage = self.stage(record)
            if stage == desired:
                return False
            if record['status'] in {'completed', 'interrupted'}:
                raise ValueError('終了済み試行の訂正を上書きしません')
            if stage != claimed:
                raise ValueError('開始後に同じ工程が変更されています。訂正を上書きしません')
            stage.update(desired)
            if stopped and record['status'] == 'running' and not any(s['status'] in {'running', 'waiting'} for s in record['stages']):
                record['status'] = 'waiting'
                if record['summary'] == link.get('claimed_summary'):
                    record['summary'] = summary + '結果・採否の確認待ち。'
            return True

        item = self.change(amend, '最終提出検査までの全実行の終了を反映。結果・採否は変更しない')
        return {**link, 'status': 'completed', 'end_revision': item['revision'],
                'synced_at': datetime.now(timezone.utc).isoformat()}
