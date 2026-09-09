from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,subprocess,shutil

ROOT=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker')
RUN=Path('/tmp/sv-principles-scope-01');CODE=Path('/tmp/sv-principles-scope-prototype')
ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(CODE/'src')}
CMD=['/tmp/sv-system-venv/bin/python','-m','svdeck.discovery']
def now():return datetime.now(timezone.utc).isoformat()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def public(args,out):
    begin=now();r=subprocess.run(CMD+args,cwd=CODE,env=ENV,capture_output=True,text=True);end=now()
    with (RUN/'preparation-operations.jsonl').open('a') as f:f.write(json.dumps({'started_at':begin,'ended_at':end,'args':args,'exit_code':r.returncode,'stderr':r.stderr,'output':str(out)},ensure_ascii=False)+'\n')
    out.write_text(r.stdout)
    assert r.returncode==0,r.stderr
    return json.loads(r.stdout)

assert not (RUN/'protocol.json').exists(),'Inputs already fixed; do not regenerate'
assert not subprocess.check_output(['git','status','--porcelain'],cwd=CODE).strip(),'Prototype must be clean and tested first'
protocol=json.loads((RUN/'protocol-draft.json').read_text())
assert sha(Path(protocol['source_db']))==protocol['source_db_sha256']
start=now();indices={};contexts={}
for name in ('design.md','rules.md'):
    (RUN/'common').mkdir(exist_ok=True);shutil.copyfile(CODE/'docs'/name,RUN/'common'/name)
shutil.copyfile(CODE/'README.md',RUN/'common/operator-readme.md')
for case in protocol['cases']:
    for arm,mode in [('a','legacy'),('b','scoped')]:
        label=case['id']+'/'+arm;directory=RUN/label;directory.mkdir(parents=True,exist_ok=True);session=directory/'session'
        response=public(['start',str(session),'--db',protocol['source_db'],'--class',case['class_name'],'--format',protocol['format'],'--objective',protocol['objective'],'--principles-scope',mode],directory/'start.json')
        public(['attach',str(session),str(RUN/'reference-sources.json')],directory/'attach.json')
        packet=public(['packet',str(session),'--stage','develop','--revision','0'],directory/'initial-packet.json')
        context=json.loads((session/'context.json').read_text())['data'];contexts[label]=context
        indices[label]={'session':str(session),'packet_hash':packet['sha256'],'packet':str(directory/'initial-packet.json'),'context_hash':response['context_sha256'],'eligible_cards':response['eligible_cards'],'related_cards':response['related_cards'],'source_count':len(packet['data']['sources'])}
    a=contexts[case['id']+'/a'];b=contexts[case['id']+'/b']
    differences=[k for k in set(a)|set(b) if a.get(k)!=b.get(k)]
    assert set(differences)<={'captured_at','principles_scope_version','principles_scope_guide'},differences
    assert a['principles']==b['principles']
    pa=json.loads((RUN/case['id']/'a/initial-packet.json').read_text())['data']
    pb=json.loads((RUN/case['id']/'b/initial-packet.json').read_text())['data']
    assert pa['sources']==pb['sources'], 'reference corpus differs'
    assert not any(k.startswith('principles_scope_') for k in a)
    assert b['principles_scope_version']=='scoped-v1' and b['principles_scope_guide']
    protocol.setdefault('input_differences',{})[case['id']]=differences
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=CODE,text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain'],cwd=CODE).strip()
protocol.update(status='fixed_before_natural_trial',fixed_at=now(),prototype_commit=commit,input_sessions=indices)
save(RUN/'protocol.json',protocol)
files=[RUN/'protocol.json',RUN/'reference-sources.json']+list((RUN/'common').glob('*'))
for row in indices.values():files.extend([Path(row['packet']),Path(row['session'])/'context.json',Path(row['session'])/'snapshot.db'])
files.extend(CODE/'src/svdeck'/p.name for p in (CODE/'src/svdeck').glob('discovery*.py'))
manifest={'fixed_at':protocol['fixed_at'],'files':{str(p):sha(p) for p in files}}
save(RUN/'manifest.json',manifest);save(RUN/'input-check.json',{'started_at':start,'finished_at':now(),'prototype_commit':commit,'indices':indices,'same_original_principles':True,'same_cards_notes_rules_keywords_sources':True,'differences':protocol['input_differences'],'frozen_file_count':len(files),'limitation':'Input identity only, not useful output.'})
print(json.dumps({'fixed_at':protocol['fixed_at'],'code':commit,'sessions':indices,'frozen_files':len(files)},ensure_ascii=False))
