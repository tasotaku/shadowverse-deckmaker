"""Reproducible CPU training, paired evaluation and inspectable AI replays."""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .battle import Battle, catalog, fingerprint, replay
from .battle_ai import BASE_WEIGHTS, MODEL_PATH, Player, load_weights, model_hash
from .battle_decks import new_match
from .combat_benchmark import peak_memory

Json = dict[str, Any]
DECKS = ('ramp-dragon', 'last-words-nightmare')


def game(job: Json) -> Json:
    # AI_NOTE: 同じ初期seed・席で比較し、予算と実際の探索範囲を保存して未完了を勝敗へ混ぜない。
    started = time.perf_counter()
    initial = new_match(job['decks'][0], job['decks'][1], seed=job['seed'])
    battle = Battle(initial.state, initial.cards, record=job.get('record', False))
    challenger = job['seat']
    players = []
    for seat in range(2):
        policy = job['policy'] if seat == challenger else job['opponent']
        options = dict(job.get('options', {})) if policy in ('roles', 'lookahead') else {}
        if policy != 'roles':
            options.pop('role_k', None)
        players.append(Player(battle.cards, policy, weights=job.get('weights' if seat == challenger else 'opponent_weights'),
                              seed=20+seat, **options))
    times: list[float] = []
    decisions: list[Json] = []
    depths: dict[str, list[int]] = {}
    cutoffs: dict[str, int] = {}
    coverage: list[Json] = []
    nodes = 0
    limited = 0
    for count in range(job.get('max_actions', 500)):
        if battle.state['winner'] is not None:
            break
        owner = battle.state['active_player']
        decision_started = time.perf_counter()
        decision = players[owner].choose(battle.observation(owner))
        elapsed_ms = (time.perf_counter()-decision_started)*1000
        if decision['action'] not in battle.legal_actions():
            raise AssertionError('AIが不合法手を選択しました')
        battle.step(decision['action'])
        times.append(elapsed_ms)
        nodes += decision['nodes']
        depths.setdefault(decision.get('depth_unit', 'actions'), []).append(decision['depth'])
        limited += bool(decision.get('limited'))
        for kind, amount in decision.get('cutoffs', {}).items():
            cutoffs[kind] = cutoffs.get(kind, 0)+amount
        role_search = decision.get('role_search')
        if role_search:
            coverage.append({'action_index': count, 'seat': owner, 'available': role_search['available'],
                             'role_k': role_search['role_k'], 'coverage_exact': role_search.get('coverage_exact'),
                             'candidate_count': len(role_search.get('candidates', [])), 'goals': role_search.get('goals', []),
                             'roles': sorted({role for candidate in role_search.get('candidates', []) for role in candidate.get('roles', [])})})
        if job.get('save_decisions') or job['policy'] in ('roles', 'lookahead') or job['opponent'] in ('roles', 'lookahead'):
            decisions.append({'action_index': count, 'seat': owner, 'wall_ms': elapsed_ms, 'decision': decision})
        if battle.recording:
            battle.frames[-1]['decision'] = decision
    winner = battle.state['winner']
    peak, memory_method = peak_memory()
    result: Json = {k:job[k] for k in ('seed','decks','seat','policy','opponent')}
    result.update(winner=winner, result='unfinished' if winner is None else 'draw' if winner==-1 else 'win' if winner==challenger else 'loss',
                  actions=len(times), seconds=round(time.perf_counter()-started,3), nodes=nodes,
                  mean_decision_ms=round(sum(times)/len(times),3) if times else 0,
                  completed=winner is not None, stop_reason='terminal' if winner is not None else 'max_actions',
                  options=job.get('options', {}), max_actions=job.get('max_actions', 500),
                  actual_depth={unit: {'min': min(values), 'max': max(values), 'mean': sum(values)/len(values)} for unit, values in depths.items()},
                  limited_decisions=limited, cutoffs=cutoffs, role_coverage=coverage,
                  peak_rss_bytes=peak, memory_method=memory_method, memory_scope='whole worker process lifetime; includes earlier jobs in this worker',
                  timing_scope='game setup and decision/action loop; decision wall_ms measured around public choose call')
    if decisions:
        result['decisions'] = decisions
    if battle.recording:
        record = battle.export()
        record['meta'] = {'title': 'AI対戦 · ' + ' vs '.join(job['decks']),
                          'ai': {'policy':job['policy'],'opponent':job['opponent'],'seed':job['seed'],
                                 'weights':players[challenger].weights, 'options':job.get('options', {}),
                                 'seat':challenger, 'information':'public observation only'}}
        if replay(record).state != battle.state:
            raise AssertionError('保存再生の最終状態が一致しません')
        result['record'] = record
    return result


def jobs(seeds: list[int], policy: str, opponent: str, weights: dict[str,float] | None = None,
         decks: tuple[str, str] | None = None, seats: tuple[int, ...] = (0, 1), options: Json | None = None) -> list[Json]:
    # AI_NOTE: 既定の全組合せを維持し、指定された組合せ・席だけでも同じ評価入口を使える。
    pairs = (decks,) if decks else ((DECKS[0],DECKS[0]),(DECKS[0],DECKS[1]),(DECKS[1],DECKS[1]))
    return [{'seed':seed, 'decks':[a,b], 'seat':seat,'policy':policy,'opponent':opponent,'weights':weights}
            | ({'options': dict(options)} if options else {}) for seed in seeds for a,b in pairs for seat in seats]


def summarize(results: list[Json]) -> Json:
    # AI_NOTE: 上限終了を引き分けや勝利へ混ぜない。信頼区間は対戦ペア単位の再抽出で算出する。
    counts = {kind:sum(row['result']==kind for row in results) for kind in ('win','loss','draw','unfinished')}
    pairs: dict[str,list[float]] = {}
    for row in results:
        key = json.dumps([row['seed'],row['decks']])
        pairs.setdefault(key,[]).append({'win':1.0,'loss':0.0,'draw':0.5,'unfinished':0.0}[row['result']])
    pair_scores = [sum(values)/len(values) for values in pairs.values()]
    generator = random.Random(924)
    boot = sorted(sum(generator.choices(pair_scores,k=len(pair_scores)))/len(pair_scores) for _ in range(2000)) if pair_scores else [0.0]
    by_deck = {}
    for deck in DECKS:
        subset = [row for row in results if row['decks'][row['seat']]==deck]
        by_deck[deck] = {'games':len(subset),'wins':sum(row['result']=='win' for row in subset),
                         'draws':sum(row['result']=='draw' for row in subset),'unfinished':sum(row['result']=='unfinished' for row in subset)}
    cutoffs: dict[str, int] = {}
    for row in results:
        for kind, amount in row.get('cutoffs', {}).items():
            cutoffs[kind] = cutoffs.get(kind, 0)+amount
    return {**counts,'games':len(results),'score_rate':(counts['win']+0.5*counts['draw'])/len(results) if results else 0,
            'paired_interval_95':[boot[int((len(boot)-1)*.025)],boot[int((len(boot)-1)*.975)]],
            'by_deck':by_deck,'mean_decision_ms':sum(row['mean_decision_ms'] for row in results)/len(results) if results else 0,
            'total_nodes':sum(row.get('nodes', 0) for row in results),
            'total_game_seconds':sum(row.get('seconds', 0) for row in results),
            'peak_rss_bytes':max((row.get('peak_rss_bytes', 0) for row in results), default=0),
            'memory_scope':'maximum individual worker lifetime peak; not combined concurrent memory',
            'memory_methods':sorted({row['memory_method'] for row in results if row.get('memory_method')}),
            'actual_depth':[row.get('actual_depth', {}) for row in results],
            'limited_decisions':sum(row.get('limited_decisions', 0) for row in results), 'cutoffs':cutoffs,
            'role_coverage':[{'game_index':index, **coverage} for index, row in enumerate(results) for coverage in row.get('role_coverage', [])],
            'interpretation':'Observed game outcomes only; small samples do not establish strength. Role availability is not a win rate.'}


def run_jobs(tasks: list[Json], workers: int) -> list[Json]:
    # AI_NOTE: 対戦ごとの独立プロセスを使い、乱数やAIの状態を共有しない。
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(game,tasks))


def train(output: Path, workers: int, generations: int = 3, candidates: int = 6,
          policy: str = 'greedy', seed_start: int = 101, spread: float = .45) -> Json:
    # AI_NOTE: 候補の変更と選択は学習seedだけで行い、最終評価seedはこの関数へ渡さない。
    generator = random.Random(1409)
    best = dict(BASE_WEIGHTS)
    history: list[Json] = []
    for generation in range(generations):
        seeds = list(range(seed_start+generation*4,seed_start+4+generation*4))
        variants = [dict(best)] + [{key:round(max(.02,value*math.exp(generator.gauss(0,spread))),5) for key,value in best.items()} for _ in range(candidates-1)]
        all_results = run_jobs([task | {'candidate':i} for i,weights in enumerate(variants)
                                for task in jobs(seeds,policy,policy,weights)], workers)
        batch_size = len(all_results)//len(variants)
        scored = [summarize(all_results[i*batch_size:(i+1)*batch_size]) for i in range(len(variants))]
        chosen = max(range(len(variants)),key=lambda i:scored[i]['score_rate'])
        best = variants[chosen]
        history.append({'generation':generation,'seeds':seeds,'selected':chosen,
                        'candidates':[{'weights':weights,'summary':score} for weights,score in zip(variants,scored)],'games':all_results})
        print(json.dumps({'generation':generation,'selected':chosen,'scores':[s['score_rate'] for s in scored]}),flush=True)
    result = {'version':1,'method':'evolutionary weight search; game outcome fitness', 'policy':policy,
              'policy_version':3 if policy=='reply' else (2 if policy=='search' else 1),
              'weights':best,'base_weights':BASE_WEIGHTS,'generations':history,
              'scope':'shared weights for both registered decks; no per-card move table',
              'training_games':sum(len(h['games']) for h in history)}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def save_model(report: Json, path: Path) -> None:
    # AI_NOTE: 学習履歴と配布用の小さな重みを分離し、採用前でも候補として再利用できる。
    model = {key:report[key] for key in ('version','method','weights','base_weights','scope','training_games')}
    version = report.get('policy_version',1)
    model.update(status='candidate',training_seeds=[seed for generation in report['generations'] for seed in generation['seeds']],
                 cards_hash=fingerprint(catalog()),policy_version=version,model_hash=model_hash(report['weights'],version))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')


def main() -> None:
    # AI_NOTE: 探索予算・デッキ・席を明示して再現でき、従来方式は元の既定設定を維持する。
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description='対戦AIの学習・比較・リプレイ作成')
    parser.add_argument('command',choices=['train','evaluate','replay'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--seed',type=int,default=10001)
    parser.add_argument('--seeds',type=int,default=12)
    policies = ['random','greedy','search','trained','legacy','turn','reply','lookahead','roles']
    parser.add_argument('--policy',choices=policies,default='search')
    parser.add_argument('--opponent',choices=policies,default='greedy')
    parser.add_argument('--decks',nargs=2,choices=DECKS,metavar=('FIRST_DECK','SECOND_DECK'),help='指定したデッキ2組だけを対戦')
    parser.add_argument('--seat',choices=['0','1','both'],help='policyの席。evaluate既定はboth、replay既定は0')
    parser.add_argument('--role-k',type=int,help='rolesの応手候補数（1〜20、既定5）')
    parser.add_argument('--turns',type=int,help='roles/lookaheadの先読みターン数（1〜5）')
    parser.add_argument('--max-nodes',type=int,help='roles/lookaheadの探索数上限（1〜10000）')
    parser.add_argument('--seconds',type=float,help='roles/lookaheadの一手あたり時間上限（0より大、60以下）')
    parser.add_argument('--max-actions',type=int,default=500,help='一試合の操作上限。未決着はunfinishedとして記録')
    parser.add_argument('--replay-dir',type=Path,help='evaluateの各試合のリプレイ保存先')
    parser.add_argument('--training-policy',choices=['greedy','search','reply'],default='greedy')
    parser.add_argument('--model-output',type=Path)
    args = parser.parse_args()
    if args.workers < 1 or args.seeds < 1:
        parser.error('workers・seedsは1以上です')
    for name, minimum, maximum in (('role_k', 1, 20), ('turns', 1, 5), ('max_nodes', 1, 10000)):
        value = getattr(args, name)
        if value is not None and not minimum <= value <= maximum:
            parser.error(f'{name}は{minimum}〜{maximum}です')
    if args.seconds is not None and not 0 < args.seconds <= 60:
        parser.error('secondsは0より大きく60以下です')
    if args.max_actions < 1:
        parser.error('max-actionsは1以上です')
    if args.command == 'replay' and args.seat == 'both':
        parser.error('replayは1試合です。両席を保存する場合はevaluate --seat both --replay-dirを使ってください')
    options = {name: getattr(args, name) for name in ('role_k', 'turns', 'max_nodes', 'seconds') if getattr(args, name) is not None}
    if args.command == 'train':
        report = train(args.output,args.workers,policy=args.training_policy,
              seed_start=301 if args.training_policy=='search' else 101,
              spread=.9 if args.training_policy=='search' else .45)
        if args.model_output:
            save_model(report,args.model_output)
        return
    if args.command == 'replay':
        result = game({'seed':args.seed,'decks':args.decks or list(DECKS),'seat':int(args.seat or '0'),
                       'policy':args.policy,'opponent':args.opponent,'record':True,
                       'options':options,'max_actions':args.max_actions})
        data = result.pop('record')
        data['meta']['evaluation'] = {key:value for key,value in result.items() if key != 'decisions'}
        print(json.dumps(data['meta']['evaluation']),flush=True)
    else:
        seeds = list(range(args.seed,args.seed+args.seeds))
        decks = (args.decks[0], args.decks[1]) if args.decks else None
        seats = (int(args.seat),) if args.seat in ('0', '1') else (0, 1)
        tasks = [task | {'max_actions':args.max_actions,'save_decisions':True,'record':args.replay_dir is not None}
                 for task in jobs(seeds,args.policy,args.opponent,decks=decks,seats=seats,options=options)]
        results = run_jobs(tasks,args.workers)
        if args.replay_dir:
            args.replay_dir.mkdir(parents=True,exist_ok=True)
            for index, result in enumerate(results):
                path = args.replay_dir/f'game-{index:03d}-seed-{result["seed"]}-seat-{result["seat"]}.json'
                path.write_text(json.dumps(result.pop('record'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                result['replay'] = str(path.resolve())
        data = {'policy':args.policy,'opponent':args.opponent,'seeds':seeds,'summary':summarize(results),'games':results,
                'model_hash':model_hash(load_weights(),json.loads(MODEL_PATH.read_text()).get('policy_version',1)) if 'trained' in (args.policy,args.opponent) else None,
                'search_version':2,'reply_version':3,'options':options,
                'command_seconds':time.perf_counter()-started,
                'command_timing_scope':'main entry through game/replay generation; excludes interpreter startup and final report write',
                'model_hash_basis':'policy_version and weights',
                'conditions':'no mulligan; same initial state for seat swaps; public observations; unfinished scored zero'}
        printed = {key:value for key,value in data['summary'].items() if key not in ('role_coverage', 'actual_depth')}
        print(json.dumps(printed),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    main()
