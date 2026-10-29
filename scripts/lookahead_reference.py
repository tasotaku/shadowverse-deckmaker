"""Tiny exhaustive reference using Battle transitions and terminal-only utility.

This intentionally does not import any search/player/heuristic implementation.
One turn includes the complete end_turn action (next start effects and draw).
Unfinished leaves tie: fixtures assert forced wins / avoided losses, not a
particular heuristic preference. Random choices are enumerated uniformly, with
the policy re-optimized after each observable outcome.
"""
from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from svdeck.battle.battle import Battle  # noqa: E402

Json = dict[str, Any]
Value = tuple[Fraction, Fraction]


class NeedChoice(Exception):
    def __init__(self, count: int):
        self.count = count


class EnumeratedBattle(Battle):
    """Override only the random source; all game transitions remain Battle's."""

    random_choices: tuple[int, ...] = ()
    cursor = 0

    def random_index(self, length: int) -> int:
        if self.cursor == len(self.random_choices):
            raise NeedChoice(length)
        choice = self.random_choices[self.cursor]
        self.cursor += 1
        return choice


def outcomes(state: Json, cards: dict[str, Json], action: Json) -> list[tuple[Fraction, Json]]:
    pending: list[tuple[Fraction, tuple[int, ...]]] = [(Fraction(1), ())]
    result: list[tuple[Fraction, Json]] = []
    while pending:
        probability, choices = pending.pop()
        battle = EnumeratedBattle(state, cards, record=False)
        battle.random_choices = choices
        try:
            battle.step(action)
        except NeedChoice as choice:
            pending.extend((probability / choice.count, choices + (index,))
                           for index in range(choice.count))
        else:
            result.append((probability, battle.state))
    return result


def solve(case: Json) -> Json:
    """Return exact rational root values and all terminal-utility optimal actions."""
    cards = case["cards"]
    initial = Battle(case["state"], cards, record=False).state
    root = initial["active_player"]
    cache: dict[tuple[int, str], Value] = {}
    nodes = 0

    def action_value(state: Json, action: Json, turns: int) -> Value:
        after_turns = turns - int(action["type"] == "end_turn")
        values = [(probability, value(after, after_turns))
                  for probability, after in outcomes(state, cards, action)]
        return (sum((p * v[0] for p, v in values), Fraction(0)),
                sum((p * v[1] for p, v in values), Fraction(0)))

    def value(state: Json, turns: int) -> Value:
        nonlocal nodes
        winner = state["winner"]
        if winner is not None:
            return Fraction(winner == root), -Fraction(winner == 1 - root)
        if turns == 0:
            return Fraction(0), Fraction(0)
        key = turns, json.dumps(state, sort_keys=True, separators=(",", ":"))
        if key in cache:
            return cache[key]
        nodes += 1
        if nodes > 100_000:
            raise RuntimeError("Reference fixture exceeded the 100,000-state safety cap")
        actions = Battle(state, cards, record=False).legal_actions()
        values = [action_value(state, action, turns) for action in actions]
        result = (max if state["active_player"] == root else min)(values)
        cache[key] = result
        return result

    ranked = [(action, action_value(initial, action, case["n_turns"]))
              for action in Battle(initial, cards, record=False).legal_actions()]
    best = max(v for _, v in ranked)
    return {"id": case["id"], "value": [str(x) for x in best],
            "optimal_first_actions": [action for action, v in ranked if v == best],
            "actions": [{"action": action, "value": [str(x) for x in v]} for action, v in ranked],
            "states": nodes}


def verify(case: Json) -> Json:
    result = solve(case)
    expected = case["expectations"]
    assert result["value"] == expected["value"], result
    encode = lambda item: json.dumps(item, sort_keys=True)
    assert set(map(encode, result["optimal_first_actions"])) == set(map(encode, expected["optimal_first_actions"])), result
    for check in expected.get("action_values", []):
        actual = next(item["value"] for item in result["actions"] if item["action"] == check["action"])
        assert actual == check["value"], (check, actual)
    if "adaptive_expectations" in case:
        initial = Battle(case["state"], case["cards"], record=False).state
        root = initial["active_player"]
        original_targets = {entity["id"] for entity in initial["players"][1 - root]["board"]}
        expected_targets = {item["removed"]: item["next_target"] for item in case["adaptive_expectations"]}
        seen = set()
        for probability, state in outcomes(initial, case["cards"], result["optimal_first_actions"][0]):
            surviving = {entity["id"] for entity in state["players"][1 - root]["board"]}
            removed, = original_targets - surviving
            seen.add(removed)
            following = solve(case | {"state": state})
            assert probability == Fraction(1, len(expected_targets))
            assert following["value"] == ["1", "0"]
            assert len(following["optimal_first_actions"]) == 1
            assert following["optimal_first_actions"][0]["target"] == expected_targets[removed]
        assert seen == set(expected_targets)
    for replay in case.get("replays", []):
        battle = Battle(case["state"] | replay.get("state_overrides", {}), case["cards"])
        for action in replay["actions"]:
            battle.step(action)
        for path, expected_value in replay["expected_paths"].items():
            actual_value: Any = battle.state
            for part in path.split("."):
                actual_value = actual_value[int(part)] if isinstance(actual_value, list) else actual_value[part]
            assert actual_value == expected_value, (case["id"], path, actual_value, expected_value)
    result["passed"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--cases", type=Path, default=Path(__file__).resolve().parents[1] / "tests/fixtures/battle_lookahead_cases.json")
    args = parser.parse_args()
    for case in json.loads(args.cases.read_text(encoding="utf-8")):
        if not args.case or case["id"] in args.case:
            print(json.dumps(verify(case), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
