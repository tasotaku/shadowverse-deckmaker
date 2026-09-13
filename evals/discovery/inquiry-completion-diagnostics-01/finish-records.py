"""Record observed results and decision; do not repair failed actor submissions."""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
from svdeck.journal_store import Journal

root = Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker')
base = root / 'evals/discovery'
j = Journal(root)
now = datetime.now(timezone.utc)
iso = now.isoformat()
stamp = now.astimezone(ZoneInfo('Asia/Tokyo')).strftime('%Y年%m月%d日 %H:%M:%S')
d = base / 'inquiry-completion-diagnostics-01'
i = base / 'remaining-resource-inspection-01'
implementation = json.loads((d/'implementation.json').read_text())
cli = json.loads((d/'main-cli-check.json').read_text())
reproduction = json.loads((d/'main-reproduction.json').read_text())
v = json.loads((i/'verification.json').read_text())
diagnosis = json.loads((i/'completion-diagnosis.json').read_text())
assert cli['returncode'] == 0 and implementation['verdict'] == 'PASS'

(d/'README.md').write_text('''# 提出確認のどこで止まったかを分かるようにする

**不足した操作の表示と手順案内を、診断補助として採用しました。機能検査100件・型検査が通り、本体へ反映後の公開操作の確認2件も通っています。実AIがこの案内で提出失敗を減らせるか、デッキ発見力が改善するかは未確認です。**

前の調査は、本文の添付と全文再読を済ませた後、完了時刻の資料を追加し、最後の報告確認をしないまま終了しました。同じエラー文では不足操作を特定できなかったため、添付・全文再読・最新状態の報告確認を区別して知らせます。追加資料を全て保存した後に確認を行う手順も明記しました。

受理条件、資料形式、操作権限、時間上限は維持しています。過去の失敗を成功へ書き換えず、不足操作を代理で補っていません。

## 検証手順と採用理由

1. 実際の公開操作を再検査し、添付と全文再読は成立、最後の資料追加後の報告確認だけが不足と切り分けました。
2. 別の作業場所で、原因表示3種類と案内1文に変更を限定しました。変更箇所を元へ戻すと旧実装と一致することも確認しました。
3. 正常な保存、分割再読、ヘルプを完了に数えない境界、添付・再読・報告確認の不足、本文や固定入力の改変拒否を検査しました。既存89件と新規11件、計100件が通りました。型検査も通っています。
4. 人工資料を使い、公開操作で添付→全文再読→報告確認を行うと受理、追加保存後は拒否、再確認後は受理となることを確かめました。
5. 本体へ取り込み、同じ実装であることと、調査・別照合の公開操作の該当2検査を再確認しました。元の実AIの失敗も本体で再現し、保存物が変わっていないことを確認しました。

採用理由は、不足した操作を特定でき、正しい追加保存後の確認を受理しつつ、未確認の提出を引き続き拒否できたことです。探索手法そのものの採用判断ではありません。

## 工程の時刻

全て2026年09月13日の日本時間です。工程内の観測点は、細工程の正確な開始・終了とは区別しています。

| 工程 | 開始 | 終了 | 時刻差・結果 |
|---|---|---|---|
| 限定実装・型検査・機能検査・公開操作 | 12:59:25 | 13:06:29 | 7分04秒、目安10分内 |
| 本体で旧失敗を読み取り専用で再現 | 13:06:11 | 13:06:11 | 0.20秒、元資料保持 |
| 本体で公開操作の2検査 | 13:12:02 | 13:12:04 | 2.00秒、2件合格 |

初回の100検査は92件成功・8件失敗でした。子プロセスの実装読込パスが相対指定だったことが原因で、検査側を絶対指定へ直して新規11件と全100件を再検査しました。このための本体修正はありません。Python環境に検査道具がない初回の問題も、既存の別Python環境を使って解消しました。

台帳登録は13:01:20で実装着手後です。事前登録した比較試験とは扱いません。実装途中の時刻、検査の失敗と訂正、コマンド、出力、差分は[検査記録](implementation.json)に保存しました。使い捨てテストは元の作業場所に保持し、検査結果を[証拠資料](test-evidence/)へ保存しています。

[最初の判断条件](protocol.json)・[本体での失敗再現](main-reproduction.json)・[本体での公開操作確認](main-cli-check.json)から確認できます。診断修正前の固定実装で動いた後続の別照合も失敗しましたが、この修正の効果試験ではありません。
''')

(i/'README.md').write_text('''# 保存した使途調査から、別照合だけを再開する

**別照合担当は7分54秒で正常終了し、報告と追加3資料を保存しました。ただし最後の提出確認で中断し、この適用検証の採用は保留です。条件付き用途の説明は支持されましたが、構築へ採用する利益とシステム全体の有用性は未確認です。**

## 分かったことと、未解決のこと

温存した通常進化権で味方を戦闘破壊し、出た別個体をもう一度使う手順について、保存されたカード本文との整合を別担当が照合しました。指定された局面内の手順は支持されています。超進化では戦闘ダメージを受けないため同じ仕事にならない、という条件付きの差です。

一方、その局面まで手札と進化権を保持して生存できるか、通常側の他の行動でも同じ利益を得られないか、失う採用枠や準備費用に見合うかは未解決です。記事の説明と担当の解釈が混じった要約も1件指摘され、カード本文からの判断と区別されました。詳細は[照合報告](partial/answer.md)に残しました。条件付き手順の成立を、実戦の強さ・独自性・採用利益へ広げません。

## 提出確認が止まった理由

本文の公開添付と全文再読は済んでいました。13:05:46に報告確認を行った後、13:06:12に完了記録を資料へ追加し、再確認せず終了しています。保存状態が変わったため、最終状態を確認したという条件を満たしませんでした。[公開記録の再検査](completion-diagnosis.json)で添付あり・全文再読あり・最新状態の報告確認なしを再現しました。

この試行は修正前の固定実装で動いています。後で採用した[原因表示と手順案内](../inquiry-completion-diagnostics-01/README.md)の効果検証ではありません。元の失敗を保持し、代理提出や自動再実行は行っていません。

## 方法と検証手順

1. 前の調査で保存した報告を指定し、既存の入口から別照合だけを一度実行しました。調査はやり直していません。
2. 元の42ファイルと調査で加えた資料・入力版を合わせた48ファイル、正式改訂3件・評価2件・資料31件を固定しました。問いと既存指示、保存報告の一致を確認しました。
3. 別照合10分の上限で、裏付け・通常側の代用手段・未確認条件を点検しました。公開操作22回はすべて成功しましたが、最終提出確認は失敗しました。
4. 元の案・評価・資料・固定実装の保持と、報告本文と添付の一致を確認し、追加3資料と停止結果を保存しました。再開用コピーは54ファイル・資料34件です。
5. 提出の失敗と内容面の進展を分けて判断しました。局所的な使い道は具体化しましたが、有用な採用判断への進展を証明できていないため、方法の採用は保留です。

初回の起動照合では、通常生成される評価用入力を追加ファイルとして拒否しました。既存の生成処理を別コピーで再現し、実入力との完全一致へ訂正しています。この失敗も[起動照合記録](launch-verification.json)に残しました。

## 工程の開始・終了

全て2026年09月13日の日本時間です。

| 工程 | 開始 | 終了 | 状態・時刻差 | 目安・上限 |
|---|---|---|---|---|
| 保存済み報告と再開条件を固定 | 12:58:10 | 12:58:11 | 完了、0.318秒 | 5分 |
| 別照合担当の実行 | 12:58:28 | 13:06:21 | 担当終了、473.63秒 | 10分 |
| 最終提出確認 | 不明 | 13:06:22 | 失敗 | — |
| 部分資料と元記録保持を確認・回収 | 13:21:44 | 13:21:46 | 完了、2.07秒 | 5分 |
| 別担当への停止理由の点検依頼 | 不明 | 不明 | 成果未回収のまま中断 | 目安3分 |
| 引き継いで公開記録を再検査 | 17:41:20 | 17:41:21 | 完了、0.71秒 | — |

担当終了後、回収開始まで15分22秒空きました。回収後から原因再検査までも約4時間20分空いています。原因と能動作業時間は不明で、照合担当の7分54秒へ合算しません。別担当の点検は17:40:45時点で成果ファイルがなく、中断して引き継ぎました。実開始・終了の時計は未回収です。

## 次の対応

新しい案内が提出操作に効くかは、今後の別試行で確かめます。元の試行を再採点しません。内容面では、条件付き用途を比較や配分の判断へ戻せるかが残る課題です。旧案・評価・失敗を保持したまま次の検証へ渡せる資料を保存しました。

[事前条件](protocol.json)・[回収確認](verification.json)・[停止理由](completion-diagnosis.json)・[全保存報告](partial/report.json)・[再開用資料](partial/preserved-session.tar.gz)から根拠を辿れます。
''')

def stage(sid, title, start, end, note, status='completed', budget=None):
    return {'id': sid, 'title': title, 'status': status, 'started_at': start,
            'ended_at': end, 'note': note, 'budget_minutes': budget}

c=j.get(d.name); r=c['record']; r.update(status='completed',started_at=implementation['time_utc']['started_at'],ended_at=iso)
r['summary']='不足した提出操作を区別する表示と手順案内を診断補助として採用。100件・型検査と本体の公開操作2検査を確認。発見力は未確認。'
r['result']={'outcome':'pass','summary':'既存89件・新規11件の計100件、型検査と本体の公開操作2件が合格。旧失敗は具体的な原因表示で再現し、元資料は保持。','limitations':'人工入力による機能検査。実AIで失敗が減るか・デッキ発見力が改善するかは未確認。登録は実装着手後。'}
r['decision']={'status':'adopted','reason':'受理条件を維持し、不足操作を特定して正しい再確認を案内できたため。診断補助に限定。'}
r['stages']=[stage('implementation','診断表示と手順の限定修正・検査',implementation['time_utc']['started_at'],implementation['time_utc']['finished_at'],'100件・型検査・人工入力の公開CLI。初回8件失敗は検査の読込パスを訂正。',budget=10),stage('main-reproduction','本体で旧失敗と保存物保持を再確認',reproduction['started_at'],reproduction['ended_at'],'公開記録の読取専用再検査。旧失敗は維持。'),stage('main-cli','本体の公開操作で拒否と再確認後の受理を検査',cli['started_at'],cli['ended_at'],'調査・別照合の人工入力2件が合格。')]
r['evidence_paths']=['evals/discovery/'+d.name+'/'+n for n in ['README.md','protocol.json','implementation.json','main-reproduction.json','main-cli-check.json','test-evidence','finish-records.py']]
j.save(r,c['revision'],'codex-root','実装・機能検査と探索の有用性を区別し、診断補助だけを採用')

c=j.get(i.name); r=c['record']; r.update(status='interrupted',ended_at=iso)
r['summary']='別照合7分54秒で報告と追加3資料を保存したが、最後の追加保存後の確認がなく中断。条件付き用途は支持、採用利益は未確認で保留。'
r['result']={'outcome':'fail','summary':'担当は正常終了、公開22操作・報告本文一致・追加3資料を保存。提出確認は添付と全文再読を満たすが最終reportが不一致。','limitations':'局面内の条件付き用途は別照合で支持。到達過程・通常側の全代案・採用利益・実戦の強さは未確認。旧固定実装の試行であり新診断案内の効果検証ではない。'}
r['decision']={'status':'deferred','reason':'提出確認で中断し、条件付き用途から有用な採用判断へ進めることも未確認。資料保存だけで方法の優位を認定しない。'}
r['stages'] += [stage('submission-check','終了後の最終提出状態を確認',None,'2026-09-13T04:06:22.388915+00:00','開始時刻不明。最後の追加資料後のreportなし。','interrupted'),stage('collect-partial','照合報告・部分資料・停止結果を回収',v['collection_started_at'],v['collection_ended_at'],'元48ファイル保持、追加3資料と入力版を加え54ファイル・34資料。',budget=5),stage('independent-diagnosis','別担当へ停止理由の点検を依頼',None,None,diagnosis['independent_attempt'],'interrupted',3),stage('completion-diagnosis','引継ぎ後に公開記録だけで停止理由を再検査',diagnosis['started_at'],diagnosis['ended_at'],'添付あり・全文再読あり・最新reportなしを再現。72ファイル保持。')]
r['evidence_paths']=['evals/discovery/'+i.name+'/'+n for n in ['README.md','protocol.json','launch-verification.json','collect-partial.py','collection-start.json','verification.json','completion-diagnosis.json','partial']]
j.save(r,c['revision'],'codex-root','担当終了・提出確認失敗・条件付き用途の支持を区別し、時刻と中断も保存')

parent=base/'remaining-resource-inquiry-01'; text=(parent/'README.md').read_text()
text=text.replace('これは未照合の説明で、採用利益や独自性が確認できたという意味ではありません。','当時は未照合の説明でした。後続の別照合では局面内の手順が支持されましたが、採用利益や独自性が確認できたという意味ではありません。')
text=text.replace('再開用コピーを作りました。旧案と評価は保持し、未照合の報告を調べ直さず別照合へ渡します。','再開用コピーを作りました。旧案と評価は保持し、報告を調べ直さず別照合へ渡しました。')
old='システム側では、最後の追加保存後に報告確認が必要だと手順へ明記し、失敗理由を添付・再読・報告確認のどれか分かる表示へ分ける修正を別の作業場所で進めています。受理条件は維持します。この診断補助の実装と、新しい着想の発見力は別に検証します。'
new='システム側の[原因表示と手順案内](../inquiry-completion-diagnostics-01/README.md)は、受理条件を維持した診断補助として採用しました。後続の別照合も旧固定実装で提出確認に失敗し、資料と停止理由を別記録へ保存しました。診断補助の機能確認と、新しい着想の発見力は別です。'
assert old in text; (parent/'README.md').write_text(text.replace(old,new))
c=j.get(parent.name); r=c['record']; r['result']['limitations']='本試行の別照合は未起動。後続の別試行で局面内の条件付き用途は支持されたが、到達過程・採用利益・独自性は未確認。元失敗は維持。'; j.save(r,c['revision'],'codex-root','後続試行の結果と診断補助の採用を参照し、元失敗は保持')

for folder in [d,i,parent]:
    (folder/'journal-record.json').write_text(json.dumps(j.get(folder.name),ensure_ascii=False,indent=2)+'\n')

progress=root/'docs/progress.md'; old=progress.read_text(); marker='以下は過去の実施時点の記録です。当時の「進行中」「次は」は現在の状態ではありません。'
head=f'''# デッキ探索システムの開発経過

更新：{stamp}（日本時間）

**提出に不足した操作を知らせる修正を、実行補助として採用しました。探索手法の有用性は採用保留で、システム全体は未完成です。**

添付・全文再読・最後の報告確認の不足を区別して表示し、全ての資料追加後に確認する手順を明記しました。受理条件は維持しています。機能100件・型検査、本体での公開操作2検査が通りました。実AIの提出失敗を減らせるかは未確認です。[変更・採用理由・検査と時刻](http://127.0.0.1:8765/#experiment/inquiry-completion-diagnostics-01)。

保存済み報告への別照合は7分54秒で終了し、報告と追加3資料を回収しました。条件付きの使い道は支持されましたが、その局面まで到達できるか、通常構築の他の行動より得かは未解決です。提出確認も、最後の追加保存後の確認がなく中断しました。修正前の固定実装で動いた試行として失敗を保持し、新案内の効果試験には数えません。[方法・結果・保留理由・全工程](http://127.0.0.1:8765/#experiment/remaining-resource-inspection-01)。

照合終了から回収開始まで15分22秒、回収後から原因再検査までも約4時間20分空いています。原因と能動作業時間は不明として、担当の実行時間と分けました。別担当への原因点検は成果未回収で中断し、公開記録を引き継いで再現しました。

次は、新案内で提出確認まで進めるかを別試行で確かめ、内容面では条件付き用途を比較・配分の判断へ戻せるかを検証します。現在、新しい実AI試行は未起動です。保存済みの資料を使い、元の失敗と採用保留を保持して続けます。

'''
progress.write_text(head+marker+'\n\n---\n'+old.split(marker+'\n\n---\n',1)[1])
print(json.dumps({'updated_at':iso,'decisions':{x.name:j.get(x.name)['record']['decision']['status'] for x in [d,i,parent]}},ensure_ascii=False))
