import os, json, hashlib, shutil, subprocess, gzip, tarfile
from pathlib import Path
from datetime import datetime, timezone
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker'); out=root/'evals/discovery/fresh-royal-01'; base=Path('/tmp/sv-fresh-royal-01'); w=base/'generation/work'; s=w/'session'; py='/tmp/sv-system-venv/bin/python'; env={**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONDONTWRITEBYTECODE':'1'}
def now(): return datetime.now(timezone.utc).isoformat()
def save(p,d): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def call(*args): return json.loads(subprocess.check_output([py,'-m','svdeck.discovery',*map(str,args)],env=env))
started=now(); protocol=json.loads((out/'protocol.json').read_text()); before=sha(root/'data/cards.db'); assert before==protocol['main_db_sha256']
result=call('start',s,'--class','ロイヤル','--format','rotation','--objective','ローテーションのロイヤルで、一般に広まった通常の使い方との差と採用負担を説明できる、独自でそこそこ戦えるデッキの種を一つ考える。カードの別用途、複数段の接続、基盤との役割配分を使える。完成40枚や勝率証明は求めない。')
attached=[]
for article in ('527767','573927','559138'):
 p=out/f'article-{article}.json'; attached.append({'article':article,'sha256':sha(p),'result':call('attach',s,p)})
for name in ('public.py','record-command.py'): shutil.copy2(root/'evals/discovery/fresh-reference-01'/name,w/name)
summary=call('packet',s,'--summary'); save(w/'input-summary.json',summary); save(out/'generation/input-summary.json',summary)
initial={str(p.relative_to(s)):sha(p) for p in s.rglob('*') if p.is_file()}; save(out/'generation/initial-files.json',initial); save(w/'initial-files.json',initial)
old=json.loads((root/'evals/discovery/article-rationale-01/a/input-summary.json').read_text()); oldwork='/tmp/sv-article-rationale-01/a/work'
prompt=(root/'evals/discovery/article-rationale-01/a/prompt.md').read_text().replace(oldwork,str(w)).replace(old['sha256'],summary['sha256'])
# No narrative summary is supplied here; update only this irrelevant wrapper description.
prompt=prompt.replace('初期の限定要約と原文引用を区別し','記事の取得情報・要約と原文引用を区別し')
(w/'prompt.md').write_text(prompt); (out/'generation/prompt.md').write_text(prompt)
archive=root/'data/discovery-archives/fresh-royal-01/initial-generation.tar.gz'; archive.parent.mkdir(parents=True,exist_ok=True); assert not archive.exists()
with tarfile.open(archive,'w:gz') as t:
 for name in sorted(initial): t.add(s/name,arcname=name,recursive=False)
with tarfile.open(archive) as t:
 assert {m.name for m in t if m.isfile()}==set(initial)
 for name,d in initial.items():
  f=t.extractfile(name); assert f is not None and hashlib.sha256(f.read()).hexdigest()==d
(out/'context.json.gz').write_bytes(gzip.compress((s/'context.json').read_bytes()))
shutil.copytree(s,root/'data/discovery/fresh-royal-01-generation-initial')
assert before==sha(root/'data/cards.db')
preparation={'started_at':started,'ended_at':now(),'public_start':result,'articles':attached,'input_frozen_at':now(),'packet_hash':summary['sha256'],'context_hash':summary['context_hash'],'initial_files':len(initial),'source_count':len(json.loads((s/'packets'/f"{summary['sha256']}.json").read_text())['data']['sources']),'archive':{'path':str(archive.relative_to(root)),'sha256':sha(archive)},'main_db_unchanged':True,'implementation':{'discovery.py':sha(root/'src/svdeck/discovery.py'),'worker.py':sha(root/'src/svdeck/worker.py'),'worker_journal.py':sha(root/'src/svdeck/worker_journal.py')},'prompt_change_from_prior_baseline':'作業先・識別値と、初期に限定要約を渡さないことの説明だけ変更。DEVELOP指示は現行のまま。'}
save(out/'preparation.json',preparation)
(out/'README.md').write_text('# 新しいロイヤル入力で、現在の探索工程を試す\n\n進化・海賊・連携ロイヤルの記事から、各40枚の参考構築と取得情報を保存しました。これから初回案の考案に進みます。正式案・独立評価はまだありません。\n\n現行の考案指示を使い、最大30分で一つの種を提出します。別担当が最大15分で成立と試す価値を評価します。追加検討という評価で具体的な問いが残る場合だけ、改訂を30分、再評価を15分まで一度ずつ行います。各工程の開始・終了は実行側から自動記録します。\n\n判定は、手順の完了、ゲーム上の正しさ、改訂の実質的な進展、試す理由、未確認事項の扱いの5点です。種への到達とシステム全体の完成は分けます。既存DBと注記を使うため、知識を遮断した試験ではありません。記事本文の採用理由や現行の強さは、この40枚取得だけで確認済みにしません。\n')
r=json.loads(subprocess.check_output([py,'-m','svdeck.experiments','--root',str(root),'show','fresh-royal-01'],env=env)); record=r['record']; record['summary']='参考3構築・取得情報6資料を固定。初回考案の開始待ち。'; record['result']['summary']='入力固定が完了。探索結果はまだない。'; record['stages'][0].update(status='completed',ended_at=now(),note='公開入口で3記事の各40枚と取得情報を保存。初期入力・資料識別値とアーカイブを照合。カードDBの変更なし。')
record['evidence_paths']+=['evals/discovery/fresh-royal-01/preparation.json','evals/discovery/fresh-royal-01/generation/input-summary.json','evals/discovery/fresh-royal-01/generation/prompt.md']; save(out/'journal-input.json',record)
res=subprocess.check_output([py,'-m','svdeck.experiments','--root',str(root),'update',str(out/'journal-input.json'),'--expect',str(r['revision']),'--actor','codex','--reason','参考3構築と初期入力を固定し考案の開始準備完了'],env=env); (out/'journal-record.json').write_bytes(res)
print(json.dumps({'packet_hash':summary['sha256'],'source_count':preparation['source_count'],'initial_files':len(initial),'main_db_unchanged':True,'generation_work':str(w)},ensure_ascii=False))
