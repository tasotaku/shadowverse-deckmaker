"""Generate fixed small battles without consulting a player or search algorithm.

The 128 seeds are a sampling contract, not a pool to filter by solver results.
Expected values must come from scripts/lookahead_reference.py in a separate run.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from svdeck.battle_env.battle import Battle  # noqa: E402

Json = dict[str, Any]
KEYWORD_PAIRS = [
    ["バリア", "守護"], ["必殺", "突進"], ["疾走", "守護"],
    ["バリア", "必殺"], ["突進", "守護"], ["疾走", "バリア"],
]
FAMILIES = [
    "chosen_damage", "random_damage", "oldest_split", "chosen_destroy",
    "random_destroy", "summon_and_grant", "fanfare_damage_grant", "barrier_buff",
    "bane_rush_grant", "storm_grant", "end_turn_damage", "turn_start_damage",
    "enter_grant", "two_random_hits", "fanfare_split", "summon_barrier",
]


def hand_card(family: int, rng: random.Random) -> Json:
    """Build one bounded effect family, with independently varied cost/stats."""
    card: Json = {"name": FAMILIES[family], "kind": "spell", "cost": rng.randrange(3)}
    amount = rng.randint(1, 3)
    if family in (0, 1, 2, 3, 4, 13):
        effects = {
            0: [{"op": "damage", "target": "chosen_any_enemy", "amount": amount}],
            1: [{"op": "damage", "target": "random_enemy", "amount": amount}],
            2: [{"op": "split_damage", "amount": amount + 1}],
            3: [{"op": "destroy", "target": "chosen_enemy"}],
            4: [{"op": "destroy", "target": "random_enemy"}],
            13: [{"op": "damage", "target": "random_enemy", "amount": 1},
                 {"op": "damage", "target": "random_enemy", "amount": amount}],
        }
        card["effects"] = effects[family]
    elif family in (5, 15):
        card["effects"] = [
            {"op": "summon", "card_id": "token", "count": 1},
            {"op": "grant", "target": "all_ally", "keywords": ["疾走" if family == 5 else "バリア"]},
        ]
    elif family in (7, 8, 9):
        grants = {7: ["バリア"], 8: ["必殺", "突進"], 9: ["疾走"]}
        card["effects"] = [{"op": "grant", "target": "chosen_ally", "keywords": grants[family]}]
        if family == 7:
            card["effects"].append({"op": "buff", "target": "chosen_ally", "attack": 1, "health": 1})
    else:
        card.update(kind="follower", attack=rng.randint(1, 2), health=rng.randint(1, 3))
        card["keywords"] = ["突進" if family % 2 else "守護"]
        if family == 6:
            card["fanfare"] = [
                {"op": "damage", "target": "chosen_enemy", "amount": amount},
                {"op": "grant", "target": "self", "keywords": ["バリア"]},
            ]
        elif family == 10:
            card["end_turn"] = [{"op": "damage", "target": "enemy_leader", "amount": 1}]
        elif family == 11:
            card["triggers"] = [{"event": "turn_start", "scope": "ally", "effects": [
                {"op": "damage", "target": "enemy_leader", "amount": 1}]}]
        elif family == 12:
            card["triggers"] = [{"event": "enter", "scope": "self", "effects": [
                {"op": "grant", "target": "event", "keywords": ["バリア", "必殺"]}]}]
        elif family == 14:
            card["fanfare"] = [{"op": "split_damage", "amount": amount},
                               {"op": "grant", "target": "self", "keywords": ["疾走"]}]
    return card


def generate_cases() -> list[Json]:
    """Return all seeds 0..127 in order; neither solve nor discard any case."""
    cases: list[Json] = []
    for seed in range(128):
        rng = random.Random(seed)
        family = seed % len(FAMILIES)
        active = (seed // 16) % 2
        n_turns = 3 if seed < 80 else 2 if seed < 112 else 1
        features = {FAMILIES[family], "mixed_keywords", f"turns:{n_turns}", f"active:{active}"}
        cards: dict[str, Json] = {
            "filler": {"name": "Unplayable draw filler", "kind": "spell", "cost": 99, "effects": []},
            "token": {"name": "Small summoned body", "kind": "follower", "cost": 1,
                      "attack": rng.randint(1, 2), "health": rng.randint(1, 2),
                      "keywords": ["突進" if seed % 2 else "守護"]},
        }
        players: list[Json] = []
        for side in range(2):
            root = side == active
            turn = 1 + (seed // 8) % 3
            count = 1
            # Multi-target and ordered split effects must encounter real alternatives.
            if not root and family in (1, 2, 4, 13, 14):
                count = 2
            elif root and seed % 16 == 7:
                count = 2
            elif (root and seed % 19 == 0) or (not root and seed % 23 == 0):
                count = 0
            hand_count = 2 if root and seed % 4 == 0 else 1
            if seed % 11 == side:
                hand_count = 0
            pp = 2 if hand_count == 2 else rng.randrange(3)
            player: Json = {
                "turn": turn, "ep": 0, "sep": 0, "extra_pp_used": True,
                "health": rng.randint(1, 6), "pp": pp, "max_pp": max(pp, rng.randrange(3)),
                "deck": ["filler"] * rng.randint(2, 4), "hand": [], "board": [],
            }
            for index in range(count):
                cid = f"body_{side}_{index}"
                keywords = KEYWORD_PAIRS[(seed + 2 * side + index) % len(KEYWORD_PAIRS)].copy()
                cards[cid] = {"name": cid, "kind": "follower", "cost": rng.randrange(3),
                              "attack": rng.randint(1, 3), "health": rng.randint(1, 4), "keywords": keywords}
                entered = turn if (seed + side + index) % 3 == 0 else turn - 1
                attacks = int((seed + 3 * side + index) % 7 == 0)
                player["board"].append({"id": cid, "card_id": cid, "entered_turn": entered, "attacks": attacks})
                features.update(keywords)
                if entered == turn:
                    features.add("entered_this_turn")
                if attacks:
                    features.add("already_attacked")
                if index == 0 and (seed + side) % 8 == 0:
                    cards[cid]["end_turn"] = [{"op": "damage", "target": "enemy_leader", "amount": 1}]
                    features.add("board_end_turn_damage")
                if index == 0 and (seed + side) % 8 == 3:
                    cards[cid]["triggers"] = [{"event": "turn_start", "scope": "ally", "effects": [
                        {"op": "heal", "target": "own_leader", "amount": 1}]}]
                    features.add("board_turn_start_heal")
            for index in range(hand_count):
                # The second root card is a different family, so order changes effects.
                selected = (family + (0 if root else 5) + 7 * index) % len(FAMILIES)
                cid = f"hand_{side}_{index}"
                cards[cid] = hand_card(selected, rng)
                if hand_count == 2:
                    cards[cid]["cost"] = 1
                player["hand"].append({"id": cid, "card_id": cid})
                features.add(FAMILIES[selected])
            if hand_count == 2:
                features.add("two_card_order")
                if seed % 8 == 4:
                    player["hand"].reverse()
                    features.add("reversed_hand_order")
            features.update({f"board:{'root' if root else 'opponent'}:{count}", f"hand:{hand_count}", f"pp:{pp}"})
            players.append(player)
        case: Json = {
            "id": f"generated_{seed:03d}", "seed": seed, "classification": "exact",
            "n_turns": n_turns, "features": sorted(features), "cards": cards,
            "state": {"active_player": active, "rng": seed + 1, "players": players},
        }
        # A generator failure is visible; never skip or replace an invalid seed.
        battle = Battle(case["state"], cards, record=False)
        assert battle.state["winner"] is None and battle.legal_actions(), case["id"]
        cases.append(case)
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "tests/fixtures/battle_lookahead_generated.json")
    args = parser.parse_args()
    cases = generate_cases()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(cases)} validated cases to {args.output}")


if __name__ == "__main__":
    main()
