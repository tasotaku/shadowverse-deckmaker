"""Reuse the verified public report runner with the fixed intermediate instructions."""
from pathlib import Path
import importlib.util
import json
import sys

root = Path(__file__).resolve().parents[3]
folder = Path(__file__).resolve().parent
arm = sys.argv[1]
assert arm in ('A', 'B')
protocol = json.loads((folder / 'protocol.json').read_text())
spec = importlib.util.spec_from_file_location('fragment_scout', root / 'evals/discovery/fragment-handoff-01/scout-run.py')
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
setattr(module, 'PURPOSE', protocol['purpose'])
setattr(module, 'INSTRUCTION', protocol['common_instruction'] + '\n' + protocol['arms'][arm])
result = module.run(Path(protocol['source']), Path('/tmp/fragment-handoff-02-' + arm.lower() + '-intermediate'), Path('/Applications/ChatGPT.app/Contents/Resources/codex'), 300, root, protocol['id'], arm.lower() + '-intermediate')
print(json.dumps({key: result.get(key) for key in ('status', 'started_at', 'ended_at', 'submission', 'failure')}, ensure_ascii=False))
raise SystemExit(0 if result['status'] == 'completed' else 2)
