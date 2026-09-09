"""同じ保存入力を元mainと試作へ渡し、公開CLIの出力をそのまま比較する。"""

from __future__ import annotations

from datetime import datetime, timezone
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASELINE = "39a98e6"
sys.path.insert(0, str(ROOT / "tests"))
from test_discovery import assessment, make_db, proposal  # noqa: E402
from svdeck.discovery import start  # noqa: E402

records: list[dict[str, Any]] = []
comparisons: list[list[str]] = []

with TemporaryDirectory(prefix="compatibility-", dir=OUT) as directory:
    temp = Path(directory)
    baseline = temp / "baseline"
    archive = subprocess.run(["git", "archive", BASELINE, "src"], cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
        for member in handle.getmembers():
            if member.isfile():
                entry = handle.extractfile(member)
                assert entry is not None
                path = baseline / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(entry.read())
    db = temp / "synthetic.db"
    make_db(db)
    template = temp / "template"
    start(template, db, "ウィッチ", "rotation", "同一保存入力の出力互換性を確認")
    for name in ("baseline", "candidate"):
        shutil.copytree(template, temp / f"{name}-session")

    def paired(command: str, *args: str) -> dict[str, Any]:
        outputs = []
        for name, source in (("baseline", baseline), ("candidate", ROOT)):
            argv = [sys.executable, "-m", "svdeck.discovery", command, str(temp / f"{name}-session"), *args]
            before = datetime.now(timezone.utc).isoformat()
            result = subprocess.run(argv, cwd=source, env={**os.environ, "PYTHONPATH": str(source / "src")},
                                    text=True, capture_output=True)
            records.append({"version": name, "started_at": before,
                            "finished_at": datetime.now(timezone.utc).isoformat(),
                            "argv": argv[1:], "returncode": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr})
            assert result.returncode == 0, result.stderr
            outputs.append(result.stdout)
        assert outputs[0] == outputs[1], f"出力が不一致: {command} {args}"
        comparisons.append([command, *args])
        return json.loads(outputs[0])

    def response(command: str, value: dict[str, Any]) -> None:
        path = temp / "answer.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        records.append({"input": value})
        paired(command, str(path))

    initial = paired("packet", "--revision", "0")
    paired("report")
    paired("read", initial["sha256"], "cards", "--offset", "0", "--limit", "2")
    response("submit", proposal(initial))
    paired("packet", "--revision", "1")
    response("attach", {"sources": [{"title": "人工の追加資料", "kind": "検査", "location": "人工入力",
                                     "observed_at": None, "content": "互換性だけを確認する。",
                                     "limitations": ["新しい探索結果ではない"]}]})
    judged = paired("packet", "--revision", "1", "--stage", "review")
    response("review", assessment(judged))
    continued = paired("packet", "--revision", "1")
    revised = proposal(continued)
    revised["hypothesis"] = "互換性確認用に改訂した仮説"
    response("submit", revised)
    paired("packet", "--revision", "2", "--stage", "review")
    paired("packet", "--revision", "2")
    paired("report")

with gzip.open(OUT / "compatibility-cli-log.jsonl.gz", "wt", encoding="utf-8") as handle:
    for record in records:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
result = {"verdict": "PASS", "baseline": BASELINE,
          "checked_at": datetime.now(timezone.utc).isoformat(),
          "comparisons": len(comparisons), "cli_calls": len(comparisons) * 2,
          "equality": "各コマンドのstdoutを文字列のまま完全一致で照合",
          "input": "同じ保存context・docs本文・captured_at・snapshot.dbを複製して両方へ投入",
          "scope": "単一クラスの資料・検索・追加資料・改訂・別評価・履歴・report。自然探索ではない。"}
(OUT / "compatibility-cli-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
