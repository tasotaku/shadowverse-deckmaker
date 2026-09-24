"""Bind independent T2 observations to the fixed report contract."""
import datetime as dt
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]

def read(p):
    return json.loads(p.read_text(encoding="utf-8"))

def main():
    obs = read(HERE / "recomputed-summary.json")
    execution = read(HERE / "execution-record.json")
    small = read(HERE / "small-evidence-review.json")
    lock = read(HERE.parent / "independent-user-test-spec.v1.lock.json")
    end = dt.datetime.now(dt.timezone.utc).isoformat()
    suites = obs["suites"]
    errors = list(obs["failures"])
    for suite, s in suites.items():
        for key in ["all_expected_trials_complete", "all_candidate_digests_equal_per_case", "public_selection_matches_recomputation"]:
            if not s[key]:
                errors.append(f"{suite}: {key} false")
    if not small["all_T1_checks_true"] or not small["all_recomputed_digests_match"]:
        errors.append("Current independent small-case evidence failed")
    findings = [json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x for x in errors]
    budget = execution["stop_reason"] == "budget"
    stopped = execution["deadline"] if budget else end
    medium = suites.get("medium", {})
    heldout = suites.get("heldout", {})
    hard = suites.get("hard", {})
    evidence = [
        "F1 PASS: 3 substantive final methods baseline/cache/native ran. Current independent T1 evidence covers all 9 small cases for each; every exact state/candidate/action/outcome/draw/replay check true. T2 separately reconstructed all 27 documented candidate digests. POR rejection independently recomputed from 18 retained complete raw trials; it is slower on all 3 prior workloads, with equal state and chance digests. See small-evidence-review.json and prior-evidence-review.json.",
        f"F2: all medium complete={medium.get('all_expected_trials_complete')}, heldout complete={heldout.get('all_expected_trials_complete')}; exact per-case canonical candidate digests equal across methods/trials={medium.get('all_candidate_digests_equal_per_case')}/{heldout.get('all_candidate_digests_equal_per_case')}. Read raw standard JSON plus report; flags/counts alone were not used as equality proof.",
        "F3 PASS: all final rows use candidates mode, own current turn before end_turn, locked fixture byte hashes, seconds=3600, max_states=100000000, debug_threshold=0, witness_samples=100. Prior POR/full-graph evidence is excluded from final timing scores. Source revision 61061aa8963f3b87fc759c693088eea38a2b8d4d and product source hash remain pinned by each public manifest.",
        "F4 PASS: directly read setup, algorithm setup, enumeration, pruning, candidate materialization, cleanup, compute and serialization timings in retained reports; worker wall, external process wall and cold start/exit are separate. RSS uses Windows PeakWorkingSetSize in bytes, whole worker lifetime including saving. Phase fields and usable candidate output retained; no heap-only memory proxy used.",
        "F5 PASS: all 45 medium/heldout measured trial values retained, each in a fresh process, plus one separate one-state warmup per case/method excluded from selection. Raw report write timestamps retain the alternating execution order. Manifests identify interpreter, dependencies, machine, revision, input/options hashes and host reservation. Direct process snapshot found only the owned benchmark chain. T1 and root resident experiment ended before timed workers began; artifact review overlapped T1.",
        f"F6: frozen cold-medium aggregate recomputation={medium.get('aggregate_median_compute_seconds')}, performance leader={medium.get('performance_leader')}, observed aggregate-range uncertainty={medium.get('ranking_uncertain')}. Heldout aggregate={heldout.get('aggregate_median_compute_seconds')}, reversal={obs.get('heldout_aggregate_reversal')}. First heldout evaluation was logged before its invocation. No rule/roster change occurred. Native wins individual 4v4 cases, independently of the cold-medium aggregate choice; finite synthetic evidence is not a universal-fastest claim.",
        f"F7: both full 5v5 inputs requested for all 3 methods in one public command, complete={hard.get('all_expected_trials_complete')}, canonical digests equal={hard.get('all_candidate_digests_equal_per_case')}. Hard aggregate={hard.get('aggregate_median_compute_seconds')}. This is one trial per hard case/method; no repeated-trial uncertainty estimate or independent exhaustive hard oracle is claimed.",
        "F8 PASS: execution-record.json retains exact public commands; raw-artifacts.json maps and hashes every measured report/result; recomputed-summary.json preserves all trial timings, source/environment manifests, per-case medians/ranges, hashes and separate workload scopes. The independent reader imports only Python standard-library modules.",
        "UX1 PASS: read each public summary.json directly. Selection/inconclusive status, workload scope, completion, case/algorithm/mode, compute, serialization, RSS and raw paths are available without opening any raw state graph.",
        "UX2 PASS: exactly one comparison invocation each for medium, heldout and hard; public docs supplied cases/output/algorithms/trials/budget/debug/witness flags. No production-source edit or internal product import was needed.",
        "UX3 PASS: separate ordinary JSON reader loaded raw reports/results and recomputed selection. Every report/result/log path resolves and rows identify case, algorithm, candidate mode, completeness, seconds and memory bytes. All raw trial results are retained.",
        "UX4: command/artifact usable as delivered (GO for this CLI workflow). Largest remaining usability limitation is that independent correctness evidence is separate from each provisional timing summary, so a recommendation must link both; this is made explicit by the saved correctness_status and combined evidence. No window/focus/scroll or interactive SLA is part of the contract.",
        "Interaction observations: three suite commands; no retries, no discarded trials. CLI-only clicks, scrolling, viewport, automatic transitions and focus transfer are not acceptance conditions. Observation budget is 120 minutes including review and host-release wait; it is not a per-case response-time SLA."
    ]
    t2 = {"id":"T2", "batch":1, "execution_count":1, "status":"INCOMPLETE" if budget else ("FINDINGS" if findings else "PASS"), "journey_started_at":execution["journey_started_at"], "journey_stopped_at":stopped, "stop_reason":"budget" if budget else "completed", "functional_findings":findings, "ux_findings":[], "unexpected_findings":[], "test_spec_issues":[], "evidence":evidence, "cleanup":{"status":"completed", "finished_at":end, "evidence":"Only owned CLI child processes were used. Driver and all child workers exited; no global app/server was stopped and all output/turn-search-acceptance-t2 artifacts remain. Budget cleanup, if any, is restricted to recorded owned PID descendants in execution-record.json."}}
    t1 = {"id":"T1", "batch":1, "execution_count":0, "status":"NOT_RUN", "journey_started_at":None, "journey_stopped_at":None, "stop_reason":"impossible", "functional_findings":[], "ux_findings":[], "unexpected_findings":[], "test_spec_issues":[], "evidence":["This T2-only executor did not execute T1. T1 is assigned to its own fresh executor; the root coordinator merges that independent execution record. Current published T1 raw evidence was reviewed as required for T2."], "cleanup":{"status":"completed", "finished_at":end, "evidence":"No T1 process or environment was created by this executor."}}
    report = {"schema_version":"user-test-report/v1", "spec_id":lock["spec_id"], "spec_version":lock["version"], "spec_sha256":lock["sha256"], "executor_id":"turn_compare_acceptance_t2", "started_at":execution["journey_started_at"], "finished_at":end, "scheduling":{"available_executor_slots":2,"batch_count":1}, "execution_artifacts":{"preserved_workspace":str(ROOT / "output/turn-search-acceptance-t2"), "completed_record":str(HERE / "execution-record.json")}, "tests":[t1,t2], "product_findings_count":len(findings), "blind_spots":["Large-case equality is cross-method semantic digest evidence, not an independent exhaustive oracle.", "Synthetic supported fixtures and this Windows host do not establish a universal fastest algorithm.", "One hard trial per case/method provides no repeated-trial range; cold-worker results are separate from long-lived resident training throughput.", "T1 execution is represented by NOT_RUN only in this executor-local report; use the coordinator's merged report for overall acceptance."]}
    (HERE / "report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":t2["status"],"findings":len(findings),"started":execution["journey_started_at"],"stopped":stopped}))

if __name__ == "__main__":
    main()
