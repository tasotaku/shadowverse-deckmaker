from pathlib import Path
from datetime import datetime,timezone
import os,json,subprocess,time
out=Path(os.environ["SVDECK_RUN_DIR"])
cmd=["/tmp/sv-system-venv/bin/python","-m","svdeck.discovery","read","/tmp/sv-principles-scope-01/elf/a/session","f76f9722d050a36dbb3d6178ed3b8418e74a81ca6df34f69582e460baddbc876","cards","--offset","0","--limit","1"]
start=datetime.now(timezone.utc).isoformat()
r=subprocess.run(cmd,env={**os.environ,"PYTHONPATH":"/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/src","PYTHONDONTWRITEBYTECODE":"1"},capture_output=True,text=True)
(out/"read.json").write_text(r.stdout)
(out/"read-operation.json").write_text(json.dumps({"command":cmd,"started_at":start,"ended_at":datetime.now(timezone.utc).isoformat(),"exit_code":r.returncode,"stderr":r.stderr},ensure_ascii=False,indent=2)+"\n")
r.check_returncode()
print("public read saved; deliberate stall starts",flush=True)
time.sleep(20)
(out/"late-write.txt").write_text("should not be created")
