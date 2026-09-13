from pathlib import Path
from datetime import datetime,timezone
import copy,gzip,hashlib,json,sqlite3
from svdeck import discovery
ROOT=Path('/Users/miyauchitsubasa/Desktop/github/shadowverse-deckmaker')
OUT=Path('/tmp/sv-reviewer-utility-01-input')
E=ROOT/'evals/discovery/reviewer-utility-01'
OUT.mkdir(exist_ok=False)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def unpack(p): return json.loads(gzip.decompress(p.read_bytes()))['data']
a=unpack(ROOT/'evals/discovery/mazel-role-review/a/review-packet.json.gz')
b=unpack(ROOT/'evals/discovery/known-candidate-review/packet-knife.json.gz')
audit=json.loads(Path('/tmp/reviewer-utility-knife-input.json').read_text())
patches=[]
mazel=next(c for c in a['context']['cards'] if c['card_id']==10304110)
old=mazel['note']
fragment='2026-09-06ユーザー実戦評価: マゼルテンポエルフは作りたかった独自デッキの例。最終的にtier3〜4程度でも初見での対処の難しさでtier1〜2と戦えたという本人評価。'
assert fragment in old
new=old.replace(fragment,'')
patches.append(dict(card_id=10304110,old=old,new=new,reason='本人の成功実績と好評価を伏せ、構想・置換条件・未提示の範囲は保持'))
for replacement in audit['replacements']:
    if replacement['path'].startswith('/data/context/cards/') and replacement['path'].endswith('/note'):
        idx=int(replacement['path'].split('/')[4]);c=b['context']['cards'][idx]
        assert c['note']==replacement['old']
        patches.append(dict(card_id=c['card_id'],old=replacement['old'],new=replacement['new'],reason=replacement['reason']))
source=ROOT/'data/cards.db';before=sha(source)
assert before=='11aef89fae292ce671781ce31da124d695b15b28f64d7813c6e0c9ad720e1414'
ro=sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True);db=sqlite3.connect(OUT/'masked.db');ro.backup(db);ro.close()
for patch in patches:
    assert db.execute('SELECT note FROM card_note WHERE card_id=?',(patch['card_id'],)).fetchone()[0]==patch['old']
    db.execute('UPDATE card_note SET note=? WHERE card_id=?',(patch['new'],patch['card_id']))
db.commit();db.close()
docs=OUT/'docs';docs.mkdir();principles=a['context']['principles']
principles=principles.replace('マゼルテンポエルフのようにtier3〜4程度でも','tier3〜4程度でも')
# The first paragraph now follows the already adopted scope; no new novelty threshold.
old_scope='**「誰も作れなかった、そこそこ強いデッキ」の種を提案する**支援システム。\n\n- **想定外の定義**: 基準は運営の意図ではなく「**人類が既に発見・共有したデッキ集合**」。\n  その外にあること。運営想定外でも既に流行していればアウト。逆に、運営想定内の\n  弱いアーキタイプが1枚差しで化けるケースは本命。'
new_scope='**「独自で、そこそこ戦えるデッキ」の種を提案する**支援システム。\n\n- **想定外の定義**: 基準は運営の意図ではなく、その使い方が「一般に広まっているか」。\n  誰かが試しただけで候補から除外しない。運営想定外でも既に流行していれば独自性の根拠にはならない。\n  逆に、運営想定内の弱いアーキタイプが1枚差しで化けるケースも本命。'
assert old_scope in principles;principles=principles.replace(old_scope,new_scope)
(docs/'design.md').write_text(principles);(docs/'rules.md').write_text(a['context']['rules']);assert a['context']['rules']==b['context']['rules']
objective='保存カード本文と提出されたデッキの種を使い、指定状態の手順の成立、通常の構築との比較から組んで試す価値があるか、独自性をそれぞれ理由付きで評価する。新しい札や別案を作らず、提出された構想・配分を評価する。資源処理用の指定例を、最速・平均・毎試合の到達と混同しない。40枚化と実戦検証は人が行う。未提示の内容は補わず未確認として示す。保存時点の材料だけを扱い、最新公式照合や実戦を今回行ったとはしない。'
string_patches=[(p['old'],p['new']) for p in patches]
for replacement in audit['replacements']:
    if replacement['path'].startswith('/data/proposal/'):
        string_patches.append((replacement['old'],replacement['new']))
string_patches.extend([
 ('2026-09-06のユーザーのTier経験は過去のデッキに関する注記。このseedの実戦強度や新規性へ転用しない。','この構想の実戦強度や新規性は未確認。'),
 ('両側のnoteは保存版を保持している。','注記内の当該案に対する過去の採否・実績は今回の出題用コピーから分離し、カードの働き・条件と未確認は保持している。'),
])
def transform(v):
    if isinstance(v,str):
        for old,new in string_patches:v=v.replace(old,new)
        return v
    if isinstance(v,list):return [transform(x) for x in v]
    if isinstance(v,dict):return {k:transform(x) for k,x in v.items()}
    return v
results={}
for name,data in [('a',a),('b',b)]:
    folder=OUT/name;session=folder/'session';folder.mkdir()
    ctx=data['context'];started=discovery.start(session,OUT/'masked.db',ctx['class_name'],ctx['format'],objective,docs)
    save(folder/'start-result.json',started)
    sources=transform(copy.deepcopy(data.get('sources',[])))
    for source_item in sources:source_item.pop('source_hash',None)
    if name=='b':
        supplement=json.loads(Path('/tmp/reviewer-utility-knife-supplement.json').read_text())
        sources.extend(supplement['sources'])
    if sources:save(folder/'attach-result.json',discovery.attach(session,{'sources':sources}))
    packet=discovery.packet(session,None,'develop')
    proposal=transform(copy.deepcopy(data['proposal']))
    for key in ('revision','context_hash'):proposal.pop(key,None)
    proposal.update(packet_hash=packet['sha256'],parent_revision=0,author='fixture-input')
    save(folder/'proposal.json',proposal);save(folder/'submit-result.json',discovery.submit(session,proposal))
    review=discovery.packet(session,1,'review');save(folder/'review-packet.json',review)
    assert review['data']['instruction']==discovery.REVIEW==data['instruction']
    assert review['data']['previous_reviews']==[] and review['data']['history']==[]
    orig={c['card_id']:c for c in ctx['cards']};changes=[]
    for card in review['data']['context']['cards']:
        expected=transform(orig[card['card_id']]);assert card==expected,card['card_id']
        if card!=orig[card['card_id']]:changes.append(card['card_id'])
    assert all(deck.get('source') is None for deck in review['data']['context']['known_decks'])
    assert [{k:v for k,v in deck.items() if k!='source'} for deck in review['data']['context']['known_decks']]==ctx['known_decks']
    results[name]=dict(session=str(session),packet_hash=review['sha256'],revision=1,cards=len(orig),changed_note_card_ids=changes,sources=len(sources),format=ctx['format'],review_instruction_unchanged=True,card_facts_preserved=True,known_decks_preserved=True)
assert sha(ROOT/'data/cards.db')==before
save(E/'input-manifest.json',dict(created_at=datetime.now(timezone.utc).isoformat(),cases=results,main_db_sha256=before,main_db_unchanged=True,note_patches=patches,string_patches=string_patches,principles_basis='旧mazel-role-reviewの共通原則。正例の実名を伏せ、冒頭の独自性説明のみ2026-09-10確定の運用へ整合。現在docsに追加された検査結果・正解は使わない。',principles_sha256=sha(docs/'design.md'),rules_sha256=sha(docs/'rules.md'),review_instruction_sha256=hashlib.sha256(discovery.REVIEW.encode()).hexdigest(),preparation_read_error='旧knife入力にsourcesがあると仮定した読み取り確認がKeyErrorになった。旧形式はsourcesなしと確認し、getで空リストとして扱った。元入力は不変。'))
print(json.dumps(results,ensure_ascii=False))
