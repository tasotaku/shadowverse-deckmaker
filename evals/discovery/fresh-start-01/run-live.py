from pathlib import Path
from datetime import datetime, timezone
import json, subprocess, sys
from svdeck import discovery
from svdeck.discovery_evidence import digest

project = Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker')
folder = project / 'evals/discovery/fresh-start-01'
config = json.loads((folder / 'live-input-protocol.json').read_text())
output = Path(config['output'])
state_path = output.parent / (output.name + '-continuation.json')
assert not output.exists() and not state_path.exists()
state = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'running', 'scope': '初回考案と別評価を一度。test/unconfirmedの場合だけ既存の後続調査を一度。', 'source': config['session'], 'output': str(output)}

def save():
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')

save()
base = [sys.executable, '-B', '-m', 'svdeck.discovery_run', config['session'], str(output), '--codex', '/Applications/ChatGPT.app/Contents/Resources/codex', '--develop-seconds', str(config['develop_seconds']), '--review-seconds', str(config['review_seconds']), '--explicit-finish', '--journal-root', str(project), '--experiment-id', 'fresh-start-01', '--stage-prefix', 'live']
state['command'] = base
save()
first = subprocess.run(base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
state['first_returncode'] = first.returncode
state['first_ended_at'] = datetime.now(timezone.utc).isoformat()
state['runner_stderr'] = first.stderr
if first.returncode != 0:
    state['status'] = 'first_failed'
else:
    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == 'completed'
    report = discovery.report(output / 'session')
    assert len(report['revisions']) == 1 and len(report['revisions'][0]['reviews']) == 1
    review = report['revisions'][0]['reviews'][0]
    state['judgment'] = {key: review[key] for key in ['procedure', 'value', 'novelty']}
    if review['value'] == 'test' and review['novelty'] == 'unconfirmed':
        state['status'] = 'followup_running'
        followup = output.parent / (output.name + '-novelty')
        command = [sys.executable, '-B', '-m', 'svdeck.discovery_inquiry', str(output / 'session'), str(followup), '--codex', '/Applications/ChatGPT.app/Contents/Resources/codex', '--revision', '1', '--review-hash', digest(review), '--novelty', '--research-seconds', str(config['research_seconds_if_test_unconfirmed']), '--inspect-seconds', str(config['inspect_seconds_if_test_unconfirmed']), '--journal-root', str(project), '--experiment-id', 'fresh-start-01', '--stage-prefix', 'novelty']
        state['followup_command'] = command
        save()
        later = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        state['followup_returncode'] = later.returncode
        state['followup_runner_stderr'] = later.stderr
        state['status'] = 'completed' if later.returncode == 0 else 'followup_failed'
    else:
        state['status'] = 'completed'
        state['followup_reason'] = '保存評価がtest/unconfirmed条件外のため後続調査を開始しない。'
state['ended_at'] = datetime.now(timezone.utc).isoformat()
save()
print(json.dumps(state, ensure_ascii=False))
