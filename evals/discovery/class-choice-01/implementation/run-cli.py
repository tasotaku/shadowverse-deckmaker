"""公開CLIの実操作を人工DBで再現し、入出力と判定を保存する。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tests"))
from test_discovery import assessment, proposal  # noqa: E402
from test_discovery_classes import class_db, class_proposal  # noqa: E402

records: list[dict[str, Any]] = []
env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
checks: list[str] = []


def cli(*args: str, expected: int = 0) -> dict[str, Any]:
    before = datetime.now(timezone.utc).isoformat()
    result = subprocess.run([sys.executable, "-m", "svdeck.discovery", *args], cwd=ROOT,
                            env=env, text=True, capture_output=True)
    records.append({"started_at": before, "finished_at": datetime.now(timezone.utc).isoformat(),
                    "argv": list(args), "returncode": result.returncode,
                    "stdout": result.stdout, "stderr": result.stderr})
    assert result.returncode == expected, result.stderr
    assert "Traceback" not in result.stderr
    return json.loads(result.stdout) if result.stdout else {}


with TemporaryDirectory(prefix="sv-class-cli-") as directory:
    temp = Path(directory)
    db = class_db.__wrapped__(temp)
    original_hash = hashlib.sha256(db.read_bytes()).hexdigest()
    session = str(temp / "all")
    cli("start", session, "--db", str(db), "--class", "all", "--objective", "人工札による機能検査")
    root = cli("packet", session, "--revision", "0")
    summary = cli("packet", session, "--revision", "0", "--summary")
    assert summary["sha256"] == root["sha256"] and "class_name" in summary["response_example"]
    cards = cli("read", session, root["sha256"], "cards", "--limit", "100")["content"]
    assert cards == root["data"]["context"]["cards"]
    checks.append("allの開始・概要・分割読出しで固定資料が一致")
    answer_path = temp / "answer.json"

    def send(command: str, value: dict[str, Any], expected: int = 0) -> dict[str, Any]:
        answer_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        records.append({"input_file": str(answer_path), "content": deepcopy(value)})
        return cli(command, session, str(answer_path), expected=expected)

    for cls in ("ウィッチ", "ドラゴン"):
        send("submit", class_proposal(root, cls))
    witch = cli("packet", session, "--revision", "1")
    dragon = cli("packet", session, "--revision", "2")
    assert witch["data"]["search"][0]["tag_hits"] == [2, 7]
    assert dragon["data"]["search"][0]["tag_hits"] == [3, 7]
    checks.append("同じ起点資料から2クラスの別案を保存し、検索は各クラス＋共通札だけ")
    for bad_class in (None, "all", "ニュートラル", "invalid"):
        data = class_proposal(root, "ウィッチ")
        if bad_class is None:
            del data["class_name"]
        else:
            data["class_name"] = bad_class
        send("submit", data, 2)
    for cid in (3, 4, 5):
        data = class_proposal(root, "ウィッチ")
        data["roles"].append({"card_id": cid, "role": "不正採用の検査"})
        send("submit", data, 2)
    send("submit", class_proposal(witch, "ドラゴン"), 2)
    checks.append("クラス未指定・無効値・混在・ローテ対象外・生成専用札の直接採用・途中のクラス変更を拒否")
    effect = class_proposal(dragon, "ドラゴン")
    effect["roles"].append({"card_id": 5, "role": "効果経由の検査", "access": "effect", "via": [7]})
    send("submit", effect)
    review_packet = cli("packet", session, "--revision", "3", "--stage", "review")
    send("review", assessment(review_packet))
    current = cli("packet", session, "--revision", "3")
    assert current["data"]["history"][0]["proposal"]["class_name"] == "ドラゴン"
    result = cli("report", session)
    assert [r["class_name"] for r in result["revisions"]] == ["ウィッチ", "ドラゴン", "ドラゴン"]
    assert result["revisions"][2]["reviews"][0]["class_name"] == "ドラゴン"
    checks.append("効果経由の札、親分岐、別評価、履歴、reportに選んだクラスを保持")
    single = str(temp / "single")
    cli("start", single, "--db", str(db), "--class", "ウィッチ", "--objective", "旧回答の機能検査")
    old = proposal(cli("packet", single))
    answer_path.write_text(json.dumps(old), encoding="utf-8")
    cli("submit", single, str(answer_path))
    checks.append("単一クラスのclass_nameなし旧回答を公開CLIで受理")
    assert hashlib.sha256(db.read_bytes()).hexdigest() == original_hash
    checks.append("入力人工DBのSHA256が開始前後で一致")

with gzip.open(OUT / "cli-log.jsonl.gz", "wt", encoding="utf-8") as handle:
    for record in records:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
(OUT / "cli-result.json").write_text(json.dumps({
    "verdict": "PASS", "checked_at": datetime.now(timezone.utc).isoformat(),
    "checks": checks, "command_count": sum("argv" in r for r in records),
    "scope": "人工DBの公開CLI機能検査。効果の実在・強さ・発見力を評価しない。",
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"verdict": "PASS", "checks": len(checks)}, ensure_ascii=False))
