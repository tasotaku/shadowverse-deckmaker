# Development observations

User goal: reduce the previous native complete current-turn runtime further while preserving every candidate and exact conditional chance semantics. Public output remains candidate JSON and the in-memory catalogue. No approximate pruning or reduced fixture scope is permitted.

Workflow checkpoint: the user found 100 seconds too slow. The previous phases identify repeated representation work (materialization and skyline comparisons) as major costs. Keep the correctness/output contract, optimize those operations, then measure unchanged hard fixtures with fresh predecessor and delivered runs. Ordinary product optimization; no reusable workflow artifact is being redesigned.

Data flow: packed reachable states → exact endpoint comparison → batch conversion to the same integer candidate rows and semantic hashes → the existing JSON writer. Enumeration retains its atomic state/outcome limits. Inputs outside the compiled subset retain the existing fallback.

Development isolation measurement: `export-only-hard2.json` is a single native worker for `hard_full_board_branching_2`, max-states 100000000, seconds 3600, debug-threshold 0, witness-samples 100. It used the new batch export with the predecessor skyline and predecessor enumeration. It completed in 47.081697 seconds (materialization 8.865108 seconds), RSS 1103069184 bytes, and retained the historical semantic digest. This was before the later enumeration lookup reuse and skyline changes; it is not the final comparison. Large output remains `output/turn-search-speed-development/export-only-hard2/result.json`.

Initial static checking found four local annotation errors after separating candidate materialization branches; declaring the shared result types resolved them. Then mypy passed and 144 export/comparator tests passed. The 96 generated export cases compare every reachable row and SHA256 against both the old kernel key and the independent full Battle semantic key. A separate test covers signed16 overflow, owner 1, empty candidates and invalid batch size.
