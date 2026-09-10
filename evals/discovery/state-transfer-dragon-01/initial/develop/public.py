import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, '/private/tmp/sv-state-transfer-dragon-01/initial/runtime')
from svdeck.discovery_run import public_main
raise SystemExit(public_main(Path(__file__).resolve().parent))
