from pathlib import Path
import os,subprocess,sys
w=Path(__file__).resolve().parent
p='/tmp/sv-system-venv/bin/python'
raise SystemExit(subprocess.call([p,str(w/'record-command.py'),'--output',str(w/'operations'),'--cwd',str(w),'--',p,'-m','svdeck.discovery',*sys.argv[1:]],env={**os.environ,'PYTHONPATH':'/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker/src','PYTHONDONTWRITEBYTECODE':'1'}))
