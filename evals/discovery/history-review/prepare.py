from pathlib import Path
import json,sqlite3,hashlib,subprocess,sys,datetime
from collections import deque

ROOT=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker')
OUT=Path('/tmp/sv-history-eval')
PYTHON='/tmp/sv-system-venv/bin/python'
NOW=datetime.datetime.now(datetime.timezone.utc).isoformat()

def save(path,value):
    with path.open('x') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

expected={
 'fixed_at':NOW,
 'purpose':'公開入口で固定された履歴と実施結果から、意味のある改訂と未解決の言い換えを区別できるか。入力担当が人工的に構成した開発用検査。',
 'access':'このファイル、prepare.py、protocol.md、採点用検算は別評価担当へ渡さない。review用packetだけを渡す。',
 'provenance':'既知の仮想role-chain SQLを再使用。探索AIが自然に発見した履歴ではない。実カード・未知入力・方式優位・実戦強度の検査ではない。',
 'a':{
  'procedure_allowed':['supported','conditional'], 'value_allowed':['test','develop'],
  'expected_progress':'あり。10PPの未完成手順へ、1PPを支出して2PP軽減する働きを組み込み、9PPで13点へ到達する。',
  'required_findings':['historyの初版では4+2+4=10PPで9PPに1不足していたと読む。','現改訂は同じ全9枚の中の軽減の使い方を具体化し、1+4+0+4=9PPである。','場への生成→手札への移動→元コスト12条件の順を確認する。','追加された説明量や引用数でなく、資源不足が解けたことを進歩として認める。','testは固定状態で13点に届く比較上の判断と限定し、実戦/Tier/新規性を認定しない。developなら残る確認を具体的に述べ、解決済みのPP不足を未解決に戻さない。'],
  'hard_errors':['drop、進歩なし、10PP不足が現改訂にも残る、と判断する。','軽減2だけを数えて支出1を忘れる。','生成した番兵を場から移さず手札条件へ算入する。','通常4点と条件13点を加算する。']},
 'b':{
  'procedure_expected':'refuted','value_expected':'drop',
  'expected_progress':'なし。元コスト9の生成物と2/3の初期フォロワーしかなく、元コスト12の条件は開かない。全9枚と固定初期手札を検査済みの後で、同じ13点条件の問いを言い換えた。',
  'required_findings':['historyの初版が抱えた元コスト条件の問いと現改訂の問いを比較し、札・能力の読み替え・資源・条件の解決が増えていないと認める。','追加sourceの実施範囲が全9枚・各1枚の初期8枚・本文の生成物だけであることを読み、未実施の問いと混同しない。','番兵は元コスト9、初期フォロワーは2と3で、軽減は元コストを上げずスペルだけを対象にする。','直接打点は各1枚の対句4点と採寸4点。攻撃可能化・再使用・追加取得がなく最大8点で13点枝は閉じない。','dropは固定初期状態の13点を繰り返す枝だけに限定し、カード全体や8点の他用途は否定しない。'],
  'hard_errors':['未解決と言い換えたことを具体的前進とする。','固定範囲を変える新しい証拠なしに同じ13点枝をdevelop/testへ残す。','初期手札に同名2枚目や元コスト12のカードを追加する。','カード全体・他用途を一律に弱いとして棄却する。']},
 'common':['過去のreview評価値は入力へ渡していない。historyは先祖proposalと当時の検索・資料識別値だけ。','sourceは観測の証拠であり、過去の採否結論ではない。sourceの結論を引用するだけでなくカード原文と照合する。','noveltyはunconfirmed、外部検索をしたと書かない。実戦/Tierは今回の評価外。'],
 'grading':'各caseの許容値と必要な因果判断を満たし、hard_errorsがない場合のみ、そのcaseをPASSとする。表現の逐語一致は求めない。全体PASSは両件PASS。失敗後に条件を変えず、未実行は未実行。'
}
save(OUT/'expected.json',expected)
(OUT/'protocol.md').write_text('''# 履歴を使う開発用検査\n\n入力担当 /root/continuation_eval_audit が、既知の仮想9枚を使って意図的に2改訂を構成する。自然に発見した探索経緯ではなく、historyと実施結果を公開入口が運べること、および別評価が進歩の有無を読み分けることの検査である。既存role-chain初回の成績には加算しない。\n\nexpected.jsonは入力作成・検算前に固定する。実施した独立検算は固定8枚の手札と本文からの全生成先に限定する有限状態列挙、および本文上の上限の説明。既存expectedの採否ラベルは証拠に使わない。検算が事前条件と食い違った場合は作成を中止し、条件を緩和しない。\n\n各caseはSQLから別DB作成→公開start→由来attach→packet→初版submit→実施結果attach→packet→改訂submit→review packet固定→read history/sources確認までを行う。過去reviewは作らず、評価ラベルを流さない。fresh評価者へ渡すのは a/b の最終review packetだけ。実装、protocol、expected、入力生成コード、旧レビューを読ませない。sourceの検算結果はカードから再確認できる証拠として渡す。\n\n最終採点は初回判断の主観一致ではなく、aで解消されたPP不足とbで変わらない元コスト条件を、祖先・現在・検査結果から理由付きで区別したかを判定する。\n''')

INITIAL=(94070001,94070002,94070003,94070004,94070006,94070007,94070008,94070009)

def enumerate_states(cards):
    # This is an evaluation-only interpreter for these nine printed effects, not a general game simulator.
    initial=(9,tuple((cid,cards[cid]['cost']) for cid in INITIAL),tuple(),0)
    paths={initial:[]};pending=deque([initial]);best=initial; edges=0
    while pending:
        state=pending.popleft();pp,hand,board,damage=state
        if damage>best[3]:best=state
        for i,(cid,cost) in enumerate(hand):
            if cost>pp:continue
            rest=hand[:i]+hand[i+1:];after=pp-cost
            choices=[]
            if cid==94070001:
                high=any(cards[h]['type_category']=='フォロワー' and cards[h]['cost']>=12 for h,_ in rest)
                choices=[(rest,board,damage+(13 if high else 4),None)]
            elif cid==94070002:
                choices=[(rest,tuple(sorted(board+(94070005,))) if len(board)<5 else board,damage,None)]
            elif cid==94070003:
                for j,target in enumerate(board):
                    if len(rest)<9:
                        choices.append((tuple(sorted(rest+((target,cards[target]['cost']),))),board[:j]+board[j+1:],damage,target))
                if not board:choices=[(rest,board,damage,None)]
            elif cid==94070004:
                for j,(target,tcost) in enumerate(rest):
                    if cards[target]['type_category']=='スペル':
                        modified=rest[:j]+((target,max(0,tcost-2)),)+rest[j+1:]
                        choices.append((modified,board,damage,target))
                if not choices:choices=[(rest,board,damage,None)]
            elif cid==94070006:choices=[(rest,board,damage+4,None)]
            elif cid==94070007:choices=[(rest,board,damage,None)]
            elif cid in (94070005,94070008,94070009):
                if len(board)<5:choices=[(rest,tuple(sorted(board+(cid,))),damage,None)]
            else:raise AssertionError(cid)
            for h,b,d,target in choices:
                nextstate=(after,tuple(sorted(h)),b,d);edges+=1
                if nextstate not in paths:
                    action={'card_id':cid,'target':target,'paid':cost,'pp_after':after,'hand_after':[x[0] for x in sorted(h)],'board_after':list(b),'damage_total':d}
                    paths[nextstate]=paths[state]+[action];pending.append(nextstate)
    return {'states':len(paths),'transitions':edges,'max_damage':best[3],'witness':paths[best],
       'bounds':'カード全文を9件確認。各1枚の初期手札8枚と本文の生成先だけ。山札、追加取得、進化権、超進化権、追加PP、相手の協力は使わない。フォロワーの当日リーダー攻撃を可能にする本文はない。回復はダメージへ足さない。'}

case_cards={};enum={};manifest={'fixed_at':NOW,'fixture_origin':{},'expected_sha256':sha(OUT/'expected.json')}
for name in ('a','b'):
    folder=OUT/name;folder.mkdir()
    source=ROOT/f'evals/discovery/role-chain/input-{name}.sql'
    db=folder/'cards.db';conn=sqlite3.connect(db);conn.row_factory=sqlite3.Row;conn.executescript(source.read_text())
    rows=[dict(r) for r in conn.execute('SELECT card_id,name,cost,type_category,skill_text FROM card ORDER BY card_id')];conn.close()
    cards={r['card_id']:r for r in rows};case_cards[name]=cards
    result=enumerate_states(cards);enum[name]=result
    save(folder/'independent-enumeration.json',result)
    save(folder/'card-text-audit.json',rows)
    manifest['fixture_origin'][name]={'source':str(source),'sql_sha256':sha(source),'database_sha256':sha(db)}
assert enum['a']['max_damage']==13,enum['a']
assert enum['b']['max_damage']==8,enum['b']
save(OUT/'input-manifest.json',manifest)
print(json.dumps({'expected_fixed_before_enumeration':True,'a':{k:v for k,v in enum['a'].items() if k not in ('witness','bounds')},'b':{k:v for k,v in enum['b'].items() if k not in ('witness','bounds')}},ensure_ascii=False))
