# Independent hard-combat answer construction

The reference author read the public `Battle` engine and the benchmark signature contract, but did not read or import `battle_combat.py`. No production solver answers were used to choose or generate expected answers.

## Exhaustiveness argument

1. Ability-free followers have at most one attack. Every action prefix therefore induces one target assignment per own follower: unused, enemy leader, or one fixed opposing follower.
2. At most one evolution can be used this turn. It is fully described by its follower, ordinary/super category, and whether it occurs before or after that follower's own attack. Evolution of an unused follower is also enumerated. Moving this evolution next to that follower's attack does not affect other ability-free followers. Evolution after a fatal attack is rejected.
3. Against one enemy, incoming attack values sum independently. If their sum is below its starting health, every ordering is legal and has the same endpoint. If the sum is lethal, a last hitter is legal exactly when total damage minus that hitter's damage is strictly below starting health. Enumerate every such last hitter, because a super-evolved last hitter adds a leader ping. This includes finishing with a small attacker after larger attackers.
4. A non-super attacking follower receives the target's fixed attack once, whether or not its attack kills that target. A super-evolved attacking follower takes no retaliation. Unrelated target groups have no effects on each other and commute.
5. Enumerating the Cartesian product of target assignments, legal evolution plans, and feasible group finishers therefore covers every distinct endpoint. Zero attack, summoning sickness, spent attacks, injured maximum health, unused evolution resources, existing evolution categories, and stopped prefixes are represented. A leader kill collapses to WIN; replay stops at the actual first winning action.

## Dominance is exact

Own-board improvement and opposing-board reduction require injective matching of followers with equal evolution category and componentwise attack, current health, and maximum health improvement. Leader health, EP and SEP are separate dimensions. Identity, order and endpoint attack rights are ignored. Matching uses subset dynamic programming, independent of production comparisons.

The reference sorts by a scalar that strictly increases under strict dominance, retaining every nondominated endpoint. Resource/stat-sum/category-count bitsets only discard pairs that cannot possibly dominate. They never accept dominance. Every domination decision still requires exact matching of both boards. There is no candidate cap, top-k, search budget, or sampling.

## Validation and artifacts

`python scripts/combat_reference.py` regenerates the certificate. All existing small oracle fixtures, reductions of each hard fixture, and an explicit post-attack-evolution/super-finisher example are compared against every endpoint from exhaustive public `Battle.legal_actions()` / `Battle.step()` enumeration. Every retained hard-case witness is replayed through the public engine. The certificate binds generator, engine, fixture-file and individual-case hashes, all signatures and signature-set hashes. These checks establish reachability; exhaustiveness for hard cases rests on the assignment argument above and small-case exhaustive cross-checks.
`verify_small_dominance.py` additionally validates 35 deterministic held-out 2v2 cases against exhaustive engine endpoints and a factorial-permutation dominance implementation (separate from the reference subset matcher and bitset filtering). The full raw results are in `independent-small-checks.json`.
