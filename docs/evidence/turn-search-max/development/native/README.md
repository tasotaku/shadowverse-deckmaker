# Native enumeration development measurements

These exploratory results select an implementation; the parent task separately runs the fixed independent end-to-end acceptance protocol. All measurements use the unchanged hard1 fixture in `docs/evidence/turn-search-compare/independent-hard-cases.v1.json`, one-state initialization followed by a complete 100,000,000-state / 3,600-second-budget call. CPU slots were coordinated with the parent. `benchmark_native_variants.py` records exact packed BFS keys and witness bytes SHA256, search/cleanup/warmup phases, and Windows process peak working set. State/witness hashing occurs after the measured search; peak memory includes initialization and verification. No edges or candidates are serialized here.

| Variant | Enumeration seconds | Decision |
|---|---:|---|
| Baseline 47eb2ef | 22.783 | Reference |
| Reuse decoded and transition buffers | 20.717 | Useful allocation reduction |
| Row32 open-address index + buffers | 18.975 | Useful memory reduction |
| Row32 index + sparse combat updates | 14.948 | Adopt direct packed updates |
| Row32 index + all sparse updates | 13.357 | Adopt spell updates too |
| Full 192-bit key + occupied word buckets | 16.316 | Reject: slower and 1,074 MB table |
| Fingerprint32 + row32 index + all sparse | 10.400; repeat 10.097 | Selected |
| Retained empty probe and hash | 10.585; repeat 10.485 | Reject: additional bookkeeping did not improve time |

Every complete run yielded exactly 11,936,220 states, 83,535,563 choices, 88,767,067 outcomes and 76,830,848 duplicate outcomes. All packed state bytes and all representative BFS witness bytes match:

- keys SHA256: `7dd4d458902c26ef677f8cfa0695460c22215962d63b5a7644433e1fb41c6f26`
- witnesses SHA256: `edfed1d687f5f44c256a6a0e130e9719375d509534e11e0d28e3f4c06e35d570`

Selected fingerprint table occupies 268,435,456 bytes at final capacity, versus 134,217,728 bytes for Row32. Process peak RSS is approximately 0.93 GB for selected, 0.727 GB for Row32, and 2.072 GB for the old dictionary. The selected design is the fastest measured search while still using less than half the original peak memory.

The parent reported a short unrelated baseline checkout copy around the first retained-probe trial. That trial remains recorded and is not used alone for the decision; both alternatives were then repeated in the isolated slot. Every JSON report is retained unmodified. `snapshots/` retains intermediate source, including rejected alternatives. File-name prefixes identify the variant. Native delta code was additive: `combat_delta.py` is combat-only; final native delta code includes spells. Baseline source is commit 47eb2ef. Non-final snapshots contain development-only comments or adapters and are not production modules.

Final focused verification: 174 PASS, 2 existing closed-subset SKIP across native, index, catalogue and comparator tests. Strict mypy passed the typed native boundary and both focused test files. Additional index tests force bucket collisions, a matching fingerprint with unequal third state word, zero and all-one keys, and repeated growth. Existing generated transition tests now directly compare every sparse packed transition as well as the original array transition against the Python reference.

Development failures, corrected before measurement/selection: the new delta test initially passed Python integer words above signed int64 into Numba unpack; converting the test adapter to uint64 fixed the sole OverflowError. The rejected full-key variant initially combined uint64 state words and signed occupancy in a row assignment; explicit uint64 occupancy fixed Numba typing (7 tests failed compilation, no result disagreement). No exact-state or witness mismatch occurred in any measured complete run.

The production array `_transition` remains an independent compatibility/reference implementation; the BFS uses sparse packed transitions and only one decoded state buffer per batch. The 70% load threshold and power-of-two growth guarantee an empty probe slot. Positive row+1 in the low32 bits is safe under the validated 100M-state public limit; zero states and zero fingerprints are not empty entries. Hash fingerprints only reject nonmatches; every possible match requires equality of all three uint64 state words. All chance outcomes are validated against the budget together before any are inserted.
