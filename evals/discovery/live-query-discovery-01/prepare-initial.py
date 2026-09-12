from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,subprocess,shutil,tarfile,io,os
from svdeck import discovery
from svdeck.discovery_run import manifest,copy_session
from svdeck.journal_store import Journal,template,validate
from svdeck.discovery_evidence import read_only
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');e=root/'evals/discovery/live-query-discovery-01';e.mkdir(exist_ok=False);now=datetime.now(timezone.utc).isoformat();base='c2a5ae073e60386015b2c89d9f99f3a5a22baf40';main=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();src=root/'data/discovery/live-query-discovery-01-input';common=Path('/tmp/sv-live-query-discovery-01-common');common.mkdir(exist_ok=False);(common/'docs').mkdir()
for name in ['design.md','rules.md']:(common/'docs'/name).write_bytes(subprocess.check_output(['git','show',base+':docs/'+name],cwd=root))
with read_only(root/'data/cards.db') as db:urls=[x[0] for x in db.execute("SELECT DISTINCT d.url FROM meta_deck d JOIN meta_deck_card m ON m.deck_id=d.id JOIN card k ON k.card_id=m.card_id WHERE d.format='rotation' AND k.class_name='ナイトメア' ORDER BY d.url")]
assert len(urls)==8
criteria='''検索補助を採用した後の、別の新規探索入力による比較。ナイトメア・ローテーションを固定し、保存DBの同クラス記事一覧8URLを同じ時点で取得して、初回案なし・旧評価なしの共通入力にする。このクラス自体や全カードが初見であるとは呼ばず、システム全体の既知知識は両方式で同じにする。
Aは検索入口追加前c2a5ae0の固定コード、Bは採用後の固定コード。両方の固定カードDB、記事8URL、本文・注記・元の一般方針・判定基準は完全同一。一般方針は追加前c2a5ae0のdocsを共通にする。異なるのは未提出新要求のquery操作と、その公開案内のみ。queryの使用を強制せず、カードの答え・具体タグ・期待するデッキや評価は開発者が与えない。
考案20分・独立した別評価10分を両方式で各一度、既存明示終了を使う。追加の自動改訂や時間切れのやり直しはしない。提出や評価の失敗も記録し、未評価をゼロ点に補完しない。
queryの使用回数、そこから生じた新しい問いや不足の解決、本文と両側注記の照合、追加候補を検索前にも読んでいたかを公開記録で確認する。queryのヒット数・単なるカード取得・計算訂正を主成果にしない。
主成果は、通常構築と同じ状態の比較から試す理由があり、一般に広まった使い方の言い直しでない根拠がある着想。試用推薦・独自性・指定条件の手順成立を分ける。別評価が追加した手順や判定差を、提案担当の発見やqueryの効果に加算しない。
1件ずつの結果の差だけで一般的な因果効果を認定しない。Bが実質的な発展と試用理由へ至っても、query以前から持っていた候補や他の推論の寄与を区別する。Bがqueryを使わない場合は検索機能の有用性未評価とし、未使用の理由を見える範囲で残す。Aも同じ発展を見つければBの上乗せとはしない。
試用推薦された案で独自性の問いが新たに残る場合は、結果回収後に両方式同じ条件で既存の先例調査15分・別照合10分へ一度接続する。記事取得時刻を記事の新しさ、掲載時点のルール適合や一般普及の証明にしない。実戦勝率・Tierは評価対象外。'''
proto={'id':e.name,'fixed_at':now,'parent_experiment':'live-query-01','base_commit':base,'query_commit':main,'class_name':'ナイトメア','format':'rotation','articles':urls,'article_selection':'保存DB内のローテーション・ナイトメア記事の全8URL。個別カードを読む前に固定。','common_docs_manifest':manifest(common/'docs'),'source':str(src),'db_sha256':hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest(),'criteria':criteria,'criteria_sha256':hashlib.sha256(criteria.encode()).hexdigest(),'develop_seconds':1200,'review_seconds':600,'model_override':None};(e/'protocol.json').write_text(json.dumps(proto,ensure_ascii=False,indent=2)+'\n')
body='''# 考案中に検索できることが、案の発展につながるか

**検索入口あり・なしの比較用に、共通入力を準備中です。結果と方法の有用性は未判定です。** 検索補助の採用を、新しい着想の発見力の証明にしないための次の検証です。

ナイトメアのローテーションを対象に、保存済みの記事一覧8URLを同じ時点で取得します。個別カードや特定デッキの答えは指定しません。新しい探索入力を作りますが、このクラスや全カードが初見という意味ではありません。

両方式には、カード本文・注記・記事・一般方針・判定基準を同一版で渡します。入口なしは既存の本文読出しと提出済みの問いの検索を使い、入口ありは考案中の新しい条件も検索できます。検索の使用は強制しません。

考案20分・別評価10分を各一度実行します。検索回数や候補件数ではなく、どの不足が解決し、通常構築と比較して試す理由が残ったかを調べます。検索前から候補を読んでいた場合や、評価者が補った手順を区別します。一回ずつの結果差で一般的な効果は断定しません。

[開始前の条件](protocol.json)。工程の開始・終了と上限は[進捗画面](http://127.0.0.1:8765/#experiment/live-query-discovery-01)に保存します。
''';(e/'README.md').write_text(body)
r=template(e.name);r.update(title='考案中に検索できることが案の発展につながるか',category='method',status='running',summary='検索入口あり・なしを同じナイトメアの新規入力で比較する。8記事の取得と固定入力の準備中。',method='固定入力と既存の考案・別評価を揃え、考案中のquery操作と案内の有無を比べる。',procedure=criteria,inputs='ナイトメア・ローテーション、保存DBと8記事URLを同一版で取得。案・評価を引き継がない新規入力。',criteria=criteria,started_at=now,stages=[{'id':'prepare','title':'8記事を取得し両方式の共通入力を固定','status':'running','started_at':now,'ended_at':None,'note':'記事一覧をカード読出し前に固定。取得日時・限界は資料へ保存する。','budget_minutes':5}]+[{'id':side+'-'+stage,'title':title+label,'status':'planned','started_at':None,'ended_at':None,'note':'同じ入力で各一度。具体カードや期待結論は与えない。','budget_minutes':limit} for side,title in [('a','入口なしの'),('b','入口ありの')] for stage,label,limit in [('develop','考案',20),('review','別評価',10)]],evidence_paths=['evals/discovery/live-query-discovery-01/README.md','evals/discovery/live-query-discovery-01/protocol.json']);validate(r);j=Journal(root);j.save(r,0,'codex-root','検索補助採用後の別入力比較の条件を固定');(e/'journal-record.json').write_text(json.dumps(j.get(e.name),ensure_ascii=False,indent=2)+'\n')
for side in ['a','b']:
 launch=Path('/tmp/sv-live-query-discovery-01-'+side+'-launch');launch.mkdir(exist_ok=False)
 if side=='a':
  raw=subprocess.check_output(['git','archive',base,'src/svdeck'],cwd=root)
  with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
   for member in tar.getmembers():
    if member.isfile():
     target=launch/'runtime'/Path(member.name).relative_to('src');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(tar.extractfile(member).read())
 else:shutil.copytree(root/'src/svdeck',launch/'runtime/svdeck',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copytree(common/'docs',launch/'docs');(e/(side+'-runtime.json')).write_text(json.dumps({'frozen_at':datetime.now(timezone.utc).isoformat(),'runtime':str(launch/'runtime'),'manifest':manifest(launch/'runtime'),'docs_manifest':manifest(launch/'docs')},ensure_ascii=False,indent=2)+'\n')
a=json.loads((e/'a-runtime.json').read_text());b=json.loads((e/'b-runtime.json').read_text());assert a['manifest'].keys()==b['manifest'].keys();diff=[k for k,v in a['manifest'].items() if b['manifest'][k]!=v];assert diff==['svdeck/discovery.py','svdeck/discovery_run.py'];assert a['docs_manifest']==b['docs_manifest']
started=datetime.now(timezone.utc).isoformat();(e/'article-start.json').write_text(json.dumps({'started_at':started,'articles':urls},ensure_ascii=False,indent=2)+'\n')
try:
 result=discovery.start(src,root/'data/cards.db','ナイトメア','rotation','独自で、強い基盤に無理なく入り、通常構築との比較から試す理由があるデッキの種を考案してください。',docs=common/'docs',articles=urls)
 packet=discovery.packet(src,0,'develop');preview=common/'a-preview';copy_session(src,preview);p=subprocess.run(['/tmp/sv-system-venv/bin/python','-B','-m','svdeck.discovery','packet',str(preview),'--revision','0','--summary'],capture_output=True,text=True,check=True,env={**os.environ,'PYTHONPATH':a['runtime']});assert json.loads(p.stdout)['sha256']==packet['sha256'];assert hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest()==proto['db_sha256'];end=datetime.now(timezone.utc).isoformat();proof={'article_start':result,'articles_started_at':started,'ended_at':end,'initial_packet_hash':packet['sha256'],'packet_same_both':True,'source_manifest':manifest(src),'only_runtime_differences':diff,'common_docs_identical':True,'cards_count':len(packet['data']['context']['cards']),'sources_count':len(packet['data']['sources']),'formal_revisions':0,'formal_reviews':0};(e/'preparation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
 with tarfile.open(e/'input.tar.gz','w:gz') as tar:tar.add(src,arcname='session')
 c=j.get(e.name);r=c['record'];r['stages'][0].update(status='completed',ended_at=end,note='8記事から共通入力を作成。両方式で初回入力の識別が完全一致。元DB保持を確認。');r['summary']='共通入力を準備し、検索入口と公開案内以外の固定入力一致を確認。両方式の考案・別評価を各一度開始する。';r['evidence_paths'] += ['evals/discovery/live-query-discovery-01/'+n for n in ['a-runtime.json','b-runtime.json','article-start.json','preparation.json','input.tar.gz']];j.save(r,c['revision'],'codex-root','8記事の取得と両方式の共通入力を確認');(e/'journal-record.json').write_text(json.dumps(j.get(e.name),ensure_ascii=False,indent=2)+'\n');print({k:proof[k] for k in ['articles_started_at','ended_at','initial_packet_hash','packet_same_both','cards_count','sources_count']})
except Exception as exc:
 end=datetime.now(timezone.utc).isoformat();(e/'preparation-failure.json').write_text(json.dumps({'started_at':started,'ended_at':end,'error':repr(exc),'source_exists':src.exists(),'note':'取得失敗を保存。実AIは未起動。'},ensure_ascii=False,indent=2)+'\n');c=j.get(e.name);r=c['record'];r['stages'][0].update(status='interrupted',ended_at=end,note='入力準備が失敗。実AI未起動。詳細はpreparation-failure.json。');r['status']='waiting';r['evidence_paths'].append('evals/discovery/live-query-discovery-01/preparation-failure.json');j.save(r,c['revision'],'codex-root','共通入力準備の失敗を保存');raise
