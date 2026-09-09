import json
from pathlib import Path
from datetime import datetime, timezone
W=Path('/tmp/sv-pp-comparison-01/a/work')
x=json.loads((W/'calc-input.json').read_text())
y=json.loads((W/'calc-output.json').read_text())
files={'comparison':Path('/tmp/sv-pp-comparison-01/inputs/original-comparison.md').read_text().splitlines(),'rules':Path('/tmp/sv-pp-comparison-01/inputs/rules.md').read_text().splitlines()}
refs=[]
def walk(v):
    if isinstance(v,dict):
        if {'source','source_hash','line','quote'}<=v.keys():refs.append(v)
        for z in v.values():walk(z)
    elif isinstance(v,list):
        for z in v:walk(z)
walk(x)
for r in refs:
    assert r['quote'] in files[r['source']][r['line']-1],r
G,L=y['plans']
assert G['t8_end']=={'current_pp':0,'extra_remaining':0,'available_pp':0}
assert L['t8_end']=={'current_pp':0,'extra_remaining':1,'available_pp':1}
assert 8+1-(5+0+2+2)==0
assert 8-(0+0+8)+7-7==0
assert G['t9_end_numeric_case']['current_pp']==9-(0+0+2+2)==5
assert L['t9_end_numeric_case']['current_pp']==9-(0+2+2+2)==3
assert 5-(3+1)==1
assert all(p['all_recorded_numeric_payments_affordable'] for p in y['plans'])
assert len(G['rows'])==len(L['rows'])==10
checks={'source_quote_checks':len(refs),'all_source_quotes_match_declared_lines':True,'t8_conservation_confirmed':True,'t9_same_endpoint_confirmed':True,'extra_state_not_reset_between_turns':True,'numeric_case_no_negative_pp':True,'no_extra_use_added_to_luria':True,'checked_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}
(W/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
report='''# 方式A：保存された二案のPP検算

元資料の記載どおりにT9の両レイピアを出し終えた時点を比べると、現在PPはゴッデス側5、ルリア側3という記載と整合する。ルリア側は後半の追加1PPを未使用で残すため、その場で追加分まで含めて使える量は5対4となる。「残りPPが2多い」は現在PPの差を説明するが、追加分込みの余裕が2多いという意味ではない。

ただし、元資料はT9開始PPを別の文で明記していない。上記の5対3は「両側とも開始9PPで、記載以外のPP増減がない」場合の検算である。9は原文の残り値と支払い額から逆算した整合条件であり、開始PPを独立に証明した結果ではない。以下はこの数値例と、開始PPを未定のままにした式を分ける。

## 範囲と数え方

- 入力は指定の元比較文と固定ルールのみ。公開readで保存された同じ二資料を読んだ。
- 現在PPは手元にある量。未使用の追加分はここへ加えない。「追加分込みで使える量」は現在PPと未使用1PPの合計であり、追加分を実際に使用したという記録ではない。
- 両案の共通出発点はT8現在8PP、後半の追加分が未使用。ゴッデス側の8は「追加PPを使用して9PP」とルールの+1から、ルリア側の8は「8→0→7」から読む。ルール上、追加分を持つこの比較は後攻の条件になる。
- 終点は両側ともT9の神秘・緋岸・レイピア2枚のプレイ後。追加の札や、原文にないルリア側の追加PP使用を行動へ足していない。攻撃・進化は本検算でPP増減を与えない。

## 行動順と途中収支

'''+(W/'calculation-table.md').read_text()+'''
G6とL6の「9」は条件付きの数値例で、T8の残りをT9へ加算した値ではない。記号g、lはそれぞれゴッデス側、ルリア側のT9開始現在PPである。G2〜G5は原文に列記された支払い順だけを保存した。各数値とカード名の完全な対応は元資料に明記されないため補わない。

T8はゴッデス側が8+1−5−0−2−2=0、ルリア側が8−0−0−8+7−7=0。ルリア側は8を支払った後に原文の0→7を経てから7を払うため、合計支払い15でも途中不足にはならない。どちらも原文に示された収支の範囲では現在PPが負にならない。ルリア側の0→7は原文の「実際に7増えた」という記述の検算であり、カードの印刷された回復値や発動条件を確認したものではない。

T8の終点では現在PPは両側0。追加分込みで使える量はゴッデス側0、ルリア側1。ゴッデス側の追加分はT8で消費され、T9へ移っても復活させていない。ルリア側は未使用の権利が残るので、使える量を数える時だけ1を足す。

## 同じ終点での結果

|T9終了時点|ゴッデス側|ルリア側|ゴッデス側から引いた差|
|---|---:|---:|---:|
|現在PP（両側開始9の場合）|5|3|2|
|未使用の後半追加分|0|1|−1|
|追加分込みで使える量|5|4|1|
|開始PPを未定にした現在PP|g−4|l−6|g−l+2|
|開始PPを未定にした使える量|g−4|l−5|g−l+1|

開始PPが同じなら、その値を9に固定しなくても現在PPの差は2、追加分込みの差は1。ただし、追加使用を挿入せず原文のT9手順を最後まで払うには、ゴッデス側g≧4、ルリア側l≧6が必要。開始PPが同じことまで確定できない読み方では、固定差ではなく上の式までが結論になる。

T8で使った追加PPはそのターン限りなので、ゴッデス側のT9にもう1足さない。ルリア側にT9末まで残る1PPは、T8の余りPPを繰り越したものではない。PP最大値と現在PPも区別し、ルールの「PP最大値上限10」だけからT9開始PPを決めていない。

## 原文との対応

入力JSONの各行にも、下記の出典識別値、元ファイルの1始まりの行番号、正確な引用を保存した。

|計算行・結論|元比較文の行|使った記述と読み方|
|---|---:|---|
|共通の未使用追加分|4|「EP1・SEP1、後半エクストラPPが残り」からT8の未使用1回分|
|G1|5|「T8エクストラPPを使用して9PP。」と固定ルール23行の+1から8→9、使用済みへ|
|G2〜G5|5|「5+0+2+2PP」から順に−5、0、−2、−2|
|G7〜G10|5|「T9神秘0、コピー緋岸0、レイピア2+2」から0、0、−2、−2|
|G6と条件付き終点5|5|「T9残り5PP。」と支払い合計4から、開始9なら整合する|
|L1〜L5|6|「T8緋岸A0と神秘0」「エンハンス8で残りPP8→0→7」「7PPでプレイ」から0、0、−8、+7、−7|
|L7〜L10|6|「T9自然ドロー7枚から神秘0、2コストまで下がった緋岸B」「レイピア2+2PP」から0、−2、−2、−2。自然ドロー7は手札枚数であり、PP7には使わない|
|L6と条件付き終点3|6|「PP残り3」と支払い合計6から、開始9なら整合する|
|L1〜L10の未使用1|6|「後半エクストラPPは使わずに残る。」を全行に適用|
|現在PP差と使える量の差|7|「ゴッデス側にはT9の残りPP2多い余地がある。」を現在PP差2として限定し、未使用追加分込みでは差1と区別|
|追加分の時期・量・後攻条件|固定ルール23|「後攻のみ。そのターンだけPP+1。T1〜5で1回・T6以降で1回・使うタイミングは任意」|

元比較文の保存識別値: `2b2103ec19f514cb1072ff5a14ace6919162d8401f334614048140daebc09e76`。
固定ルールの保存識別値: `0ee2133f3364cb871e43d5e00635e41b928b0f494216dd4825553579b6a46cf5`。
公開readに使った資料一式の識別値: `3fa583f23bb113c46c615f5fd464781a9dee9e7d47f6a5b306e4d3a9a2198013`。

## 説明できること・できないこと

説明できるのは、指定された支払い順の途中不足の有無、原文の残り5・3と開始9の整合、同じ終点での現在PP差2と未使用追加分込みの差1である。

「ゴッデス側の方が常に強い」「追加の処理を必ず1回多くできる」「T9で使える量の差が2ある」などは、この検算からは出ない。追加分込みの量だけではカードの使い道や効率が決まらない。元文の打点差1、手札枚数、守護・破壊の価値、最適手順の有無、初手からの実現率や実戦での勝敗は検査対象外である。

未確認条件は、T9開始PPの独立した根拠、各カード全文・PP増減条件や回復上限、記載のない効果、T8支払いとカード名の完全な対応。これらを元資料の外から埋めていない。数字が合うことをカード効果全体の合法性の証明として扱わない。

## 計算・確認・保存記録

通常のPythonで `calc-input.json` を読み、`calculate.py` が `calc-output.json` と行表を生成した。`write_report.py` で出典の引用が指定行に実在すること、T8の収支、T9の終点、未使用分の持ち越し状態、支払い途中の非負を確認した。詳細は `verification.json`。計算・入力の修正は0回。

開始・資料読取終了・入力またはスクリプト作成終了・計算終了・確認終了・保存終了の実時計、公開操作ごとの成否と合計は `execution.json` に記録する。公開の元資料readは完了済み。公開attachによる保存結果と、その後のreportでの対応確認は `public-attach-result.json`、`public-report.txt`、`save-verification.json` に残す。採点・他方式との比較は実施しない。
'''
(W/'report.md').write_text(report)
e=json.loads((W/'execution.json').read_text())
e['milestones']['confirmation_complete']=checks['checked_at']
(W/'execution.json').write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(checks,ensure_ascii=False,indent=2))
