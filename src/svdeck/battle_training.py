"""Reproducible CPU training, paired evaluation and inspectable AI replays."""
from __future__ import annotations

import argparse
import copy
import json
import math
import random
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .battle import Battle, fingerprint, replay
from .battle_ai import BASE_WEIGHTS, MODEL_PATH, Player
from .battle_decks import new_match

Json = dict[str, Any]
DECKS = ('ramp-dragon', 'last-words-nightmare')


def game(job: Json) -> Json:
    # AI_NOTE: 同じ初期seed・デッキ配置で選手の先後を入替え、引きやデッキ相性の偏りを抑える。
    initial = new_match(job['decks'][0], job['decks'][1], seed=job['seed'])
    battle = Battle(initial.state, initial.cards, record=job.get('record', False))
    challenger = job['seat']
    players = [Player(battle.cards, job['opponent'], weights=job.get('opponent_weights'), seed=20+i) for i in range(2)]
    players[challenger] = Player(battle.cards, job['policy'], weights=job.get('weights'), seed=20+challenger)
    started = time.perf_counter()
    times: list[float] = []
    nodes = 0
    for count in range(job.get('max_actions', 500)):
        if battle.state['winner'] is not None:
            break
        owner = battle.state['active_player']
        decision = players[owner].choose(battle.observation(owner))
        if decision['action'] not in battle.legal_actions():
            raise AssertionError('AIが不合法手を選択しました')
        battle.step(decision['action'])
        times.append(decision['elapsed_ms'])
        nodes += decision['nodes']
        if battle.recording:
            battle.frames[-1]['decision'] = decision
    winner = battle.state['winner']
    result: Json = {k:job[k] for k in ('seed','decks','seat','policy','opponent')}
    result.update(winner=winner, result='unfinished' if winner is None else 'draw' if winner==-1 else 'win' if winner==challenger else 'loss',
                  actions=len(times), seconds=round(time.perf_counter()-started,3), nodes=nodes,
                  mean_decision_ms=round(sum(times)/len(times),3) if times else 0)
    if battle.recording:
        record = battle.export()
        record['meta'] = {'title': '先読みAI対戦 · ランプドラゴン vs ラストワードナイトメア',
                          'ai': {'policy':job['policy'],'opponent':job['opponent'],'seed':job['seed'],
                                 'weights':players[challenger].weights, 'information':'public observation only'}}
        if replay(record).state != battle.state:
            raise AssertionError('保存再生の最終状態が一致しません')
        result['record'] = record
    return result


def jobs(seeds: list[int], policy: str, opponent: str, weights: dict[str,float] | None = None) -> list[Json]:
    # AI_NOTE: 異種対戦と同種対戦を両方含め、双方の席を同じ初期状態で比較する。
    return [{'seed':seed, 'decks':[a,b], 'seat':seat,'policy':policy,'opponent':opponent,'weights':weights}
            for seed in seeds for a,b in ((DECKS[0],DECKS[0]),(DECKS[0],DECKS[1]),(DECKS[1],DECKS[1])) for seat in (0,1)]


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
    return {**counts,'games':len(results),'score_rate':(counts['win']+0.5*counts['draw'])/len(results) if results else 0,
            'paired_interval_95':[boot[int((len(boot)-1)*.025)],boot[int((len(boot)-1)*.975)]],
            'by_deck':by_deck,'mean_decision_ms':sum(row['mean_decision_ms'] for row in results)/len(results) if results else 0}


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
              'weights':best,'base_weights':BASE_WEIGHTS,'generations':history,
              'scope':'shared weights for both registered decks; no per-card move table',
              'training_games':sum(len(h['games']) for h in history)}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main() -> None:
    # AI_NOTE: 実験条件と全試合結果を保存し、同じコマンドで学習・比較・再生を繰り返せる。
    parser = argparse.ArgumentParser(description='対戦AIの学習・比較・リプレイ作成')
    parser.add_argument('command',choices=['train','evaluate','replay'])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--seed',type=int,default=10001)
    parser.add_argument('--seeds',type=int,default=12)
    parser.add_argument('--policy',choices=['random','greedy','search','trained'],default='search')
    parser.add_argument('--opponent',choices=['random','greedy','search','trained'],default='greedy')
    parser.add_argument('--training-policy',choices=['greedy','search'],default='greedy')
    args = parser.parse_args()
    if args.workers < 1 or args.seeds < 1:
        parser.error('workers・seedsは1以上です')
    if args.command == 'train':
        train(args.output,args.workers,policy=args.training_policy,
              seed_start=301 if args.training_policy=='search' else 101,
              spread=.9 if args.training_policy=='search' else .45)
        return
    if args.command == 'replay':
        result = game({'seed':args.seed,'decks':list(DECKS),'seat':0,'policy':args.policy,'opponent':args.opponent,'record':True})
        data = result.pop('record')
        print(json.dumps(result),flush=True)
    else:
        seeds = list(range(args.seed,args.seed+args.seeds))
        results = run_jobs(jobs(seeds,args.policy,args.opponent),args.workers)
        data = {'policy':args.policy,'opponent':args.opponent,'seeds':seeds,'summary':summarize(results),'games':results,
                'model_hash':fingerprint(json.loads(MODEL_PATH.read_text())) if 'trained' in (args.policy,args.opponent) else None,
                'conditions':'no mulligan; same initial state for seat swaps; public observations; unfinished scored zero'}
        print(json.dumps(data['summary']),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    main()
