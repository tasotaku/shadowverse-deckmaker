"""Independent CLI-only observation driver; does not import product internals."""
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[4]
EVIDENCE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "output/turn-search-acceptance-t2"
START = dt.datetime.fromisoformat("2026-09-24T16:07:35.950754+00:00")
DEADLINE = START + dt.timedelta(minutes=120)

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def save(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    record = {"journey_started_at": START.isoformat(), "deadline": DEADLINE.isoformat(), "driver_started_at": now(), "suites": [], "commands_per_suite": 1}
    save("execution-record.json", record)
    for suite, trials in [("medium", 3), ("heldout", 3), ("hard", 1)]:
        if dt.datetime.now(dt.timezone.utc) >= DEADLINE:
            record["stop_reason"] = "budget"
            break
        if suite == "heldout":
            save("first-heldout-evaluation.json", {"recorded_at": now(), "event": "Before first heldout suite invocation or result inspection", "roster": ["baseline", "cache", "native"], "selection_protocol_sha256": hashlib.sha256((ROOT / "docs/evidence/turn-search-compare/selection-protocol.v1.json").read_bytes()).hexdigest(), "changes_after_freeze": []})
        command = [sys.executable, "-X", "utf8", "-m", "svdeck.battle_frontier_compare", "--cases", f"docs/evidence/turn-search-compare/independent-{suite}-cases.v1.json", "--output", f"output/turn-search-acceptance-t2/{suite}", "--algorithms", "baseline,cache,native", "--trials", str(trials), "--seconds", "3600", "--max-states", "100000000", "--debug-threshold", "0", "--witness-samples", "100", "--load-note", "Host released by root after T1 and separate resident experiment; no competing benchmark/oracle workers; serial fresh-process T2 trials"]
        row = {"suite": suite, "command": command, "started_at": now(), "stdout": str(OUT / f"{suite}.stdout.txt"), "stderr": str(OUT / f"{suite}.stderr.txt")}
        record["suites"].append(row)
        with open(row["stdout"], "w", encoding="utf-8") as stdout, open(row["stderr"], "w", encoding="utf-8") as stderr:
            child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            row["owned_pid"] = child.pid
            save("execution-record.json", record)
            while child.poll() is None:
                remaining = (DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds()
                if remaining <= 0:
                    row["stopped_for_budget_at"] = now()
                    cleanup = subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True, text=True)
                    row["cleanup"] = {"owned_tree_root": child.pid, "returncode": cleanup.returncode, "stdout": cleanup.stdout, "stderr": cleanup.stderr}
                    record["stop_reason"] = "budget"
                    child.wait(timeout=30)
                    break
                save("heartbeat.json", {"at": now(), "suite": suite, "owned_pid": child.pid, "remaining_seconds": remaining})
                time.sleep(min(10, remaining))
            row["exit_code"] = child.returncode
            row["finished_at"] = now()
            save("execution-record.json", record)
        if record.get("stop_reason") == "budget":
            break
    record.setdefault("stop_reason", "commands_finished")
    record["driver_finished_at"] = now()
    save("execution-record.json", record)
    print(json.dumps(record, indent=2))

if __name__ == "__main__":
    main()
