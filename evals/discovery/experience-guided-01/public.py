from pathlib import Path
import os,subprocess,sys
w=Path(__file__).resolve().parent
py='/tmp/sv-system-venv/bin/python'
raise SystemExit(subprocess.call([py,str(w/'record-command.py'),'--output',str(w/'operations'),'--cwd',str(w),'--',py,str(w/'dispatch.py'),*sys.argv[1:]],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}))
