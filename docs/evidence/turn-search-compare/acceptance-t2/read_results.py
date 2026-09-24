"""Ordinary JSON reader of public artifacts, independent of product modules."""
import collections
import datetime as dt
import hashlib
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[4]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "output/turn-search-acceptance-t2"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def main():
    suites = {}
    raw_paths = []
    failures = []
    fixture_manifest = read(ROOT / "docs/evidence/turn-search-compare/independent-fixtures-manifest.v1.json")
    for suite in ["medium", "heldout", "hard"]:
        folder = OUT / suite
        if not (folder / "summary.json").exists():
            failures.append(f"{suite}: no completed summary")
            continue
        public = read(folder / "summary.json")
        manifest = read(folder / "manifest.json")
        trials = []
        for path in sorted(folder.glob("case-*/*/trial-*/report.json")):
            r = read(path)
            result_path = folder / r["result_path"]
            x = read(result_path)
            digest_equal = x["candidate_semantic_sha256"] == r["candidate_semantic_sha256"]
            flags = all(r[k] and x[k] for k in ["complete", "enumeration_complete", "frontier_complete"])
            checks = {
                "report_result_digest_equal": digest_equal,
                "all_complete_flags": flags,
                "empty_cutoffs": not r["cutoffs"] and not x["cutoffs"],
                "candidate_count_matches_saved_rows": r["candidate_count"] == x["candidate_count"] == len(x["candidates"]),
                "same_output_mode": r["mode"] == x["mode"] == manifest["output_mode"] == "candidates",
                "case_algorithm_match": r["case_id"] == x["case_id"] and r["algorithm"] == x["algorithm"],
                "input_hash_matches_fixture": r["input_sha256"] == manifest["input_sha256"] == fixture_manifest[f"independent-{suite}-cases.v1.json"]["sha256"],
                "source_hash_matches_manifest": r["source_sha256"] == manifest["source_sha256"],
                "frozen_options": r["options"] == {"seconds": 3600.0, "max_states": 100000000, "mode": "candidates", "debug_threshold": 0, "witness_samples": 100},
                "whole_lifetime_peak": r["memory_method"] == "Windows PeakWorkingSetSize" and r["memory_scope"] == "whole worker lifetime" and r["peak_rss_bytes"] > 0,
                "raw_logs_retained": (path.parent / "stdout.log").exists() and (path.parent / "stderr.log").exists(),
            }
            if not all(checks.values()):
                failures.append({"path": str(path), "checks": checks})
            trials.append({"case": r["case_id"], "algorithm": r["algorithm"], "trial": r["trial"], "complete": flags, "mode": r["mode"], "digest": r["candidate_semantic_sha256"], "candidate_count": r["candidate_count"], "state_count": r["state_count"], "timings_seconds": r["timings"], "process_wall_seconds": r["process_wall_seconds"], "cold_start_and_exit_seconds": r["cold_start_and_exit_seconds"], "peak_rss_bytes": r["peak_rss_bytes"], "checks": checks, "report_path": str(path.relative_to(ROOT)), "result_path": str(result_path.relative_to(ROOT)), "report_written_at": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()})
            raw_paths.append({"suite": suite, "case": r["case_id"], "algorithm": r["algorithm"], "trial": r["trial"], "report": str(path.relative_to(ROOT)), "result": str(result_path.relative_to(ROOT)), "report_sha256": sha(path), "result_sha256": sha(result_path), "result_bytes": result_path.stat().st_size})
            del x
        groups = collections.defaultdict(list)
        digests = collections.defaultdict(set)
        for r in trials:
            groups[(r["case"], r["algorithm"])].append(r)
            digests[r["case"]].add(r["digest"])
        aggregate = collections.defaultdict(float)
        ranges = collections.defaultdict(lambda: [0.0, 0.0])
        rows = []
        for (case, algorithm), rs in groups.items():
            times = [r["timings_seconds"]["compute_seconds"] for r in rs]
            median = statistics.median(times)
            aggregate[algorithm] += median
            ranges[algorithm][0] += min(times)
            ranges[algorithm][1] += max(times)
            row = {"case": case, "algorithm": algorithm, "complete": all(r["complete"] for r in rs), "mode": "candidates", "trial_count": len(rs), "compute_seconds": times, "median_compute_seconds": median, "range_compute_seconds": [min(times), max(times)], "median_serialization_seconds": statistics.median(r["timings_seconds"]["serialization_seconds"] for r in rs), "median_process_wall_seconds": statistics.median(r["process_wall_seconds"] for r in rs), "median_peak_rss_bytes": statistics.median(r["peak_rss_bytes"] for r in rs), "candidate_digest": rs[0]["digest"], "candidate_count": rs[0]["candidate_count"], "state_count": rs[0]["state_count"]}
            rows.append(row)
            reported = next(g for g in public["groups"] if g["case_id"] == case and g["algorithm"] == algorithm)
            for key in ["median_compute_seconds", "median_serialization_seconds", "median_peak_rss_bytes"]:
                if row[key] != reported[key]:
                    failures.append(f"{suite}/{case}/{algorithm}: summary {key} mismatch")
        ranked = sorted(aggregate, key=aggregate.get)
        equal = all(len(d) == 1 for d in digests.values())
        expected_trials = 1 if suite == "hard" else 3
        expected_cases = len(fixture_manifest[f"independent-{suite}-cases.v1.json"]["case_ids"])
        full = len(trials) == expected_cases * 3 * expected_trials and all(r["complete"] for r in trials)
        overlap = any(ranges[ranked[0]][1] >= ranges[a][0] for a in ranked[1:])
        chronological = sorted(trials, key=lambda r:r["report_written_at"])
        orders = collections.defaultdict(list)
        for r in chronological:
            orders[(r["case"], r["trial"])].append(r["algorithm"])
        warmups = [read(p) for p in folder.glob("case-*/*/warmup/report.json")]
        warmups_ok = len(warmups) == expected_cases * 3 and all(w["warmup"] and w["options"]["max_states"] == 1 for w in warmups)
        alternating = {tuple(v) for v in orders.values()} == {("baseline", "cache", "native"), ("native", "cache", "baseline")}
        if not warmups_ok or not alternating:
            failures.append(f"{suite}: warmup policy or alternating observed order not satisfied")
        suites[suite] = {"all_expected_trials_complete": full, "all_candidate_digests_equal_per_case": equal, "groups": rows, "aggregate_median_compute_seconds": dict(aggregate), "aggregate_range_seconds": dict(ranges), "performance_leader": ranked[0] if full and equal else None, "ranking_uncertain": overlap, "public_selection_matches_recomputation": public["selection"]["aggregate_median_compute_seconds"] == aggregate and public["selection"]["algorithm"] == ranked[0], "warmup_count": len(warmups), "warmup_policy_verified": warmups_ok, "alternating_order_verified": alternating, "manifest": manifest, "trials": trials, "observed_report_write_order": [{k:r[k] for k in ["case", "algorithm", "trial", "report_written_at"]} for r in chronological], "summary_path": str((folder / "summary.json").relative_to(ROOT))}
    for key in ["revision", "source_sha256", "dependencies", "interpreter", "python", "platform", "machine", "processor", "horizon", "output_mode", "options", "options_sha256"]:
        if len({json.dumps(s["manifest"][key],sort_keys=True) for s in suites.values()}) != 1:
            failures.append(f"Manifest {key} differs across suites")
    if sha(ROOT / "docs/evidence/turn-search-compare/selection-protocol.v1.json") != read(HERE / "first-heldout-evaluation.json")["selection_protocol_sha256"]:
        failures.append("Frozen selection protocol changed after heldout evaluation")
    summary = {"read_at": dt.datetime.now(dt.timezone.utc).isoformat(), "scope": "Cold fresh-process candidate output; frozen medium aggregate selects; heldout and hard reported separately. Large equality is cross-method evidence, not an independent exhaustive oracle.", "suites": suites, "failures": failures}
    if "medium" in suites and "heldout" in suites:
        summary["heldout_aggregate_reversal"] = suites["medium"]["performance_leader"] != suites["heldout"]["performance_leader"]
    (HERE / "recomputed-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (HERE / "raw-artifacts.json").write_text(json.dumps(raw_paths, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"suites": {s:{k:v[k] for k in ["all_expected_trials_complete", "all_candidate_digests_equal_per_case", "aggregate_median_compute_seconds", "performance_leader", "ranking_uncertain", "public_selection_matches_recomputation"]} for s,v in suites.items()}, "failures": failures}, indent=2))

if __name__ == "__main__":
    main()
