# Fixed generated battles

`scripts/lookahead_generated_cases.py` produces exactly 128 cases from Python
`random.Random(seed)`, for every integer seed 0 through 127, in that order.
Each case records `seed`, `classification: exact`, and sorted `features`.
No search result, runtime, winner, or expected action controls inclusion.

The generator was authored using only the public `Battle`/`battle_rules`
definitions and the existing fixture/reference formats. Neither
`battle_lookahead.py` nor `battle_ai.py` was read or imported. The generator
does not compute expectations. A separate runner must compare each case with
`scripts/lookahead_reference.py:solve`; any timeout remains a reported outcome.

Flow: seed -> effect family and independently varied small state -> public
Battle normalization/legal-action check -> JSON. Invalid input raises an error;
there is no rejection sampling, fallback seed, or solver-based filtering.

- Horizons: seeds 0–79 use 3 turns, 80–111 use 2, and 112–127 use 1.
  Each boundary includes the complete `end_turn`, as in the reference solver.
- Both active sides occur. Initial player turns vary from 1 to 3; board bodies
  vary between newly entered, ready, and already attacked. Some boards carry
  end-turn damage or turn-start healing.
- Initial boards contain 0–2 followers per side (71 cases are 1 versus 1).
  Multi-target random/removal/split families usually get two opposing bodies;
  list order is the actual oldest-first split order.
- Initial hands contain 0–2 cards per side; 29 cases have two different root
  cards costing 1 each with 2 PP. Some reverse hand order. Leader health is
  1–6; current/max PP is 0–2; decks contain 2–4 unplayable fillers.
- Body attack/health, card costs, leader health, PP, hand contents, active
  side, timing and board sizes vary independently or through fixed schedules.
  IDs are reused across cases, so diversity cannot come from ID renaming.
- Six keyword pairs combine barrier, bane, storm, rush and ward. Sixteen
  hand-card families cover chosen/random damage and destruction, oldest-first
  split damage, two successive random hits, summons followed by grants,
  fanfare damage/split followed by grants, ally grants, enter triggers and
  turn-start/end damage. Tags name the scheduled family as well as families
  actually present in each hand; zero-hand cases can omit the scheduled card.

This is a bounded synthetic corpus, not a uniform sample of all reachable
matches. Evolution and extra PP are disabled to keep independent exhaustive
enumeration practical. It probes interacting abilities and turn boundaries;
it does not claim comprehensive card coverage or production search exactness.

Validation on the initial generated corpus:

- All 128 seeds normalize successfully and have legal actions.
- Both repeated generation and saved JSON compare equal.
- All 367 initial legal actions execute and their resulting states normalize.
- The temporary pytest checks passed (2 tests); strict mypy passed for the
  generator with `MYPYPATH=src` and `--follow-imports=silent`.
- Full search comparison is intentionally delegated to the independent root
  runner and is not represented by these initial-state checks.

Regenerate with `python scripts/lookahead_generated_cases.py --output
tests/fixtures/battle_lookahead_generated.json` from the repository root.
