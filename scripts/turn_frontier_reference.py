"""Small-state raw oracle for one own turn, independent of search implementations.

Only Battle.legal_actions/step supply game rules. Every random_index choice is
replayed, including unfavorable outcomes. Only identical full states (except
rng) merge; no Pareto, score, card-identity, or board-order pruning is allowed.
end_turn means stop at the current state: it is NEVER passed to Battle.step.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from svdeck.battle.battle import Battle  # noqa: E402

Json = dict[str, Any]


def state_signature(state: Json) -> str:
    """Keep every field and every list's order; discard ONLY the RNG seed."""
    return json.dumps({k: v for k, v in state.items() if k != 'rng'},
                      ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def action_signature(action: Json) -> str:
    return json.dumps(action, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class NeedChoice(Exception):
    def __init__(self, length: int) -> None:
        self.length = length


class ReplayBattle(Battle):
    """Replay a finite random prefix, then request its next complete branch."""

    def __init__(self, state: Json, cards: dict[str, Json], choices: tuple[int, ...]) -> None:
        super().__init__(state, cards, record=False)
        self.random_choices = choices
        self.cursor = 0
        self.probability = Fraction(1)

    def random_index(self, length: int) -> int:
        if self.cursor == len(self.random_choices):
            raise NeedChoice(length)
        choice = self.random_choices[self.cursor]
        if not 0 <= choice < length:
            raise AssertionError('Random prefix is invalid for this execution')
        self.cursor += 1
        self.probability /= length
        return choice


@dataclass(frozen=True)
class Outcome:
    state: Json
    choices: tuple[int, ...]
    probability: Fraction


def all_outcomes(state: Json, cards: dict[str, Json], action: Json) -> list[Outcome]:
    """Expand the random decision tree, including distinct rolls with equal states."""
    if action['type'] == 'end_turn':
        raise ValueError('end_turn is a stop marker, not an executed action')
    pending: list[tuple[int, ...]] = [()]
    outcomes = []
    while pending:
        prefix = pending.pop()
        battle = ReplayBattle(state, cards, prefix)
        try:
            battle.step(action)
        except NeedChoice as choice:
            pending.extend(prefix + (index,) for index in reversed(range(choice.length)))
            continue
        assert battle.cursor == len(prefix)
        outcomes.append(Outcome(copy.deepcopy(battle.state), prefix, battle.probability))
    assert sum((result.probability for result in outcomes), Fraction()) == 1
    return outcomes


@dataclass(frozen=True)
class Edge:
    source: str
    action: str
    target: str
    choices: tuple[int, ...]
    probability: Fraction

    def signature(self) -> tuple[str, str, str, tuple[int, ...], Fraction]:
        """Complete comparison key; outcome identities and probabilities matter."""
        return (self.source, self.action, self.target, self.choices, self.probability)


@dataclass
class TurnGraph:
    root: str
    states: dict[str, Json]
    edges: list[Edge]
    stops: set[str]
    terminals: set[str]

    def to_json(self) -> Json:
        keys = {signature: index for index, signature in enumerate(self.states)}
        return {
            'root': keys[self.root],
            'states': [{'id': keys[sig], 'signature': sig, 'state': state}
                       for sig, state in self.states.items()],
            'edges': [{'source': keys[e.source], 'action': json.loads(e.action),
                       'target': keys[e.target], 'choices': list(e.choices),
                       'probability': str(e.probability)} for e in self.edges],
            'stops': sorted(keys[sig] for sig in self.stops),
            'terminals': sorted(keys[sig] for sig in self.terminals),
            'complete': True,
        }


def enumerate_turn(state: Json, cards: dict[str, Json], max_states: int = 100000) -> TurnGraph:
    """Enumerate all reachable states/edges, raising rather than claiming truncation exact."""
    if max_states < 1:
        raise ValueError('max_states must be positive')
    initial = Battle(state, cards, record=False)
    root = state_signature(initial.state)
    graph = TurnGraph(root, {root: copy.deepcopy(initial.state)}, [], set(), set())
    queue = deque([root])
    owner = initial.state['active_player']
    while queue:
        source = queue.popleft()
        battle = Battle(graph.states[source], cards, record=False)
        assert battle.state['active_player'] == owner
        if battle.state['winner'] is not None:
            graph.terminals.add(source)
            continue
        for action in battle.legal_actions():
            if action['type'] == 'end_turn':
                graph.stops.add(source)
                continue
            for result in all_outcomes(battle.state, cards, action):
                target = state_signature(result.state)
                graph.edges.append(Edge(source, action_signature(action), target,
                                        result.choices, result.probability))
                if target in graph.states:
                    continue
                if len(graph.states) >= max_states:
                    raise RuntimeError(f'Oracle state limit {max_states} exceeded; no complete result')
                graph.states[target] = result.state
                queue.append(target)
    return graph


def verify_case(case: Json, graph: TurnGraph) -> Json:
    """Check hand-authored action witnesses and their field-level expectations."""
    witness_states: dict[str, str] = {}
    for witness in case.get('witnesses', []):
        current = graph.root
        for step in witness['steps']:
            matches = [edge for edge in graph.edges
                       if edge.source == current and edge.action == action_signature(step['action'])
                       and edge.choices == tuple(step.get('choices', []))]
            assert len(matches) == 1, (case['id'], witness['id'], step, len(matches))
            current = matches[0].target
        assert current in graph.stops | graph.terminals
        witness_states[witness['id']] = current
        for check in witness.get('checks', []):
            actual: Any = graph.states[current]
            for key in check['path']:
                actual = actual[key]
            if 'equals_ids' in check:
                actual = [entity['id'] for entity in actual]
                expected = check['equals_ids']
            else:
                expected = check['equals']
            assert actual == expected, (case['id'], witness['id'], check, actual)
    for relation in case.get('relations', []):
        left, right = (witness_states[ident] for ident in relation['witnesses'])
        if relation['raw_relation'] == 'equal':
            assert left == right, relation
        else:
            assert relation['raw_relation'] == 'distinct' and left != right, relation
    return {'id': case['id'], 'states': len(graph.states), 'edges': len(graph.edges),
            'stops': len(graph.stops), 'terminals': len(graph.terminals),
            'witnesses': len(witness_states), 'verified': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, default=Path(__file__).resolve().parents[1]
                        / 'tests/fixtures/turn_frontier_cases.json')
    parser.add_argument('--case', help='Case ID; omit to enumerate every fixture')
    parser.add_argument('--output', type=Path, help='Optional full graphs, including raw state signatures')
    parser.add_argument('--max-states', type=int, default=100000)
    args = parser.parse_args()
    cases = json.loads(args.fixtures.read_text(encoding='utf-8'))
    selected = [case for case in cases if args.case is None or case['id'] == args.case]
    if not selected:
        parser.error('No matching fixture')
    graphs = []
    for case in selected:
        graph = enumerate_turn(case['state'], case['cards'], args.max_states)
        print(json.dumps(verify_case(case, graph), ensure_ascii=False))
        if args.output:
            graphs.append({'id': case['id'], **graph.to_json()})
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(graphs, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
