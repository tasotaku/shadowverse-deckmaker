from pathlib import Path
from datetime import datetime,timezone
import json,sys,shutil,uuid
from svdeck import discovery,worker
from svdeck.discovery_run import copy_session,manifest,check_unchanged
from svdeck.discovery_read import packet_summary
from svdeck.discovery_evidence import write_new
from svdeck.discovery_inquiry import verify_report
from svdeck.worker_journal import RunJournal
from svdeck.journal_store import Journal
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker'); source=root/'data/discovery/resource-use-01-b-result';output=Path('/tmp/sv-live-query-01-use');runtime=Path('/tmp/sv-live-query-01-launch/runtime');work=output/'use';original=manifest(source);runtime_before=manifest(runtime)
assert all(s['status']=='planned' for s in Journal(root).get('live-query-01')['record']['stages'] if s['id'] in ['live-use','inspect'])
output.mkdir(exist_ok=False);copy_session(source,work/'session');parent=2;packet=discovery.packet(work/'session',parent,'develop');key=packet['sha256'];run_id=uuid.uuid4().hex;kind='live-query-use';location=f'live-query:{run_id}:use';config={'stage':'develop','revision':parent,'packet_hash':key,'author':f'worker:{run_id}:use','report_kind':kind,'report_location':location,'explicit_finish':False}
write_new(work/'public-config.json',config);write_new(work/'input-summary.json',packet_summary(work/'session',key));(work/'public.py').write_text('import sys\nsys.dont_write_bytecode = True\nfrom pathlib import Path\nsys.path.insert(0, '+repr(str(runtime))+')\nfrom svdeck.discovery_run import public_main\nraise SystemExit(public_main(Path(__file__).resolve().parent))\n')
prompt=f'''今回は、考案中の新要求を検索する公開入口の利用確認です。デッキ案の作り直しや正式な改訂・評価の提出は行いません。保存された案・残った問いから、さらに検索すると判断に役立つ問いを1件だけ自分で選び、提供された語彙で空でない検索条件へ対応づけ、queryで既存の型検索へ渡してください。既存searchの問いと条件をそのまま再実行するのでなく、未確定の点から新しい条件を具体化してください。個別カードや特定の答えは指定されていません。
型検索が返した候補の本文・進化・参照先・主役と候補双方の注記を固定資料から読み、問いに対して何を確認できたか、何が未確認かを書いてください。一致0なら調べた条件と範囲を記し、全範囲で不可能とは断定しません。ヒット件数を強さや新規性の証明にしません。queryは固定DBの型検索で、PP・場・手札や実際の生成可能性の証明ではありません。

上限は待ち時間込み経過360秒、今回1回だけです。残り秒は {sys.executable} -c "import os,time; print(float(os.environ['SVDECK_DEADLINE_MONOTONIC']) - time.monotonic())" で確認できます。UTCの開始・終了と経過時計は区別してください。
入力は次の公開入口だけで読みます。作業先外、親会話、実装、別探索、私的な実行ログは読みません。既存入力を直接開いたり変更したりしません。公開操作の出力を自分の作業先へ保存し再読してよいですが、私的な思考過程は転記しません。
{sys.executable} public.py --help
{sys.executable} public.py packet --summary
{sys.executable} public.py read {key} SECTION --offset 0 --limit 20
{sys.executable} public.py query --question '自分で選んだ問い' --tag '自分で対応づけた条件'
案はproposal、残問はprevious_reviews/search、カード本文と注記はcards、語彙はfulfillment_mapやcardsのtagsです。readの返すoffset/next_offsetで分割して読めます。1ページのlimitは100以下です。query結果の参照案内から候補の本文・注記を照合してください。queryは読み取りのみであり、以下の添付が成果保存になります。

answer.mdへ、選んだ問い・対応づけた検索条件と理由・query結果の原文JSON・固定版の識別・候補本文と注記の引用・その候補が満たす条件と残る制約・確認時刻・この道具でできたことと未確認のことを簡潔にまとめてください。外部検索、採点変更、formal submit/review、追加の新要求検索は不要です。
{sys.executable} public.py attach-file answer.md --title '考案中の新要求を検索した利用報告' --kind {kind} --location {location}
添付後にpacket --summaryを再取得し、新しい識別値のsourcesから自分の追加報告の全文を公開readで再読してください。全旧資料を読み直す必要はありません。添付前後のsources行数と返った内容から位置を特定できます。最後に {sys.executable} public.py report で保存を確かめ、通常終了してください。finishは正式な改訂・評価用のため今回は使いません。保存できなければ代理提出は求めず、その事実をfinal-messageへ書いてください。
最終回答には報告の識別値と実際に確認した結論・未確認だけを短く記してください。
'''
(work/'prompt.md').write_text(prompt);fixed=manifest(work);result={'id':'live-query-01','run_id':run_id,'status':'running','started_at':datetime.now(timezone.utc).isoformat(),'source':str(source),'work':str(work),'source_manifest':original,'runtime_manifest':runtime_before,'packet_hash':key,'limits':'既知入力での検索補助の利用確認。正式案・評価は追加しない。私的stdout/JSONLは監査・収集しない。'};worker.save_record(output/'result.json',result)
cmd=['/Applications/ChatGPT.app/Contents/Resources/codex','exec','--ephemeral','--sandbox','workspace-write','--skip-git-repo-check','--cd',str(work),'--json','--output-last-message',str(work/'final-message.md'),'-']
code,record=worker.run(cmd,output/'use-run',360,2,work,work/'prompt.md','elapsed',RunJournal(root,'live-query-01','live-use'))
result.update(returncode=code,run=record,ended_at=datetime.now(timezone.utc).isoformat());worker.save_record(output/'result.json',result)
try:
 check_unchanged(source,original,exact=True);check_unchanged(runtime,runtime_before,exact=True);check_unchanged(work,fixed)
 result['report_verification']=verify_report(work,config)
 ops=[json.loads(p.read_text()) for p in (work/'operations').glob('*.json')]
 queries=[p for p in ops if p['args'] and p['args'][0]=='query' and '--help' not in p['args']]
 assert len(queries)==1 and queries[0]['exit_code']==0,'query must succeed exactly once'
 assert len(list((source).glob('revision-*.json')))==len(list((work/'session').glob('revision-*.json')))
 assert len(list((source).glob('review-*.json')))==len(list((work/'session').glob('review-*.json')))
 result.update(status='completed' if code==0 else 'incomplete',query=queries[0],source_runtime_preserved=True,formal_records_added=0)
except Exception as exc:result.update(status='verification_failed',verification_error=str(exc))
worker.save_record(output/'result.json',result)
print(json.dumps({k:v for k,v in result.items() if k in ['id','run_id','status','started_at','ended_at','returncode','report_verification','verification_error','source_runtime_preserved','formal_records_added']},ensure_ascii=False,indent=2))
