"""Run one complete reference/cache comparison workload in a fresh process."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from svdeck.battle_env.battle import Battle  # noqa: E402
from svdeck.battle_env.battle_frontier import analyze  # noqa: E402
from svdeck.battle_env.battle_frontier_cache import CachedKernel  # noqa: E402
from svdeck.battle_env.battle_frontier_fast import Kernel  # noqa: E402


def main() -> None:
    # AI_NOTE: 同じ全グラフ・候補を作る二方式を新規processで比較し、完了しない上限prefixは成功扱いしない。
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=['reference', 'cache'], required=True)
    parser.add_argument('--size', type=int, choices=[2, 3, 4], required=True)
    parser.add_argument('--hand', type=int, default=3)
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1]/'tests/fixtures/battle_lookahead_hard.json'
    case = next(c for c in json.loads(path.read_text(encoding='utf-8'))
                if c['id'] == 'hard_full_board_branching_1')
    for player in case['state']['players']:
        player['board'] = player['board'][:args.size]
    case['state']['players'][case['state'].get('active_player', 0)]['hand'] = case['state']['players'][0]['hand'][:args.hand]
    battle = Battle(case['state'], case['cards'])
    instances: list[CachedKernel] = []

    def factory(battle: Battle) -> Kernel:
        # AI_NOTE: 実験時だけ依存を差し替え、製品公開APIの既定挙動は変更しない。
        kernel = CachedKernel(battle)
        instances.append(kernel)
        return kernel

    started = perf_counter()
    with patch('svdeck.battle_env.battle_frontier_fast.Kernel', factory if args.variant == 'cache' else Kernel):
        result = analyze(battle, backend='fixed-slots', seconds=30, max_states=10000000)
    wall = perf_counter()-started
    digest = hashlib.sha256()
    for key in ('positions', 'actions', 'choices', 'outcomes', 'candidates', 'probabilities', 'draws'):
        for row in result[key]:
            digest.update(repr(row).encode('utf-8'))
    print(json.dumps({'variant': args.variant, 'size': args.size, 'hand': args.hand,
                      'complete': result['complete'], 'stats': result['stats'], 'wall_seconds': wall,
                      'result_sha256': digest.hexdigest(),
                      'cache': instances[0].cache_stats() if instances else {}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
