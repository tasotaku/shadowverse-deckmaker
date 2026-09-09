import json
from pathlib import Path
from datetime import datetime, timezone
W=Path('/tmp/sv-pp-comparison-01/a/work')
comparison_hash='2b2103ec19f514cb1072ff5a14ace6919162d8401f334614048140daebc09e76'
rules_hash='0ee2133f3364cb871e43d5e00635e41b928b0f494216dd4825553579b6a46cf5'
def ref(line,quote,source='comparison'):
    return {'source':source,'source_hash':comparison_hash if source=='comparison' else rules_hash,'line':line,'quote':quote}
def action(row,label,delta,reference,extra=None):
    x={'row':row,'label':label,'delta':delta,'references':[reference]}
    if extra is not None:x['extra_after']=extra
    return x
extra=ref(23,'- **エクストラPP**: 後攻のみ。そのターンだけPP+1。T1〜5で1回・T6以降で1回・使うタイミングは任意（確定）','rules')
g5=ref(5,'ゴッデス側: T8エクストラPPを使用して9PP。')
g8=ref(5,'5+0+2+2PP、EPをゴッデスへ使い、顔10点。')
g9=ref(5,'T9神秘0、コピー緋岸0、レイピア2+2で顔10点、残るSEPをレイピアへ使えば13点。')
l8=ref(6,'元のルリア側の一例: T8緋岸A0と神秘0を使い、ルリアのエンハンス8で残りPP8→0→7、唯一の7コスト以上であるセタス＆メイシアを引き、7PPでプレイ。')
l9=ref(6,'T9自然ドロー7枚から神秘0、2コストまで下がった緋岸Bで破壊＋1ドロー、レイピア2+2PPを出す。')
input_data={
 'method':'A / 通常のPythonによる数値と記号の計算。公開pp操作は不使用',
 'source_hashes':{'comparison':comparison_hash,'rules':rules_hash},
 'definitions':{'current_pp':'現在のPP。未使用の追加分は含まない。','available_pp':'現在PPに、この時点で未使用の後半追加分1PPを足した量。追加分を実行済みとは扱わない。','extra_remaining':'未使用1、使用済み0。各自分ターンで復活させない。'},
 'common_start':{'turn':8,'current_pp':8,'extra_remaining':1,'side':'second','references':[g5,l8,ref(4,'EP1・SEP1、後半エクストラPPが残り、T6鹿王のクレストからT8終了時にも神秘を得られる。'),extra],'derivation':'ルリア側8→0→7の先頭に8が明記。ゴッデス側は追加1で9から使用直前8を逆算。後攻は追加PPを使用できるルールから帰結。'},
 'plans':[
 {'name':'ゴッデス','t8':[
 action('G1','後半の追加PPを使う',1,g5,0),
 action('G2','原文5+0+2+2の第1支払い',-5,g8),
 action('G3','原文5+0+2+2の第2支払い',0,g8),
 action('G4','原文5+0+2+2の第3支払い',-2,g8),
 action('G5','原文5+0+2+2の第4支払い',-2,g8)],
 't9_start':{'symbol':'g','numeric_case':9,'status':'原文の残り5と支払い合計4が整合する開始値。開始9そのものの独立した記載はない。','references':[ref(5,'T9残り5PP。'),g9]},
 't9':[
 action('G7','神秘0',0,g9),action('G8','コピー緋岸0',0,g9),action('G9','レイピア1枚目2',-2,g9),action('G10','レイピア2枚目2',-2,g9)],
 'extra_at_t9':0},
 {'name':'ルリア','t8':[
 action('L1','緋岸A0',0,l8),action('L2','神秘0',0,l8),action('L3','ルリアのエンハンス8',-8,l8),
 action('L4','原文0→7の実際の増加として扱う',7,l8),action('L5','セタス＆メイシア7',-7,l8)],
 't9_start':{'symbol':'l','numeric_case':9,'status':'原文の残り3と支払い合計6が整合する開始値。開始9そのものの独立した記載はない。','references':[ref(6,'EPを一方へ使えば5+7=12点、PP残り3、手札7→6→6→4。'),l9]},
 't9':[
 action('L7','神秘0',0,l9),action('L8','緋岸B2',-2,l9),action('L9','レイピア1枚目2',-2,l9),action('L10','レイピア2枚目2',-2,l9)],
 'extra_at_t9':1,'extra_reference':ref(6,'後半エクストラPPは使わずに残る。')}
 ],
 'endpoint':'T9の記載された神秘・緋岸・レイピア2枚のプレイを済ませた直後。これ以降の追加PP使用や追加カードプレイは計算行に加えない。',
 'limitations':['全カードの本文・追加効果・PP回復の上限や条件は未確認。原文0→7を実際の増加7として検算する。','T9開始PPを一般的なターン数から自動設定しない。記号での結果と原文残り値に対応する9の条件付き結果を併記する。','手札・盤面・進化権・打点・カード評価・初手からの到達率・実戦頻度は検算対象外。','T8の5+0+2+2の各支払いに対するカード名の完全な対応は元資料に明記されないため、第1〜4支払いとして保持する。','記載されたPP以外に増減がないという原文の列を検算し、カード効果全体による完全な合法性は証明しない。']
}
(W/'calc-input.json').write_text(json.dumps(input_data,ensure_ascii=False,indent=2)+'\n')
x=json.loads((W/'execution.json').read_text())
x['milestones']['input_or_script_complete']=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
(W/'execution.json').write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
