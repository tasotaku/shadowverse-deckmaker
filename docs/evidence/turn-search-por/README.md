# Sleep-set partial-order prototype (rejected for deployment)

This experiment preserves the set of every reachable current-turn STOP state. It reduces alternative orders only for provably commuting deterministic operations. It does **not** claim to export the complete action-policy graph. Production code does not call this prototype.

The measured implementation is slower than ordinary state memoization on all three complete cases. The conclusion is to reject **this implementation**, not a claim that every partial-order algorithm is slower.

## Exactness boundary

- Both traversals use the same validated fixed-slot `Kernel`. No scoring, beam, board dominance or chance-outcome pruning is used.
- Every encountered prefix is stored before sleep-set/visited checks. Representative parent/action/tape witnesses replay from the root.
- Independence is deliberately narrow: board attacks on disjoint sources/targets, or single deterministic targeted damage/destroy/grant spells on disjoint targets; spells must be distinct hand entities and jointly affordable.
- Face attacks, super-evolved attacks (which can damage the leader), random actions, split damage, evolution, extra PP and summon are dependency barriers. When a summon card is present, all independence is disabled, avoiding generated entity-ID reuse assumptions.
- Disjoint operations leave each other's required followers, attack rights, keywords, target existence and spell cost unchanged. Distinct ordinary attacks can remove separate guards without disabling either attack. PP consumption commutes only when the sum is affordable. The fixed kernel has no triggers, so those disjoint local changes commute in full state, including normalized deaths/hand resources.
- Sleep sets remove one ordering, not both. At a state reached with a less restrictive sleep set, traversal reopens using the intersection of old/new sleep sets. A simple `seen` check would be unsound. Current-turn resources make the graph acyclic.
- All stochastic choices with actual random draws are retained with their complete exact Fraction distributions and tapes, as verified by equality with the unpruned traversal. Random operations are never commuted past observations or decisions.
- Deterministic edges omitted from the reduced traversal must be regenerated from `Kernel.actions/outcomes` if evaluating arbitrary adaptive policies. Use the production raw graph for consumers requiring all edges. A STOP state is not a policy probability distribution; this prototype never presents them as interchangeable.
- Two of eight independent small fixtures use compound effects outside `Kernel.eligible`; these are explicitly skipped, not approximated. Production generic fallback remains necessary.

## Complete isolated measurements

Each row uses three fresh Python processes per method, alternating baseline/POR order, with a 30-second per-call safety limit. All runs completed. Times are median enumeration-only seconds; OS peak is median whole-process Windows PeakWorkingSetSize. Both methods save the same reachable states, representative witnesses and stochastic-choice table. JSON/hashing is outside the timing. This compares prototype traversal to its own unpruned counterpart, not end-to-end production graph export.

| Case | States | Transitions baseline → POR | Reopens | Seconds baseline → POR | Peak MiB baseline → POR |
|---|---:|---:|---:|---:|---:|
| 3v3, 2 deterministic spells | 560 | 1,342 → 1,165 | 45 | 0.00701 → 0.00757 | 22.58 → 22.49 |
| 4v4, 2 deterministic spells | 6,234 | 20,116 → 16,992 | 819 | 0.10022 → 0.12214 | 27.92 → 28.20 |
| 4v4, 3 spells including random | 20,518 | 78,745 → 85,335 | 6,061 | 0.43801 → 0.62751 | 48.15 → 48.50 |

Every paired state SHA256 and stochastic-choice SHA256 matches. Raw JSON reports are adjacent to this file. On the mixed case, sleep-set reopening costs more transitions than it eliminates; management overhead also outweighs savings on the deterministic cases. POR has little prospect of removing millions of *distinct* required STOP states, since its benefit is mainly eliminating redundant operation orders.

## Verification

- New prototype: 71 passed, 2 explicitly unsupported fixtures skipped.
- Together with existing fast-kernel differential tests: 169 passed, 2 skipped.
- Strict mypy: all 3 changed Python files pass.
- Coverage: 6 supported fixed fixtures, 48 fully explored generated scenarios, 16 fully explored pairwise independence/diamond checks; replay every representative witness; all reached states and stochastic choices exactly equal baseline; zero-time interruption reports incomplete.
- Inputs include barrier, bane, ward, rush/storm, existing/new evolution, zero damage, attack-use flags, token ID collision cases, chosen/random/split damage. Independent diamond assertions require both action orders to remain legal and lead to exactly identical states/distributions.
- Scope: kernel semantics are shared with production; the existing fast-kernel tests compare to ordinary `ChanceBattle`. This experiment is not a second independent rules engine.

## Reproduce

From the worktree root, with `PYTHONPATH=src`:

```powershell
python -X utf8 scripts/turn_frontier_por_benchmark.py --size 4 --mixed --output output/base.json
python -X utf8 scripts/turn_frontier_por_benchmark.py --size 4 --mixed --por --output output/por.json
python -X utf8 -m pytest -q tests/test_battle_frontier_por.py tests/test_battle_frontier_fast.py
python -X utf8 -m mypy --strict src/svdeck/battle_frontier_por.py scripts/turn_frontier_por_benchmark.py tests/test_battle_frontier_por.py
```
