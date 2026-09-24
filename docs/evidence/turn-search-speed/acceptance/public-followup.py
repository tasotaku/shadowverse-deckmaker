import copy,json,subprocess,sys,time
from pathlib import Path
from fractions import Fraction
from consume import ROOT,HERE,OUT,statekey,replay
PY=ROOT/'.venv/Scripts/python.exe'
cmds=[];events=[]
def run(args,stem):
    cmd=[str(PY),'-X','utf8','-m','svdeck.battle_frontier_compare',*map(str,args)]
    start=time.time();r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf8',timeout=60)
    cmds.append({'command':subprocess.list2cmdline(cmd),'started_unix':start,'seconds':time.time()-start,'returncode':r.returncode})
    (HERE/f'{stem}.stdout.txt').write_text(r.stdout,encoding='utf8');(HERE/f'{stem}.stderr.txt').write_text(r.stderr,encoding='utf8')
    return r
for algorithm in ('native',):
    result=OUT/'case-008'/algorithm/'trial-1/result.json'
    rootpath=HERE/f'adaptive-{algorithm}-root.json'
    run(['--expand',result,'--output',rootpath],f'adaptive-{algorithm}-root')
    root=json.loads(rootpath.read_text(encoding='utf8'))
    random=next(c for c in root['choices'] if c['action']=={'type':'play','card':'random'})
    for idx,o in enumerate(random['outcomes']):
        observed=HERE/f'adaptive-{algorithm}-{idx}-state.json';observed.write_text(json.dumps(o['state']),encoding='utf8')
        branchpath=HERE/f'adaptive-{algorithm}-{idx}-choices.json'
        run(['--expand',result,'--state',observed,'--output',branchpath],f'adaptive-{algorithm}-{idx}')
        branch=json.loads(branchpath.read_text(encoding='utf8'))
        # With both alive remove exposed; if random killed exposed remove protected.
        target='exposed' if any(e['id']=='exposed' for e in o['state']['players'][1]['board']) else 'protected'
        choice=next(c for c in branch['choices'] if c['action']=={'type':'play','card':'remove','target':target})
        steps=[{'action':random['action'],'draws':o['draws']},{'action':choice['action'],'draws':choice['outcomes'][0]['draws']}]
        sp=HERE/f'adaptive-{algorithm}-{idx}-steps.json';sp.write_text(json.dumps(steps),encoding='utf8')
        final=HERE/f'adaptive-{algorithm}-{idx}-replayed.json'
        run(['--expand',result,'--steps',sp,'--output',final],f'adaptive-{algorithm}-{idx}-replayed')
        end=json.loads(final.read_text(encoding='utf8'))
        events.append({'algorithm':algorithm,'observed_draws':o['draws'],'probability':o['probability'],'chosen_followup':choice['action'],'legal_choices':branch['choices'],'stop_offered':branch['stop'],'replayed_equals_observed_followup':statekey(end['state'])==statekey(choice['outcomes'][0]['state']),'remaining_enemy_ids':[e['id'] for e in end['state']['players'][1]['board']]})
# Validate every compact candidate via documented expansion and conditional witness.
candidate_checks=[]
for idx in range(9):
    for algorithm in ('native',):
        path=OUT/f'case-{idx:03d}'/algorithm/'trial-1/result.json';r=json.loads(path.read_text(encoding='utf8'))
        for sample in r['witness_samples']:
            c=sample['candidate'];output=HERE/f'candidate-{idx}-{algorithm}-{c}.json'
            proc=run(['--expand',path,'--candidate',c,'--output',output],f'candidate-{idx}-{algorithm}-{c}')
            expanded=json.loads(output.read_text(encoding='utf8'))
            expected=replay(r['record']['initial'],r['record']['cards'],sample['steps'])
            candidate_checks.append({'case':r['case_id'],'algorithm':algorithm,'candidate':c,'equals_witness':statekey(expected)==statekey(expanded['state']),'stop':expanded['stop'],'path':str(output)})
(HERE/'followup-observations.json').write_text(json.dumps({'adaptive':events,'candidate_expansion':candidate_checks},ensure_ascii=False,indent=2),encoding='utf8')
(HERE/'public-followup-commands.json').write_text(json.dumps(cmds,indent=2),encoding='utf8')
print(json.dumps({'adaptive_branches':len(events),'candidate_expansions':len(candidate_checks),'all_pass':all(x['replayed_equals_observed_followup'] and x['stop_offered'] for x in events) and all(x['equals_witness'] and x['stop'] for x in candidate_checks)}))
