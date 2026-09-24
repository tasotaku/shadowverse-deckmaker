"""Run one bounded, isolated full-reachability POR measurement."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from svdeck.battle import Battle, Json
from svdeck.battle_frontier_fast import Kernel
from svdeck.battle_frontier_por import enumerate_states
from svdeck.combat_benchmark import peak_memory


def medium(size: int, mixed: bool) -> Battle:
    # AI_NOTE: 相互独立な戦闘と、依存する対象指定・確率スペルを同じ全完走条件で比較する。
    cards: dict[str, Json] = {
        'body': {'name': 'Body', 'kind': 'follower', 'cost': 1, 'attack': 2, 'health': 3},
        'ping': {'name': 'Ping', 'kind': 'spell', 'cost': 1, 'effects': [{'op': 'damage', 'target': 'chosen_enemy', 'amount': 1}]},
        'kill': {'name': 'Kill', 'kind': 'spell', 'cost': 1, 'effects': [{'op': 'destroy', 'target': 'chosen_enemy'}]},
        'random': {'name': 'Random', 'kind': 'spell', 'cost': 1, 'effects': [{'op': 'damage', 'target': 'random_enemy', 'amount': 2}]}}
    players: list[Json] = [{'turn': 4, 'ep': 0, 'sep': 0, 'pp': 3, 'max_pp': 3, 'extra_pp_used': True,
                          'board': [{'id': f'{owner}-{i}', 'card_id': 'body', 'entered_turn': 0,
                                     'attack': i+1, 'health': size+1-i,
                                     'keywords': ['守護'] if owner == 1 and i == 0 else ['バリア'] if i == 1 else []}
                                    for i in range(size)]} for owner in range(2)]
    players[0]['hand'] = [{'id': cid, 'card_id': cid} for cid in ('ping', 'kill', 'random') if mixed or cid != 'random']
    return Battle({'players': players}, cards)


def main() -> None:
    # AI_NOTE: 別プロセス単位でOS最大常駐メモリを記録し、未完走prefixを速度比較に混ぜない。
    parser = argparse.ArgumentParser()
    parser.add_argument('--size', type=int, choices=(2, 3, 4), default=3)
    parser.add_argument('--mixed', action='store_true')
    parser.add_argument('--por', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = enumerate_states(Kernel(medium(args.size, args.mixed)), por=args.por)
    peak, metric = peak_memory()
    report = {'size': args.size, 'mixed': args.mixed, 'por': args.por, 'complete': result.complete,
              'states': len(result.states), 'chance_choices': len(result.chance), 'expansions': result.expansions,
              'transitions': result.transitions, 'outcomes': result.outcomes, 'slept': result.slept,
              'reopens': result.reopens, 'seconds': result.seconds, 'peak_bytes': peak, 'memory_metric': metric,
              'states_sha256': hashlib.sha256(repr(sorted(result.states)).encode()).hexdigest(),
              'chance_sha256': hashlib.sha256(repr(sorted(result.chance.items())).encode()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
