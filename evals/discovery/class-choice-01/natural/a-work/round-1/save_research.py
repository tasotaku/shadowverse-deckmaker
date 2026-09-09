import json
from pathlib import Path
base=Path('/tmp/sv-class-choice-01')
out=base/'a-work/round-1'
idx=json.load(open(base/'a-session-index.json'))
end='2026-09-09T02:52:47Z'
web=[
 {'title':'第8弾 連打ドラゴン（ドラーク＆アルザード）', 'url':'https://note.com/took3116/n/n463e32944a0a','query':'スターライトゴッデス ドラーク アルザード／バベロンシティ ヴォーラライ ドラゴン','checked_at':'2026-09-09T02:51:00Z','time_precision':'minute; within research window','access':'本文を開いて確認','finding':'要約：著者のノーランプ構築では冒険者のギルドでドラークを引き、突進を付ける。アイカで再取得し、キミカ・ヴォーラライ・バベロンシティも使う。軽くなったドラークをスターライトゴッデスで増やす案にも言及し、復帰札が手札右端へ入る難しさを記す。従って同じ着想を新発見とはできない。','limitations':['2026年7月15日の個人記事。現環境の強さや全40枚の合法性を検査していない。','著者の対戦結果は本人の報告であり、本試行の測定結果ではない。']},
 {'title':'エルタロを信じろ：フェイスドラゴンの動画への公開投稿','url':'https://www.youtube.com/watch?v=gTTrExMQy04','query':'エルタロ ドラゴン デッキ','checked_at':'2026-09-09T02:51:00Z','time_precision':'minute; within research window','access':'Yahooリアルタイム検索の投稿抜粋。YouTube本体のopenはthrottled','finding':'要約：8月29日の投稿抜粋にエルタロ入りでドローできるフェイスドラゴンの動画表題が見つかった。エルタロで手札を補うという用途の先例候補。','limitations':['動画内容・全40枚・投稿日時の一次ページ確認は未完了。既知構築と細部まで同一と断言しない。','二次検索抜粋のため、独自性を肯定する根拠には用いない。']},
 {'title':'魔手ウィッチ：数字で見る偉丈夫じゃんけん','url':'https://note.com/shostp/n/n2250cfa9d2fa','query':'軍配の偉丈夫 ウィッチ','checked_at':'2026-09-09T02:51:00Z','time_precision':'minute; within research window','access':'公開本文を開いて確認','finding':'要約：軍配の偉丈夫とオリヴィエ・バハムートを魔手ウィッチへ入れる型を既存構築として説明。支払コストが下がる札と元の高いコストを組み合わせる発想は既出。','limitations':['8月2日の記事。能力調整前の説明を現在のサーチ能力として流用しない。','記事の大会普及率や勝率は本試行で独立確認していない。']},
 {'title':'偉丈夫、バハムート、オリヴィエ採用型魔手ウィッチ解説','url':'https://note.com/a0923_sv/n/n8b2b7605ab26','query':'軍配の偉丈夫 ウィッチ','checked_at':'2026-09-09T02:51:00Z','time_precision':'minute; within research window','access':'検索抜粋と公開ページを開いて確認。有料部分未読','finding':'要約：三枚のニュートラルを採用する魔手ウィッチについて、作成者自身の説明が存在する。同名カードが偶然並ぶだけでなく用途の既知例として扱った。','limitations':['有料部分は読んでいない。現在の最適構築を確定する資料ではない。']},
 {'title':'天晶ウィッチ、土抜きで','url':'https://note.com/orfe1006/n/n957e35b00a5f','query':'大遊戯世界 ウィッチ／大遊戯世界 スペル','checked_at':'2026-09-09T02:51:43Z','time_precision':'exact tool clock after search','access':'検索結果に含まれた本文抜粋','finding':'要約：土関連を抜き、大遊戯世界と低コストの補充札へ置き換える構築を作者が説明している。低コスト補充を土台に配分を変える用法も先例がある。','limitations':['3月26日の記事で、旧能力・ローテ落ちを含み得る。現行案として転用していない。','全40枚の画像を読んでいない。']},
 {'title':'デイリーミッションを爆速でクリアするデッキ TYPE2','url':'https://hanhans.hatenablog.com/entry/2026/06/26/211254','query':'大遊戯世界 スペル','checked_at':'2026-09-09T02:51:43Z','time_precision':'exact tool clock after search','access':'検索結果の本文抜粋','finding':'要約：大遊戯世界自身が元1コストなので、1コスト札の連打でカウントを進め、知恵の輝き・ストームブラストなどと組む説明がある。この相互作用そのものは既知。','limitations':['対CPUのミッション用デッキ。対人の強さの根拠にはできない。']},
 {'title':'疾走テンポバフエルフデッキを作ってみた','url':'https://hon-to-game.com/sissou-bahu-eruh/','query':'エルタロ エルフ デッキ','checked_at':'2026-09-09T02:51:43Z','time_precision':'exact tool clock after search','access':'検索結果の本文抜粋','finding':'要約：エルタロを潜伏して強化を受ける打点兼補充札として説明し、低コストを増やした際の手札維持に使う例がある。','limitations':['本文全体・全40枚は未検査。記事中の旧環境札を現行採用札にしていない。']},
 {'title':'ダストデイズ入りのバフエルフについて考える回','url':'https://shiroiseijin.hatenablog.jp/entry/2026/07/09/170707','query':'エルタロ エルフ デッキ','checked_at':'2026-09-09T02:51:43Z','time_precision':'exact tool clock after search','access':'検索結果の本文抜粋','finding':'要約：エルタロの潜伏と強化を併用し、ドローと打点を兼ねる説明がある。枚数と手札超過への懸念も記載される。','limitations':['個人の構築考察。勝率の検証ではなく、現在の全40枚を確定していない。']},
 {'title':'ゲテンオウドラゴン既出検索','url':'https://game8.jp/shadowverse-beyond/753730','query':'ゲテンオウ ルインジェノサイダー','checked_at':end,'time_precision':'recorded at research end; searched earlier in window','access':'検索結果の抜粋','finding':'要約：ゲテンオウドラゴンの既存構築が見つかった。デッキ圧縮からの軽減狙いという同じ仕組みを新規扱いしない。','limitations':['サタン等の現在採用不可な札を含む歴史例。現行で成立する組み方は未確定。']}
]
# Remove falsely precise intermediate reading timestamps: the exact end clock is known, original open time not retained.
for w in web:
 if w['time_precision'].startswith('minute'):
  w['checked_at']=end
  w['time_precision']='recorded at research end; read within 02:36:33–02:52:47 UTC'
searches=[
 'スターライトゴッデス ラスティ ロイヤル','バベロンメイヤー エルタロ クキシロ','ゲテンオウ ルインジェノサイダー','バベロンシティ ヴォーラライ ドラゴン',
 'スターライトゴッデス 天斧の深淵','スターライトゴッデス マナリアの魔弾','スターライトゴッデス フラッシュブリンク','エルタロ ドラゴン デッキ',
 'スターライトゴッデス ヴォーラライ','スターライトゴッデス 天刀の深淵','スターライトゴッデス ディスカード','スターライトゴッデス サガツマツ',
 '軍配の偉丈夫 ウィッチ','スターライトゴッデス ドラーク アルザード','ヘイレムハニィ 死神払い','ゼラエル 輪廻転衝',
 '大遊戯世界 ウィッチ','大遊戯世界 スペル','ゴッズレポーター セレス','エルタロ エルフ デッキ']
checks=[
 {'seed':'エルタロ→安い攻撃札を増やすドラゴン','state':'用途の先例候補あり、未提出','observed':'保存40枚のフェイスドラゴンを参照。T4にエルタロ3PPと寸裂1PPを組めば前ターンの顔攻撃をつなぐ余地はある。T3を補充だけへ使うと翌ターンの攻撃条件を失い得る。Webに同用途の動画投稿があった。','missing':'全40枚の具体的な交換差、動画内容との違い、設置後の盤面負担と勝ち筋の実測。'},
 {'seed':'ゴッデス→軽減済ドラークを増やすドラゴン','state':'同じ着想の公開記述あり、未提出','observed':'本人の公開記事に2PPのドラークをコピーする案と手札順の難しさが記されている。天刀の深淵3枚を捨て札兼ダメージに使う案も考えたが、コピー対象を左へ寄せる条件と準備負担は解決していない。','missing':'手札順と6枚以上の残量を再現可能に作る手順、既存の反復より勝ちへ近づく配分、超進化の競合。'},
 {'seed':'ゴッデス→疾走を得たラスティを増やすロイヤル','state':'未完成・非推薦','observed':'ラスティの超進化は山札の同名を引き疾走を付ける。ゴッデスの注記では付与状態もコピー。原型1枚＋疾走2枚を得た後、その2枚をコピーすれば疾走4枚にできる。単純なT6ラスティ→T7ゴッデスは、7PPではゴッデス5＋ラスティ3を同時に払えず、攻めが一旦止まる。','missing':'他にコピーする1枚と捨てる3枚の実際の入手、初期手札で同名を引いた場合、準備2ターンと2回の進化系資源に見合う強さ。検索に直接一致する構築が見つからないことだけでは独自性を肯定しない。'},
 {'seed':'ゲテンオウ→ルインジェノサイダー後の補充または軽減','state':'既知の仕組み・現行案の勝ち方未確定','observed':'保存注記が軽減先のランダム性と強い受け先を要求。Webで既存の圧縮・ゲテンオウ構築が見つかった。旧サタン等をローテへ持ち込まない。','missing':'偶数の山札を作る負担に見合う現在合法な勝ち方。'},
 {'seed':'軍配の偉丈夫→元コストを保った軽減札のウィッチ','state':'既知用途','observed':'魔手ウィッチへの具体的採用解説が複数ある。','missing':'同じ採用と異なる役割変更。'},
 {'seed':'大遊戯世界→1コストスペルによる高速補充','state':'相互作用と配分変更とも先例あり','observed':'自身の元1コストを利用したカウント促進、軽い札を多めに使うウィッチへの採用説明が公開されている。','missing':'今回の新しい構築として何が変わるか。'},
 {'seed':'エルタロ→潜伏しながら強化されるエルフ','state':'既知用途','observed':'潜伏への強化、低コスト寄せの補充、後の顔打点という役割が公開構築で説明される。','missing':'既存用途を越える配分上の具体的利益。'},
 {'seed':'その他の短い候補照合','state':'精査未完了','observed':'ヘイレムハニィと死神払い、ゼラエルと輪廻転衝、アズヴォルトで守護再展開、ゴッズレポーターやベルエンジェルによる補充等をカード本文・注記へ照合した。成立する全手順や40枚比較を作ったという意味ではない。','missing':'既出確認、相手の動きを含む速度、準備負担を満たす構築。'}]
coverage={
 'sources':'指定の初期packet7件のみ。実装、採点基準、他担当結果、過去自然試行結果を読んでいない。',
 'eligible_cards':{'unique_card_id_count':516,'neutral_card_count':46,'fields_read_across_all':['card_id','name','class_name','cost','atk','life','type','skill_text','ref_effect_text','note'],'saved_union':'eligible-cards.json','limitation':'全カードのraw・全進化文・タグ・requirementsを全件精査したという主張ではない。表示が切れたニュートラル中段とナイトメア中段は再表示して読んだ。'},
 'related_cards':'金貨、深淵、操り人形、アーティファクトなど候補の関連札を選択的に確認。関連カード99件全体の読了とは扱わない。',
 'rules':'公開packetのrules本文117行と、指定docs/design.mdのフォーマット・評価・マッチング・既出判定の節を参照。',
 'known_decks':'同じ保存参考構築33件の名称、クラス、ニュートラル採用を横断照合。ドラゴンのフェイス寄せ2リストを40枚の参照として読んだ。全33件の全手順・合法性・優劣の監査はしていない。',
 'practical_tests':'対戦、勝率測定、手札シミュレーション、完成40枚の交換比較は実施していない。'
}
research={'author':'/root/class_choice_a1','objective':'ニュートラルの別用途からクラス・配分・勝ち方まで発展させる','research_ended_at_utc':end,'decision':'not_submitted','selected_proposal_session':None,'evidence_storage_session':idx['a-4']['session'],'reason':'具体的な着想はあったが、既知との差と採用負担に見合う勝ち方を同時に説明できる案まで到達しなかった。候補不存在や方式失敗の証明ではない。','read_scope':coverage,'candidate_checks':checks,'representative_search_scope':searches,'search_scope_limitation':'日本語のカード名・組み合わせ検索中心。全検索結果の網羅、全言語・動画内容の網羅はしていない。検索0件を未発見の証明にしていない。','web_checks':web,'sessions':idx}
(out/'research.json').write_text(json.dumps(research,ensure_ascii=False,indent=2)+'\n')
md=['# 初回調査：正式案は未提出','','ニュートラルの別用途からクラスと配分を検討したが、既知の使い方との差と、準備負担に見合う勝ち方を同時に説明できる案まで進まなかった。候補が存在しないという結論ではない。','','開始：2026-09-09 02:36:33 UTC。新規調査終了：2026-09-09 02:52:47 UTC。','','## 読んだ範囲','',coverage['eligible_cards']['limitation'],coverage['related_cards'],coverage['known_decks'],coverage['practical_tests'],'','## 検討結果','']
for c in checks:
 md += [f"### {c['seed']}", '',c['state']+'。'+c['observed'],'','残る確認：'+c['missing'],'']
md += ['## Webの確認','',research['search_scope_limitation'],'']
for w in web:
 md += [f"- [{w['title']}]({w['url']})：{w['finding']} 確認範囲：{w['access']}。"]
(out/'research.md').write_text('\n'.join(md)+'\n')
sources=[]
for w in web:
 sources.append({'title':w['title'],'kind':'Web確認の要約','location':w['url'],'observed_at':w['checked_at'],'content':w['finding']+'\n検索・照合：'+w['query']+'\n確認範囲：'+w['access'],'limitations':w['limitations']+['確認時刻の精度：'+w['time_precision']]})
sources.append({'title':'初回7クラス横断調査の範囲と未提出判断','kind':'利用担当の調査記録','location':str(out/'research.json'),'observed_at':end,'content':'要約：採用可能な516枚の基本情報・効果本文・関連効果・注記を横断した。33参考構築のニュートラル採用を照合し、ドラゴンのフェイス寄せ2構築を参照。コピー、継続補充、コスト軽減、再展開を検討したが、既知との差と採用負担に見合う勝ち方を同時に説明できる案に到達せず、正式案は提出しない。\n未完成のロイヤル案：疾走付きラスティ2枚をゴッデスで複製して4枚へ増やす。ただしT6ラスティ、T7ゴッデスという順では7PPで5+3を払えず、攻めを一旦止める。3枚の捨て札・コピーの第三対象・手札順・進化系資源・他の勝ち筋が未解決。','limitations':[coverage['eligible_cards']['limitation'],coverage['related_cards'],coverage['known_decks'],coverage['practical_tests'],'同じ着想のWeb上の不存在も、候補全体の不存在も証明していない。']})
(out/'sources-to-attach.json').write_text(json.dumps({'sources':sources},ensure_ascii=False,indent=2)+'\n')
execution=json.load(open(out/'execution.json'))
execution.update({'research_ended_at_utc':end,'status':'saving','sessions_read':idx,'read_scope':coverage,'formal_submission':{'status':'not_submitted','revision':None,'session':None,'reason':research['reason']},'evidence_storage_session':idx['a-4']['session'],'remaining_unknowns':[c['missing'] for c in checks],'record_files':['research.json','research.md','sources-to-attach.json','eligible-cards.json']})
(out/'execution.json').write_text(json.dumps(execution,ensure_ascii=False,indent=2)+'\n')
