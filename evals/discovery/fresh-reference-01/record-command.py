"""Record one public command without colliding with concurrent recordings."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    # AI_NOTE: 実行前に固有の記録を確保し、同時読出しでも本文と日時を取り違えない。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command: list[str] = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("command is required after --")
    args.output.mkdir(parents=True, exist_ok=True)
    descriptor, filename = tempfile.mkstemp(prefix="operation-", suffix=".json", dir=args.output)
    os.close(descriptor)
    path = Path(filename)
    stdout_path = path.with_suffix(".stdout.txt")
    record: dict[str, object] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "command": command,
        "cwd": str(args.cwd),
        "exit_code": None,
        "output": str(stdout_path),
        "stderr": None,
        "state": "started",
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    try:
        result = subprocess.run(command, cwd=args.cwd, capture_output=True, text=True)
    except OSError as error:
        record.update(ended_at=datetime.now(timezone.utc).isoformat(), state="launch_failed", error=str(error))
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        print(error, file=sys.stderr)
        return 127
    stdout_path.write_text(result.stdout)
    record.update(ended_at=datetime.now(timezone.utc).isoformat(), state="completed", exit_code=result.returncode, stderr=result.stderr)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
