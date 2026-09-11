import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, '/private/tmp/sv-cycle-runner-01/round-1/runtime')
from svdeck.discovery_run import public_main
raise SystemExit(public_main(Path(__file__).resolve().parent))
