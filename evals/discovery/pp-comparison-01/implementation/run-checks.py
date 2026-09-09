from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

folder = Path('/tmp/sv-pp-comparison-01/implementation')
worktree = Path('/tmp/sv-pp-comparison-prototype')
env = {**os.environ, 'PYTHONPATH': str(worktree / 'src') + ':' + str(worktree / 'tests')}
python = '/tmp/sv-system-venv/bin/python'
commands = [
    ('mypy', [python, '-m', 'mypy', '--follow-imports=silent', 'src/svdeck/discovery.py',
              'src/svdeck/discovery_evidence.py', 'src/svdeck/discovery_read.py', 'src/svdeck/discovery_sources.py',
              'src/svdeck/discovery_compare.py', 'src/svdeck/discovery_resources.py', 'src/svdeck/explore.py']),
    ('related-tests', [python, '-m', 'pytest', *map(str, sorted(Path('tests').glob('test_discovery*.py'))), '-q']),
    ('diff-check', ['git', 'diff', '--check']),
]
records = []
for label, command in commands:
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, cwd=worktree, env=env, text=True, capture_output=True)
    ended = datetime.now(timezone.utc).isoformat()
    record = dict(label=label, command=command, started_at=started, ended_at=ended,
                  returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    records.append(record)
    (folder / f'{label}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(label, result.returncode, result.stdout.strip(), result.stderr.strip())
(folder / 'checks.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
if any(record['returncode'] for record in records):
    raise SystemExit(1)
