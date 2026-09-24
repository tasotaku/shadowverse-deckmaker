import json
from pathlib import Path

base = Path('docs/evidence/turn-search-max/acceptance-final')
paths = [base/'commands.jsonl', base/'final-source-integrity.json', base/'worker-schedule.json', base/'hard-0-delivered.processes.json', base/'observations.json',base/'public-witnesses.json',base/'harness-diagnostics.json',Path('docs/evidence/turn-search-compare/acceptance-t1/oracle.json'),Path('output/turn-search-max-acceptance-final/small-delivered/case-000/native/trial-1/result.json'),Path('output/turn-search-max-acceptance-final/hard-0-delivered/case-000/native/trial-1/report.json'),Path('output/turn-search-max-acceptance-final/hard-0-delivered/summary.json'),Path('output/turn-search-max-acceptance-final/hard-0-delivered/manifest.json')]
for p in paths:
    data = json.loads(p.read_text(encoding='utf-8').splitlines()[0]) if p.suffix == '.jsonl' else json.loads(p.read_text(encoding='utf-8'))
    print('\nPATH', p)
    if isinstance(data,list):
        print('LIST',len(data)); print(json.dumps(data[:1],ensure_ascii=False)[:5500])
    else:
        print('KEYS',list(data))
        print(json.dumps({k:(v[:1] if isinstance(v,list) else v) for k,v in data.items()},ensure_ascii=False)[:9000])
