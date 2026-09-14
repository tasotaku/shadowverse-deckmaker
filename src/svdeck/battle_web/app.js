'use strict';
// AI_NOTE: 盤面の結果と合法手は常に対戦エンジンから受け取り、画面にはルールを複製しない。
const $ = id => document.getElementById(id);
const STORE = 'svdeck-battle-v1';
const ANIMATION_STORE = 'svdeck-battle-animation';
const animation = new BattleAnimation($('board'),$('animation-caption'));
let operation = 0, autoRun = 0;
let bootstrap, view, selectedCase = null, busy = false, running = false, selectedSource = null, builderDraft = null;

function node(tag, cls, text) {
  // AI_NOTE: カード名・入力内容をHTMLとして解釈せず、保存記録の読み込みも安全に表示する。
  const element = document.createElement(tag);
  if (cls) element.className = cls;
  if (text !== undefined) element.textContent = String(text);
  return element;
}
function notify(message, error = false) {
  // AI_NOTE: 操作失敗を盤面付近へ表示し、直前の有効状態を保つ。
  $('notice').textContent = message;
  $('notice').className = error ? 'error' : '';
  $('settings-notice').textContent = error && $('settings-dialog').open ? message : '';
}
async function api(path, body) {
  // AI_NOTE: JSON応答の失敗を利用者へ伝え、古い成功表示で上書きしない。
  const response = await fetch('/api/' + path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作を完了できませんでした。');
  return result;
}
async function guarded(work, interrupt = false) {
  // AI_NOTE: 連打による手順の競合を防ぎ、自動対戦も同じ操作境界を通す。
  if (busy && !(interrupt && animation.active)) return;
  if (interrupt) animation.cancel();
  const current = ++operation;
  busy = true;
  controls();
  try { await work(); }
  catch (error) { stopAuto(); notify(error.message, true); }
  finally { if (current === operation) { busy = false; controls(); } }
}
function persist() {
  // AI_NOTE: 再読込時にケースと再生位置を復元でき、保存失敗も利用者へ知らせる。
  try { localStorage.setItem(STORE, JSON.stringify({record:view.record, cursor:view.cursor, selectedCase, reveal:$('reveal').checked, policy:$('ai-policy').value})); }
  catch { notify('ブラウザの保存領域が不足しています。「記録を保存」でファイルへ保存してください。', true); }
}
function accept(result) {
  // AI_NOTE: 更新後の盤面・操作一覧・履歴をまとめて切り替える。
  animation.cancel();
  $('settings-dialog').close();
  $('card-dialog').close();
  view = result;
  selectedSource = null;
  render();
  persist();
}
function entityName(id, state = view.state) {
  // AI_NOTE: 同名カードを区別するため内部番号を短く添える。
  if (typeof id !== 'string') return String(id ?? '');
  if (id.startsWith('leader:')) return `プレイヤー${Number(id.split(':')[1]) + 1}`;
  for (const player of state.players) {
    for (const zone of ['hand','board','deck']) {
      const card = (player[zone] || []).find(card => card.id === id);
      if (card) return `${card.name || card.card_id} [${id}]`;
    }
  }
  return id;
}
function actionLabel(action, state = view.state) {
  // AI_NOTE: 操作対象を日本語で明示し、複数の合法手を区別できるようにする。
  const names = {play:'使用', attack:'攻撃', evolve:'進化', super_evolve:'超進化', end_turn:'ターン終了', extra_pp:'追加PPを使う'};
  const forms = {accelerate:'アクセラレート',crystallize:'結晶'};
  const form = forms[action.form] ? ` · ${forms[action.form]}` : '';
  const mode = action.mode == null ? '' : ` · モード${Number(action.mode) + 1}`;
  const choiceNames = {hand:'手札',enemy:'相手',ally:'自分の場',discard:'捨てる手札'};
  const choices = Object.entries(action.choices || {}).map(([key,value]) => {
    const cards = (Array.isArray(value) ? value : [value]).map(id => entityName(id,state)).join(' ＋ ');
    return ` · ${choiceNames[key] || '選択'}：${cards}`;
  }).join('');
  return `${names[action.type] || action.type}${action.card || action.source ? '：' + entityName(action.card || action.source,state) : ''}${form}${mode}${action.target ? ' → ' + entityName(action.target,state) : ''}${choices}`;
}
function controls() {
  // AI_NOTE: 状態がない時・自動操作中・履歴端で無効な操作を押せないようにする。
  for (const id of ['start','test','apply-case','test-json','act','case-step','first','back','next','last','scenario','action','scrub','replay-turn','example-replay','ai-example-replay','ai-step','ai-policy']) $(id).disabled = busy || running;
  $('auto').disabled = busy && !running;
  if (animation.active) for (const id of ['start','first','back','next','last','scenario','scrub','replay-turn','example-replay','ai-example-replay']) $(id).disabled = false;
  for (const element of $('builder').querySelectorAll('button,input,select')) element.disabled = busy || running;
  if (!view) return;
  $('ai-step').disabled ||= view.state.winner != null || !view.legal_actions.length;
  $('act').disabled ||= !view.legal_actions.some(action => !selectedSource || (action.card || action.source) === selectedSource);
  $('case-step').disabled ||= !selectedCase || view.cursor >= (selectedCase.actions || []).length || JSON.stringify(view.record.actions.slice(0,view.cursor)) !== JSON.stringify(selectedCase.actions.slice(0,view.cursor));
  $('first').disabled ||= view.cursor === 0;
  $('back').disabled ||= view.cursor === 0;
  $('next').disabled ||= view.cursor === view.record.actions.length;
  $('last').disabled ||= view.cursor === view.record.actions.length;
  $('test').disabled ||= !selectedCase;
  $('auto').disabled ||= view.state.winner !== null && view.state.winner !== undefined && !running;
  $('save').disabled = !view;
}
function cardNode(card, zone) {
  // AI_NOTE: カードを直接選ぶと、そのカードで可能な操作だけに絞る。
  const available = view.legal_actions.some(action => (action.card || action.source) === card.id);
  const element = node('button', 'card' + (zone === 'hand' ? ' hand' : '') + (available ? ' selectable' : '') + (selectedSource === card.id ? ' chosen' : ''));
  element.type = 'button';
  element.dataset.entity = card.id;
  const definition = view.record.cards?.[card.card_id] || bootstrap.cards[card.card_id] || {};
  element.dataset.kind = definition.kind || '';
  element.classList.toggle('wounded',card.health < card.max_health);
  element.setAttribute('aria-pressed',String(selectedSource === card.id));
  const title = node('div', 'card-name');
  title.append(node('span','cost',card.cost ?? definition.cost ?? '?'), document.createTextNode(card.name || definition.name || card.card_id));
  element.append(title);
  const text = definition.text || '';
  if (text) element.append(node('div','card-text',text));
  const abilities = node('div','ability-row');
  for (const keyword of card.keywords || []) abilities.append(node('span','keywords',keyword));
  if (['crystallize','crystalline'].includes(card.form)) abilities.append(node('span','keywords','結晶'));
  if (card.lost_last_words) abilities.append(node('span','keywords','ラストワード消失'));
  if (card.evolved) abilities.append(node('span','keywords evolution',card.evolved === 2 ? '超進化' : '進化'));
  if (card.countdown != null) abilities.append(node('span','keywords',`残り ${card.countdown}`));
  if (abilities.children.length) element.append(abilities);
  if (definition.kind === 'follower' || card.max_health > 0) {
    const stats = node('div','card-stats');
    stats.append(node('span','attack',`⚔ ${card.attack ?? 0}`),node('span','card-health',`♥ ${card.health ?? 0}/${card.max_health ?? 0}`));
    element.append(stats);
  }
  element.title = `${card.name || card.card_id} [${card.id}]\n${text}\n${available ? 'クリックで操作を絞る' : '現在このカードから行える操作はありません'}`;
  element.onclick = () => {
    if (busy || running) return;
    selectedSource = selectedSource === card.id ? null : card.id;
    renderBoard(); renderActions();
    showCard(card,definition);
  };
  return element;
}
function showCard(card, definition) {
  // AI_NOTE: 盤面では短く表示し、現在の能力とカード本文はクリック・キーボードで全文を読める。
  $('detail-name').textContent = card.name || definition.name || card.card_id;
  $('detail-stats').replaceChildren(node('span','cost-detail',`${card.cost}PP`));
  if (definition.kind === 'follower' || card.max_health > 0) $('detail-stats').append(
    node('span','attack',`⚔ 攻撃 ${card.attack}`),node('span','card-health',`♥ 体力 ${card.health} / ${card.max_health}`));
  for (const ability of [...(card.keywords || []),...(card.evolved ? [card.evolved === 2 ? '超進化' : '進化'] : []),...(card.lost_last_words ? ['ラストワード消失'] : [])]) $('detail-stats').append(node('span','keywords',ability));
  $('detail-text').replaceChildren();
  // AI_NOTE: 公式本文を変更せず、能力見出しだけを色と太字で識別する。
  for (const part of (definition.text || '能力なし').split(/(【[^】]+】)/g)) {
    $('detail-text').append(part.startsWith('【') ? node('strong','ability-title',part) : document.createTextNode(part));
  }
  $('card-dialog').showModal();
}
function renderBoard() {
  // AI_NOTE: 相手側を上、自分側を下へ固定し、手番が変わっても盤面の位置を飛ばさない。
  $('board').replaceChildren();
  for (const index of [1,0]) {
    const player = view.state.players[index];
    const section = node('div','player' + (index === view.state.active_player ? ' active' : ''));
    const head = node('div','player-head');
    head.dataset.entity = `leader:${index}`;
    head.append(node('span','player-name',`${index === 0 ? '先攻' : '後攻'} · P${index + 1}${index === view.state.active_player ? ' ▶ 手番' : ''}`),node('span','health',`♥ ${player.health}`),node('span','stat pp',`PP ${player.pp}/${player.max_pp}`),node('span','stat evolution',`進化 ${player.ep} / 超進化 ${player.sep}`),node('span','stat',`山札 ${player.deck.length} · 墓場 ${player.graveyard}`));
    if (player.damage_shield) head.append(node('span','player-badge','免疫'));
    section.append(head);
    if ((player.crests || []).length) {
      const crests = node('div','crests');
      crests.append(node('span','crest-label','クレスト'));
      for (const crest of player.crests) {
        const badge = node('span','player-badge',crest.name || '名前なし');
        badge.title = [crest.name,...(crest.keywords || [])].filter(Boolean).join(' · ');
        crests.append(badge);
      }
      head.append(crests);
    }
    for (const zone of index === 1 ? ['hand','board'] : ['board','hand']) {
      section.append(node('div',`zone-label ${zone}-label`,zone === 'hand' ? `▤ 手札 · ${player.hand.length}枚` : `▦ 盤面 · ${player.board.length}/5`));
      const cards = node('div',`cards ${zone}-cards`);
      if (zone === 'hand' && !$('reveal').checked && index !== view.state.active_player) cards.append(node('div','empty','相手の手札は非公開'));
      else for (const card of player[zone]) cards.append(cardNode(card,zone));
      if (!player[zone].length) cards.append(node('div','empty',zone === 'board' ? '盤面にカードがありません' : '手札がありません'));
      section.append(cards);
    }
    $('board').append(section);
  }
}
function renderActions() {
  // AI_NOTE: エンジンの合法手をそのまま保持し、表示文言から行動を再構成しない。
  $('action').replaceChildren();
  const actions = view.legal_actions.map((action,index) => ({action,index})).filter(({action}) => !selectedSource || (action.card || action.source) === selectedSource);
  for (const {action,index} of actions) {
    const option = node('option','',actionLabel(action)); option.value = String(index); $('action').append(option);
  }
  if (!actions.length) $('action').append(node('option','',selectedSource ? 'このカードからの操作なし · もう一度クリックで解除' : '可能な操作なし'));
  $('act').disabled = busy || running || !actions.length;
}
const LABELS = {players:'プレイヤー',health:'体力',max_health:'最大体力',pp:'PP',max_pp:'最大PP',ep:'進化回数',sep:'超進化回数',graveyard:'墓場',hand:'手札',board:'盤面',deck:'山札',active_player:'操作するプレイヤー',winner:'勝者',keywords:'能力',cost:'コスト',attack:'攻撃力',attacks:'攻撃回数',evolved:'進化状態',destroyed:'破壊履歴',combo:'プレイ枚数',turn:'ターン',rng:'乱数の状態',next_id:'次のカード番号'};
function prettyPath(path) {
  // AI_NOTE: 内部フィールド名を読める日本語にし、位置情報を残す。
  return String(path).replace(/[A-Za-z_]+/g, part => LABELS[part] || part);
}
function differences(before, after, path = '') {
  // AI_NOTE: 全状態の変化を追跡し、体力以外の資源・履歴の変化も見落とさない。
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  if (before && after && typeof before === 'object' && typeof after === 'object' && Array.isArray(before) === Array.isArray(after)) {
    return [...new Set([...Object.keys(before),...Object.keys(after)])].flatMap(key => differences(before[key],after[key],path ? `${path}.${key}` : key));
  }
  return [{path,expected:before,actual:after}];
}
function showDifferences(target, items, expected = false) {
  // AI_NOTE: 期待と実際、変更前と変更後を同じ並びで表示する。
  target.replaceChildren();
  for (const item of items.slice(0,150)) {
    const row = node('div','change');
    row.append(node('b','',prettyPath(item.path)),node('span','old',`${expected ? '期待' : '前'}: ${JSON.stringify(item.expected) ?? 'なし'}`),document.createTextNode(' → '),node('span','new',`${expected ? '実際' : '後'}: ${JSON.stringify(item.actual) ?? 'なし'}`));
    target.append(row);
  }
  if (!items.length) target.append(node('div','hint',expected ? '期待する終了状態と一致しました。' : '状態の変化はありません。'));
  if (items.length > 150) target.append(node('div','hint',`ほか${items.length - 150}件。全状態は下の確認欄・保存記録で確認できます。`));
}
function render() {
  // AI_NOTE: 再生位置に対応した処理と変更だけを示し、未来の結果と混同させない。
  const state = view.state;
  const winner = state.winner;
  $('turn').textContent = winner == null ? `プレイヤー${state.active_player + 1} のターン · ${state.players[state.active_player].turn}ターン目` : winner === -1 ? '引き分け' : `プレイヤー${winner + 1} の勝利`;
  renderBoard(); renderActions();
  $('cursor').textContent = `${view.cursor} / ${view.record.actions.length} 手`;
  $('scrub').max = view.record.actions.length; $('scrub').value = view.cursor;
  $('state-json').value = JSON.stringify(state,null,2);
  const frames = view.record.frames || [];
  const events = view.cursor ? frames[view.cursor - 1]?.events || view.events || [] : [];
  $('events').replaceChildren();
  if (!events.length) $('events').append(node('div','hint',view.cursor ? 'この操作の処理記録はありません。' : '開始状態です。操作すると効果の処理順がここに表示されます。'));
  events.forEach((event,index) => {
    const box = node('div','event');
    if (typeof event !== 'string') box.dataset.kind = event.type || '';
    if (typeof event === 'string') box.append(node('strong','',`${index + 1}. ${event}`));
    else {
      box.append(node('strong','',`${index + 1}. ${event.reason || event.message || event.type || '状態の変化'}`));
      const detail = node('details'); detail.append(node('summary','','対象・数値の詳細'),node('pre','',JSON.stringify(event,null,2))); box.append(detail);
    }
    $('events').append(box);
  });
  const previous = view.cursor > 1 ? frames[view.cursor - 2]?.state : view.record.initial;
  const turns = BattleReplay.turns(view.record);
  $('replay-turn').replaceChildren(...turns.map(point => new Option(point.label,String(point.cursor))));
  $('replay-turn').value = String(BattleReplay.currentTurn(turns,view.cursor));
  $('replay-action').textContent = view.cursor
    ? `${view.cursor}手目 · ${actionLabel(view.record.actions[view.cursor - 1],previous || state)}`
    : '開始状態 · 「一手進む」で記録された操作を再生します。';
  renderDecision(view.cursor ? frames[view.cursor - 1]?.decision : null,previous || state);
  showDifferences($('changes'),view.cursor && previous ? differences(previous,state) : []);
  controls();
}
const AI_NAMES = {search:'先読みAI',reply:'相手の返しを読む（試作）',trained:'調整版（比較用）',greedy:'一手評価',random:'無作為'};
function renderDecision(decision, state) {
  // AI_NOTE: 判断は表示中の手に保存されたものだけを示し、現在の選択方式と取り違えない。
  const target = $('ai-decision');
  target.replaceChildren();
  $('ai-method').textContent = AI_NAMES[decision?.policy] || '';
  if (!decision) {
    target.append(node('p','hint',view.cursor ? 'この手にはAIの判断記録がありません。' : '「AIが一手実行」で、選んだ手と判断理由を記録します。'));
    return;
  }
  target.append(node('p','ai-reason',decision.reason || '判断理由の記録はありません。'));
  const score = value => Number.isFinite(value) ? value.toFixed(1) : '—';
  target.append(node('p','ai-metrics',`評価 ${score(decision.score)} · 試した手 ${decision.nodes ?? '—'} · 先読み ${decision.depth ?? '—'}手 · ${Number.isFinite(decision.elapsed_ms) ? (decision.elapsed_ms / 1000).toFixed(2) + '秒' : '時間未記録'}`));
  target.append(node('p','hint','評価値は勝率ではありません。相手の実際の手札・山札順は見ていません。' + (decision.response_search?.available ? '公開デッキから手札を仮定しています。' : '')));
  if (decision.uncertain) target.append(node('p','ai-caution','未確定の結果を含むため、先読みの評価には限界があります。'));
  if (decision.candidates?.length) {
    const table = node('table','ai-candidates');
    table.append(node('caption','','比べた候補'));
    const head = node('tr'); head.append(node('th','','操作'),node('th','','評価')); table.append(head);
    for (const candidate of decision.candidates) {
      const row = node('tr');
      row.append(node('td','',actionLabel(candidate.action,state)),node('td','',score(candidate.score)));
      table.append(row);
    }
    target.append(table);
  }
  const response = decision.response_search;
  const worst = response?.candidates?.[response.chosen_candidate]?.worst_reply;
  if (worst?.labels?.length) {
    const detail = node('details'), list = node('ol','ai-plan');
    detail.append(node('summary','','仮定した相手の返し'));
    detail.append(node('p','hint','選んだ手順に対して、試した手札の中で最も厳しかった返しです。実際の相手手札ではありません。'));
    for (const label of worst.labels) list.append(node('li','',label));
    detail.append(list); target.append(detail);
  }
  if (decision.plan?.length > 1) {
    const detail = node('details'), list = node('ol','ai-plan');
    detail.append(node('summary','','先読みした手順（途中で選び直します）'));
    // AI_NOTE: 生成後の仮番号を実山札の同番号と取り違えず、その段階の公開配置で名前を解決する。
    const forecast = {players:state.players.map((player,owner) => ({board:player.board,
      hand:owner === state.active_player ? player.hand : [],deck:[]}))};
    decision.plan.forEach((action,index) => {
      list.append(node('li','',actionLabel(action,forecast)));
      const layout = decision.plan_layouts?.[index];
      if (layout) forecast.players.forEach((player,owner) => {
        for (const zone of ['hand','board']) player[zone] = layout.filter(card => card.owner === owner && card.zone === zone);
      });
    });
    detail.append(list); target.append(detail);
  }
}
function caseInitial(testCase) {
  // AI_NOTE: 入力の開始状態が欠けたまま標準状態へ暗黙に置き換わることを防ぐ。
  const initial = testCase.initial || testCase.state;
  if (!initial) throw new Error('ケースには initial（開始状態）が必要です。');
  return initial;
}
async function startCase(testCase) {
  // AI_NOTE: 新しい開始条件では以前の合否を消し、別ケースの結果を取り違えない。
  stopAuto();
  const result = await api('start',{state:testCase ? caseInitial(testCase) : bootstrap.state,cards:testCase?.cards || bootstrap.cards});
  selectedCase = testCase && Object.hasOwn(testCase,'expected') ? testCase : null;
  $('case-json').value = JSON.stringify(testCase || {name:'自由対戦',initial:bootstrap.state,actions:[],expected:{}},null,2);
  $('case-description').textContent = testCase?.description || '';
  $('verdict').textContent = '未実行'; $('test-result').replaceChildren();
  accept(result);
  notify(testCase ? `${testCase.name || testCase.title || testCase.id || '検査ケース'} の開始状態を読み込みました。` : '自由対戦を開始しました。');
}
async function step(action, policy = null) {
  // AI_NOTE: 手動とAIの結果を同じ演出・履歴経路へ流し、過去からの実行では履歴を分岐する。
  const branched = view.cursor < view.record.actions.length;
  if (policy) notify(`${AI_NAMES[policy]}が手を選んでいます…`);
  const result = await api(policy ? 'ai-step' : 'step',{record:view.record,cursor:view.cursor,...(policy ? {policy} : {action})});
  const before = animation.capture();
  accept(result);
  const presentation = animation.play(result.events || result.record.frames?.[result.cursor - 1]?.events || [],before);
  controls();
  await presentation;
  if (view !== result) return;
  notify(branched ? 'この位置から別の手順へ分岐しました。' : policy ? `${AI_NAMES[policy]}が一手実行しました。右側の「この手のAI判断」で理由を確認できます。` : '操作を実行しました。');
}
async function seek(cursor, animate = false) {
  // AI_NOTE: 保存された見た目だけを切り替えず、同じ操作をエンジンで再生する。
  stopAuto();
  const result = await api('replay',{record:view.record,cursor});
  const before = animate ? animation.capture() : null;
  accept(result);
  if (animate) {
    const presentation = animation.play(result.events || [],before);
    controls();
    await presentation;
    if (view !== result) return;
  }
  notify(`${cursor}手目を表示しています。`);
}
async function openReplay(record) {
  // AI_NOTE: まず終局まで検査して全ターンの状態を揃え、閲覧は開始状態から始める。
  stopAuto();
  const checked = await api('replay',{record});
  const result = await api('replay',{record:checked.record,cursor:0});
  selectedCase = null;
  $('case-json').value = JSON.stringify({name:'読み込んだ記録',initial:record.initial,actions:record.actions,expected:{}},null,2);
  $('verdict').textContent = '期待結果なし'; $('test-result').replaceChildren();
  $('case-description').textContent = ''; $('scenario').value = '';
  accept(result);
  notify(`${record.meta?.title || '対戦記録'} · 全${record.actions.length}手。「一手進む」または「ターンへ移動」で再生できます。`);
}
async function testCase(testCase) {
  // AI_NOTE: 自動試験の記録もそのまま盤面へ開き、失敗局面を調べられるようにする。
  const result = await api('test',{case:testCase});
  if (result.record) {
    selectedCase = testCase && Object.hasOwn(testCase,'expected') ? testCase : null;
    accept(await api('replay',{record:result.record}));
  }
  $('verdict').textContent = result.passed ? 'PASS' : 'FAIL';
  showDifferences($('test-result'),result.differences || [],true);
  if (result.error) $('test-result').prepend(node('p','',`操作結果: ${result.error}`));
  if (!result.passed && !(result.differences || []).length) $('test-result').replaceChildren(node('p','',result.error || '検査に失敗しました。'));
  $('test-panel').open = true;
  notify(result.passed ? '検査合格：期待する結果と一致しました。' : '検査不一致：期待結果との差分を確認してください。',!result.passed);
}
function stopAuto() {
  // AI_NOTE: 停止後に新たな自動手を予約しない。実行中の一手だけは完了する。
  autoRun++;
  running = false; $('auto').textContent = '自動対戦';
}
async function autoLoop() {
  // AI_NOTE: 両者とも選択した方式で一手ずつ判断し、停止後は新しい手を要求しない。
  if (running) { stopAuto(); controls(); return; }
  running = true; selectedSource = null; $('auto').textContent = '自動対戦を停止'; controls();
  const currentRun = ++autoRun;
  let count = 0;
  while (currentRun === autoRun && running && view.state.winner == null && view.legal_actions.length && count < 500) {
    await guarded(() => step(null,$('ai-policy').value));
    count++;
    await new Promise(resolve => setTimeout(resolve,Number($('speed').value)));
  }
  if (currentRun !== autoRun) return;
  const limited = count >= 500;
  stopAuto(); controls();
  if (limited) notify('500操作で一時停止しました。続けるには自動対戦を押してください。');
}
async function init() {
  // AI_NOTE: 保存記録を検証して復元し、壊れた記録は消さず理由を表示する。
  try { $('animate').checked = localStorage.getItem(ANIMATION_STORE) !== 'off'; }
  catch { notify('演出設定の保存を利用できません。',true); }
  animation.enabled = $('animate').checked;
  bootstrap = await api('bootstrap');
  setupBuilder();
  $('scenario').append(new Option('5ダメージを試す · 自由操作',''));
  (bootstrap.presets || []).forEach(preset => $('scenario').append(new Option(preset.title,'preset:' + preset.id)));
  bootstrap.cases.forEach((testCase,index) => $('scenario').append(new Option(testCase.name || testCase.title || testCase.id || `ケース ${index + 1}`,String(index))));
  let saved = null;
  try { saved = localStorage.getItem(STORE); } catch { notify('ブラウザの自動保存を利用できません。ファイル保存は利用できます。',true); }
  if (saved) {
    try {
      const data = JSON.parse(saved);
      selectedCase = data.selectedCase;
      if (Object.hasOwn(AI_NAMES,data.policy)) $('ai-policy').value = data.policy;
      $('reveal').checked = data.reveal !== false;
      const restored = await api('replay',{record:data.record,cursor:data.cursor});
      $('case-json').value = JSON.stringify(selectedCase || {name:'自由対戦',initial:data.record.initial,actions:[],expected:{}},null,2);
      const match = bootstrap.cases.findIndex(item => selectedCase && item.id === selectedCase.id);
      $('scenario').value = match < 0 ? '' : String(match);
      $('case-description').textContent = selectedCase?.description || '';
      accept(restored); notify('前回の対戦と再生位置を復元しました。'); return;
    } catch (error) {
      view = await api('start',{state:bootstrap.state,cards:bootstrap.cards});
      selectedCase = null; render();
      notify(`前回の記録を復元できません：${error.message}。開始条件を選んで開始できます。`,true); return;
    }
  }
  await startCase(null);
}
// AI_NOTE: すべての変更操作を単一の処理待ち境界へ結び付ける。
function chosenScenario() {
  // AI_NOTE: 通常対戦の開始条件と期待値を持つ検査ケースを区別する。
  const value = $('scenario').value;
  return value === '' ? null : value.startsWith('preset:') ? bootstrap.presets.find(item => 'preset:' + item.id === value) : bootstrap.cases[Number(value)];
}
$('start').onclick = () => guarded(() => startCase(chosenScenario()),true);
$('settings-open').onclick = () => { $('settings-notice').textContent = ''; $('settings-dialog').showModal(); };
$('settings-close').onclick = () => $('settings-dialog').close();
$('card-close').onclick = () => $('card-dialog').close();
$('scenario').onchange = () => { $('case-description').textContent = chosenScenario()?.description || ''; };
$('act').onclick = () => guarded(() => { const action = view.legal_actions[Number($('action').value)]; if (!action) throw new Error('可能な操作を選んでください。'); return step(action); });
$('case-step').onclick = () => guarded(() => step(selectedCase.actions[view.cursor]));
$('test').onclick = () => guarded(() => testCase(selectedCase));
$('test-json').onclick = () => guarded(() => testCase(JSON.parse($('case-json').value)));
$('apply-case').onclick = () => guarded(() => startCase(JSON.parse($('case-json').value)));
$('first').onclick = () => guarded(() => seek(0),true);
$('back').onclick = () => guarded(() => seek(view.cursor - 1),true);
$('next').onclick = () => guarded(() => seek(view.cursor + 1,true),true);
$('last').onclick = () => guarded(() => seek(view.record.actions.length),true);
$('scrub').onchange = () => guarded(() => seek(Number($('scrub').value)),true);
$('replay-turn').onchange = () => guarded(() => seek(Number($('replay-turn').value)),true);
$('example-replay').onclick = () => guarded(async () => openReplay(await api('example-replay')),true);
$('ai-example-replay').onclick = () => guarded(async () => openReplay(await api('ai-example-replay')),true);
$('ai-step').onclick = () => guarded(() => step(null,$('ai-policy').value));
$('ai-policy').onchange = () => { if (view) persist(); };
$('auto').onclick = autoLoop;
$('reveal').onchange = () => { animation.cancel(); if (view) { renderBoard(); persist(); } };
$('animate').onchange = () => {
  animation.enabled = $('animate').checked;
  if (!animation.enabled) animation.cancel();
  try { localStorage.setItem(ANIMATION_STORE,animation.enabled ? 'on' : 'off'); } catch { notify('演出設定を保存できませんでした。',true); }
  controls();
};
$('save').onclick = () => {
  const link = node('a'); const url = URL.createObjectURL(new Blob([JSON.stringify(view.record,null,2)],{type:'application/json'}));
  link.href = url; link.download = `battle-${Date.now()}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
  notify('開始状態・操作列・処理履歴を保存しました。');
};
$('import').onchange = () => guarded(async () => {
  stopAuto(); const file = $('import').files[0]; if (!file) return;
  if (file.size > 4 * 1024 * 1024) throw new Error('記録は4MB以内にしてください。');
  const record = JSON.parse(await file.text());
  await openReplay(record); $('import').value = '';
},true);
function builderCatalog() {
  // AI_NOTE: 読み込んだ記録に独自定義がある場合も、その定義を維持して局面を編集する。
  return {...bootstrap.cards,...(view?.record.cards || {})};
}
function setupBuilder() {
  // AI_NOTE: 実カードと検証用を区別し、対応範囲をカード選択時に確認できるようにする。
  const cards = Object.values(builderCatalog());
  const real = cards.filter(card => !card.synthetic).length;
  $('catalog-count').textContent = `実カード ${real}種 / 検証用 ${cards.length - real}種`;
  $('card-options').replaceChildren();
  for (const card of cards) {
    const option = node('option'); option.value = `${card.name} [${card.card_id}]`;
    option.label = `${card.synthetic ? '検証用' : '実カード'} · ${card.cost}PP`;
    $('card-options').append(option);
  }
}
function loadBuilder() {
  // AI_NOTE: 表示中の状態を明示的に複製し、編集途中に対戦本体を書き換えない。
  if (!view) return;
  builderDraft = JSON.parse(JSON.stringify(view.state));
  builderDraft.winner = null;
  $('builder-active').value = String(builderDraft.active_player);
  setupBuilder(); renderBuilder();
  $('builder-status').textContent = '現在の状態を読み込みました。変更後に開始してください。';
}
function renderBuilder() {
  // AI_NOTE: 選択した側の配置と数値を並べ、少数のカードだけ修正できるようにする。
  if (!builderDraft) return;
  const player = builderDraft.players[Number($('builder-player').value)];
  for (const [id,key] of [['health','health'],['pp','pp'],['max-pp','max_pp'],['turn','turn']]) $('builder-' + id).value = player[key];
  $('builder-cards').replaceChildren();
  for (const [zone,label] of [['hand','手札'],['board','盤面'],['deck','山札']]) {
    const row = node('div','builder-zone'); row.append(node('strong','',`${label} ${player[zone].length}枚`));
    player[zone].forEach((card,index) => {
      const definition = builderCatalog()[card.card_id] || {};
      const chip = node('span','builder-chip',`${card.name || definition.name || card.card_id}${card.health ? ` (${card.attack}/${card.health})` : ''}`);
      const remove = node('button','','×'); remove.type = 'button'; remove.title = `${card.name || definition.name}を${label}から取り除く`;
      remove.setAttribute('aria-label',remove.title);
      remove.onclick = () => { player[zone].splice(index,1); renderBuilder(); $('builder-status').textContent = '編集しました。開始ボタンで反映します。'; };
      chip.append(remove); row.append(chip);
    });
    $('builder-cards').append(row);
  }
}
function updateBuilderStats() {
  // AI_NOTE: 数値の入力を検査し、PPと最大PPなどの整合は開始時にエンジンでも確認する。
  if (!builderDraft) loadBuilder();
  const player = builderDraft.players[Number($('builder-player').value)];
  const values = {};
  for (const [id,key] of [['health','health'],['pp','pp'],['max-pp','max_pp'],['turn','turn']]) {
    const input = $('builder-' + id), value = Number(input.value);
    if (input.value === '' || !Number.isInteger(value) || !input.checkValidity()) throw new Error('体力・PP・ターンを指定範囲の整数で入力してください。');
    values[key] = value;
  }
  Object.assign(player,values);
  player.max_health = Math.max(player.max_health,player.health);
  builderDraft.active_player = Number($('builder-active').value);
  $('builder-status').textContent = '数値を編集しました。開始ボタンで反映します。';
}
$('builder').ontoggle = () => { if ($('builder').open && !builderDraft) loadBuilder(); };
$('builder-reset').onclick = loadBuilder;
$('builder-player').onchange = renderBuilder;
$('builder-stats').onclick = () => guarded(async () => { updateBuilderStats(); renderBuilder(); });
$('builder-card').oninput = () => {
  const card = Object.values(builderCatalog()).find(item => `${item.name} [${item.card_id}]` === $('builder-card').value);
  $('card-preview').textContent = card ? `${card.synthetic ? '検証用カード' : '実カード'} · ${card.cost}PP · ${card.name}\n${card.text || '能力なし'}${card.note ? '\n' + card.note : ''}` : '候補からカードを選ぶと全文を確認できます。';
};
$('builder-add').onclick = () => guarded(async () => {
  if (!builderDraft) loadBuilder();
  updateBuilderStats();
  const card = Object.values(builderCatalog()).find(item => `${item.name} [${item.card_id}]` === $('builder-card').value);
  if (!card) throw new Error('追加するカードを候補から選んでください。');
  const zone = $('builder-zone').value;
  if (zone === 'board' && card.kind === 'spell') throw new Error('スペルは盤面へ配置できません。手札か山札を選んでください。');
  const cards = builderDraft.players[Number($('builder-player').value)][zone];
  if (cards.length >= {hand:9,board:5,deck:200}[zone]) throw new Error('配置先の枚数が上限です。先にカードを取り除いてください。');
  cards.push({card_id:card.card_id}); renderBuilder();
  $('builder-status').textContent = `${card.name}を追加しました。開始ボタンで反映します。`;
});
$('builder-clear').onclick = () => guarded(async () => { updateBuilderStats(); builderDraft.players[Number($('builder-player').value)].board = []; renderBuilder(); $('builder-status').textContent = 'この側の盤面を空にしました。'; });
$('builder-apply').onclick = () => guarded(async () => {
  updateBuilderStats();
  const cards = builderCatalog();
  const result = await api('start',{state:builderDraft,cards});
  selectedCase = null;
  $('case-json').value = JSON.stringify({name:'編集した開始状態',initial:result.state,actions:[],expected:{},cards},null,2);
  $('verdict').textContent = '期待結果なし'; $('test-result').replaceChildren();
  accept(result); loadBuilder();
  $('builder-status').textContent = '編集した状態から開始しました。';
  notify('編集した状態から新しい対戦を開始しました。');
});
guarded(init);
