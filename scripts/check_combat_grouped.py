"""Reproducible comparison of combat combinations with exhaustive state search."""
from __future__ import annotations

import json
from pathlib import Path
from random import Random

from svdeck.battle_env.battle import Battle, replay
from svdeck.battle_env.battle_combat import Position, analyze, canonical, endpoint, position


def check() -> None:
    # AI_NOTE: 固定乱数の未調整局面と既存5対5を同条件で比較し、再生と候補集合を別々に検査する。
    rng = Random(917)
    cards = {'v': {'kind': 'follower', 'name': '検証体', 'cost': 1, 'attack': 1, 'health': 1}}
    reports = []
    for n in range(36):
        players = []
        for side in range(2):
            board = [{'card_id': 'v', 'id': f'{side}-{i}', 'attack': rng.randrange(0, 7),
                      'health': rng.randrange(1, 7), 'evolved': rng.choice([0, 0, 1, 2]),
                      'attacks': int(side == 0 and n % 5 == i),
                      'entered_turn': 7 if n % 4 == i else 0} for i in range(3)]
            players.append({'board': board, 'turn': 7, 'health': 100, 'max_health': 100})
        battle = Battle({'players': players}, cards)
        mode = ('attack', 'evolve', 'super')[n % 3]
        pair = {s: analyze(battle, mode, max_states=None, strategy=s) for s in ('exhaustive', 'grouped')}
        signatures: dict[str, set[Position]] = {}
        for strategy, result in pair.items():
            signatures[strategy] = set()
            for candidate in result['candidates']:
                actual = replay({**result['record'], 'actions': candidate['actions'], 'frames': []})
                signatures[strategy].add(canonical(endpoint(position(actual))))
        assert signatures['grouped'] == signatures['exhaustive'], (n, players, signatures)
        reports.append({'case': n, 'mode': mode, 'equal_candidates': True,
                        **{s: r['stats'] for s, r in pair.items()}})
    for fixture in json.loads(Path('docs/evidence/combat-benchmark.json').read_text(encoding='utf-8')):
        definitions = {b['card_id']: {'kind': 'follower', 'name': b['name'], 'cost': 1,
                       'attack': 1, 'health': 1} for p in fixture['initial']['players'] for b in p['board']}
        battle = Battle(fixture['initial'], definitions)
        pair = {s: analyze(battle, 'super', strategy=s) for s in ('exhaustive', 'grouped')}
        reports.append({'case': fixture['case'], **{s: {'complete': r['complete'], 'candidates': len(r['candidates']),
                        **r['stats']} for s, r in pair.items()}})
    Path('docs/evidence/combat-grouped-comparison.json').write_text(
        json.dumps(reports, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(reports[-3:], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    check()
