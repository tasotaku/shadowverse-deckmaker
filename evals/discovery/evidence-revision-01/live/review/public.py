import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, '/private/tmp/sv-evidence-revision-01/run/runtime')
from svdeck.discovery_run import public_main
raise SystemExit(public_main(Path(__file__).resolve().parent))
