from pathlib import Path
from datetime import datetime,timezone
import json,shutil,subprocess,tarfile,io,hashlib
from svdeck.discovery_run import manifest,check_unchanged,verify_submission
from svdeck.journal_store import Journal,template
from svdeck import discovery
root=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker');eid='remaining-resource-inquiry-01';e=root/'evals/discovery'/eid;e.mkdir(exist_ok=False);started=datetime.now(timezone.utc);source=root/'data/discovery/remaining-question-01-a-result';review_file=next(source.glob('review-0003-*.json'));review=json.loads(review_file.read_text());question=review['data']['next_questions'][0];original=manifest(source);verify_submission(source,'develop',3);verify_submission(source,'review',3);report=discovery.report(source);commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();runtime=Path('/tmp/sv-remaining-resource-inquiry-01-launch/runtime');runtime.mkdir(parents=True,exist_ok=False)
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive',commit,'src'],cwd=root))) as tar:
 for member in tar.getmembers():
  path=Path(member.name);assert not member.issym() and not member.islnk() and '..' not in path.parts and path.parts[0]=='src'
  if member.isfile():
   dest=runtime.joinpath(*path.parts[1:]);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(tar.extractfile(member).read())
assert manifest(root/'src')==manifest(runtime)
criteria=['既存調査→別照合の適用確認。コード・指示の新設なし。focused-inquiry-01/inquiry-to-revision-01と重なる既存工程の別用途への再検証であり、新手法や本体の追加採用とはしない。','前試験の現行Aから残った先頭の問いを選ぶ固定規則。対象は保存済みT6比較の終点後のEP使途で、通常側のSEPと自動進化という代替も含む未比較箇所。根拠が得られない結論を許し、成功状態・カード答案をrootから与えない。','調査15分・別照合10分、各1回のみ。自然終了を確認する既存経路を使用。時間切れは部分資料を保持し、再実行・代理提出しない。正式改訂・強さの再採点はこの実行では行わない。','元案・旧評価・固定DBと実装を保持し、報告の正式添付・全文再読・report一致を確認する。これは動作の検証で、資料数や完走を有用性に数えない。','問いに新しく答えた根拠、通常側でもできる分、相手・引き込み・生存の未確認を別照合する。使途と採用利益につながる根拠がなければ未解決を記録し、同じ問いの言い換えで追加工程へ自動継続しない。','同時対照なし・既知入力1件のため、調査を分けることの一般的効果や発見力は認定しない。独自性や実戦勝率も自動認定しない。']
proto={'id':eid,'fixed_at':started.isoformat(),'parent':'remaining-question-01','source':str(source),'source_manifest':original,'source_archive':'evals/discovery/remaining-question-01/a/session.tar.gz','revision':3,'review_hash':review['sha256'],'question_index':0,'question':question,'criteria':criteria,'criteria_sha256':hashlib.sha256('\n'.join(criteria).encode()).hexdigest(),'research_seconds':900,'inspect_seconds':600,'attempts_per_stage':1,'model_override':None,'code_changed':False,'base_commit':commit,'runtime':str(runtime),'runtime_manifest':manifest(runtime),'main_db_sha256':hashlib.sha256((root/'data/cards.db').read_bytes()).hexdigest(),'instruction_scope':'既存のRESEARCH/INSPECTをそのまま使用。別評価第1問を完全一致で渡す。','output':'/tmp/sv-remaining-resource-inquiry-01-live'}
assert proto['main_db_sha256']=='11aef89fae292ce671781ce31da124d695b15b28f64d7813c6e0c9ad720e1414';check_unchanged(source,original,exact=True);ended=datetime.now(timezone.utc);proto['preparation_ended_at']=ended.isoformat();(e/'protocol.json').write_text(json.dumps(proto,ensure_ascii=False,indent=2)+'\n');shutil.copyfile('/tmp/prepare-remaining-resource-inquiry.py',e/'prepare.py');shutil.copyfile('/tmp/comparison-handoff-public-next.json',e/'public-api-check.json');shutil.copyfile('/tmp/comparison-handoff-gap.json',e/'prior-gap-check.json')
(e/'README.md').write_text(f'''# 温存した進化権の使い道を、既存の調査工程で確認する

**条件と入力を固定しました。調査・別照合はこれからで、有用性は未判定です。追加実装はありません。**

前の比較では、温存できた進化権が何に役立つかを示せず、両方式とも追加検討に残りました。既存の一問調査と別照合へ、現行側の正式評価の先頭の問いをそのまま渡します。使う道具や指示は変えず、残った問いの種類を変えた適用確認です。前の追加指示は本体採用保留を維持します。

## 調べる問いと判断

> {question}

T6の保存比較に続く使途と、通常側の代用手段との差が未比較の対象です。根拠が得られない結果も残します。既に確認した温存量の言い換え、未知のドローや盤面生存を足した利益、通常側にもできる利益を新しい成果にしません。

調査報告が正式保存され、別担当が根拠と問いへの答えを照合できた時に工程完了とします。使う理由の裏付けが得られたかは別に判断します。この実行では元案の改訂や強さの再採点はしません。資料数や正常終了だけでは有用な種の発見と数えません。

## 手順・現在地・時間

1. 保存済みの正式改訂3件・評価2件・資料27件を保持し、先頭の問いを選びました。固定入力は{len(original)}ファイルです。
2. 公開入口で番号指定を渡せることをコードと実ヘルプで確認し、既存実装を固定しました。新しいコード変更はないため、90件の検査を今回の新規検査数として加算しません。
3. 調査15分・別照合10分を各一度行います。開始・終了は[進捗画面](http://127.0.0.1:8765/#experiment/{eid})へ記録します。現在は起動前です。
4. 保存物・全文再読・元案と旧評価の保持を回収時に照合し、新しく答えた範囲と未確認を報告します。根拠のないまま同じ問いを繰り返しません。

準備は日本時間{started.astimezone().isoformat()}〜{ended.astimezone().isoformat()}、{(ended-started).total_seconds():.3f}秒です。調査・照合は未着手で、終了時刻はまだありません。既存の調査経路は自然終了を待ち、期限停止時は部分保存があっても成功へ変更しません。

これは過去の一問調査・改訂接続の再検証に当たります。同時対照のない既知入力1件から、工程分離の一般的な優越・独自性・実戦勝率を認定しません。

[条件と固定入力](protocol.json)・[既存入口の適合確認](public-api-check.json)・[前試験と既存実装の重複確認](prior-gap-check.json)を保存しました。
''')
j=Journal(root);r=template(eid);r.update({'title':'温存した進化権の使い道を、既存の調査工程で確認する','status':'running','summary':'既存の一問調査と別照合へ、温存EPの具体的な使途という残問を渡す適用確認。追加実装なし、起動前。','method':'保存された第1問を既存の調査・別照合へ渡し、根拠の追加と未確認範囲を検査する。','procedure':'\n'.join(criteria),'inputs':f'現行Aの正式改訂3・評価2・資料27。同じ{len(original)}ファイルと先頭の問いを保持。','criteria':'\n'.join(criteria),'started_at':started.isoformat(),'stages':[{'id':'prepare','title':'問いと入力・実装・判断条件を固定','status':'completed','started_at':started.isoformat(),'ended_at':ended.isoformat(),'note':'正式案・評価の対応、元入力、現行srcと隔離実装の完全一致を確認。追加実装なし。','budget_minutes':5},{'id':'live-inquiry','title':'温存した進化権の具体的な使途を調査','status':'planned','started_at':None,'ended_at':None,'note':'保存評価の先頭の問いをそのまま渡し、根拠と未確認を資料保存。具体答えはrootから与えない。','budget_minutes':15},{'id':'live-inspect','title':'調査の根拠と問いへの答えを別照合','status':'planned','started_at':None,'ended_at':None,'note':'正式保存・出典の裏付け・新しく答えた範囲を確認。工程完了と有用性を区別。','budget_minutes':10}],'evidence_paths':['evals/discovery/'+eid+'/'+n for n in ['protocol.json','prepare.py','README.md','public-api-check.json','prior-gap-check.json']]});j.save(r,0,'codex-root','既存一問調査の適用確認として条件固定。新実装の効果比較とはしない');(e/'journal-record.json').write_text(json.dumps(j.get(eid),ensure_ascii=False,indent=2)+'\n');print({'experiment_id':eid,'prepared_at':ended.isoformat(),'input_files':len(original),'runtime':str(runtime),'review_hash':review['sha256']})
