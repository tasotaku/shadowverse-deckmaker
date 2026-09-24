"""Independent JSON consumer; endpoint projection written solely from public docs.
Imports only standard library and permitted independent oracle for witness replay.
"""
import copy, hashlib, json, sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'scripts'))
from turn_frontier_reference import all_outcomes, action_signature
OUT=ROOT/'output/turn-search-max-acceptance-final/small-delivered'
HERE=Path(__file__).parent
def js(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def statekey(s):
    s=copy.deepcopy(s);s.pop('rng',None)
    for p in s['players']:
        p['destroyed']=sorted(p['destroyed'])
        for zone in ('hand','board','deck'):
            for e in p[zone]:
                if isinstance(e,dict):e['keywords']=sorted(e.get('keywords',[]))
    return js(s)
def endpoint(s,cards):
    owner=s['active_player'];players=[s['players'][owner],s['players'][1-owner]]
    boards=[]; vals=[players[0]['health'],-players[1]['health'],players[0]['pp'],players[0]['ep'],players[0]['sep']]
    for i,p in enumerate(players):
        board=[]
        for e in p['board']:
            behavior={k:v for k,v in cards[e['card_id']].items() if k not in {'id','card_id','name','text','class_name','synthetic','cost','attack','health','max_health'}}
            if 'keywords' in behavior:behavior['keywords']=sorted(behavior['keywords'])
            traits={k:v for k,v in e.items() if k not in {'id','card_id','name','attack','health','max_health'}}
            traits['keywords']=sorted(traits.get('keywords',[]))
            board.append([behavior,traits])
            vals.extend([(-1 if i else 1)*e[k] for k in ('attack','health','max_health')])
        boards.append(board)
    hand=[]
    for e in players[0]['hand']:
        e=copy.deepcopy(e);e['keywords']=sorted(e.get('keywords',[]));hand.append(js(e))
    return (js([s['winner'],boards]),tuple(vals),tuple(sorted(hand)))
def skyline(keys):
    keys=set(keys);out=set()
    for x in keys:
        dominated=False
        for y in keys:
            if x==y or x[0]!=y[0]:continue
            if all(a>=b for a,b in zip(y[1],x[1])) and Counter(y[2])>=Counter(x[2]):dominated=True;break
        if not dominated:out.add(x)
    return out
def serialkeys(xs): return sorted([list(x) for x in xs],key=js)
def replay(initial,cards,steps):
    state=initial
    for step in steps:
        matches=[o for o in all_outcomes(state,cards,step['action']) if o.choices==tuple(step.get('draws',step.get('choices',[])))]
        assert len(matches)==1
        state=matches[0].state
    return state
def main():
    cases=json.loads((ROOT/'docs/evidence/turn-search-compare/independent-small-cases.v1.json').read_text(encoding='utf8'))
    oracles=json.loads((ROOT/'docs/evidence/turn-search-compare/acceptance-t1/oracle.json').read_text(encoding='utf8'))
    observations=[];failures=[]
    for idx,(case,oracle) in enumerate(zip(cases,oracles)):
        os={x['id']:x['state'] for x in oracle['states']}
        expected_states={statekey(x) for x in os.values()}
        expected_candidates=skyline(endpoint(x,case['cards']) for x in os.values())
        oe=defaultdict(Fraction)
        rawdraw=defaultdict(Fraction)
        for e in oracle['edges']:
            key=(statekey(os[e['source']]),js(e['action']),statekey(os[e['target']]))
            oe[key]+=Fraction(e['probability']);rawdraw[key+(tuple(e['choices']),)]+=Fraction(e['probability'])
        for algorithm in ('native',):
            p=OUT/f'case-{idx:03d}'/algorithm/'trial-1/result.json'
            r=json.loads(p.read_text(encoding='utf8'));nodes=r['debug_nodes']
            states={statekey(n['state']) for n in nodes}
            candidates={endpoint(n['state'],case['cards']) for n in nodes if n['candidate']}
            actual_edges=defaultdict(Fraction);actual_draws=defaultdict(Fraction);mass=[];replays=[]
            for n in nodes:
                replayed=replay(r['record']['initial'],r['record']['cards'],n['witness'])
                replays.append(statekey(replayed)==statekey(n['state']))
                for c in n['conditional']:
                    mass.append(sum((Fraction(o['probability']) for o in c['outcomes']),Fraction())==1)
                    for o in c['outcomes']:
                        key=(statekey(n['state']),js(c['action']),statekey(o['state']))
                        actual_edges[key]+=Fraction(o['probability']);actual_draws[key+(tuple(o['draws']),)]+=Fraction(o['probability'])
            witnesses=[]
            for w in case.get('witnesses',[]):
                target=replay(r['record']['initial'],r['record']['cards'],w['steps'])
                cursor=statekey(r['record']['initial']);valid=True
                for step in w['steps']:
                    sn=next(n for n in nodes if statekey(n['state'])==cursor)
                    c=next(c for c in sn['conditional'] if c['action']==step['action'])
                    o=next(o for o in c['outcomes'] if o['draws']==step.get('choices',[]))
                    cursor=statekey(o['state'])
                valid &= cursor==statekey(target)
                witnesses.append({'id':w['id'],'public_path_equals_oracle':valid,'target_state':json.loads(cursor),'endpoint_is_candidate':endpoint(target,case['cards']) in candidates})
            checks={'complete':all(r[k] is True for k in ('complete','enumeration_complete','frontier_complete')),'all_states_exact':states==expected_states,'candidate_set_exact':candidates==expected_candidates,'all_action_outcome_distributions_exact':dict(actual_edges)==dict(oe),'all_draw_paths_exact':dict(actual_draws)==dict(rawdraw),'every_action_mass_one':all(mass),'every_debug_witness_replays':all(replays),'every_fixture_witness_replays':all(w['public_path_equals_oracle'] for w in witnesses),'root_present':statekey(os[oracle['root']]) in states,'own_turn_only':all(n['state']['active_player']==os[oracle['root']]['active_player'] and [p['turn'] for p in n['state']['players']]==[p['turn'] for p in os[oracle['root']]['players']] for n in nodes) and all(json.loads(k[1])['type']!='end_turn' for k in actual_edges)}
            details={'case':case['id'],'algorithm':algorithm,'checks':checks,'actual_states':len(states),'oracle_states':len(expected_states),'actual_candidates':len(candidates),'oracle_candidates':len(expected_candidates),'missing_states':[json.loads(x) for x in sorted(expected_states-states)],'extra_states':[json.loads(x) for x in sorted(states-expected_states)],'missing_candidates':serialkeys(expected_candidates-candidates),'extra_candidates':serialkeys(candidates-expected_candidates),'witnesses':witnesses,'conditional_groups':len(mass),'witness_replays':len(replays),'result_path':str(p),'candidate_semantic_sha256':r['candidate_semantic_sha256']}
            observations.append(details)
            failures.extend({'case':case['id'],'algorithm':algorithm,'check':k} for k,v in checks.items() if not v)
    (HERE/'observations.json').write_text(json.dumps({'observations':observations,'failures':failures},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'comparisons':len(observations),'failures':failures},ensure_ascii=False))
if __name__=='__main__': main()

