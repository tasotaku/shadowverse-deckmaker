'use strict';
// AI_NOTE: 盤面の結果と合法手は常に対戦エンジンから受け取り、画面にはルールを複製しない。
const $ = id => document.getElementById(id);
const STORE = 'svdeck-battle-v1';
let bootstrap, view, selectedCase = null, busy = false, running = false, selectedSource = null;

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
async function guarded(work) {
  // AI_NOTE: 連打による手順の競合を防ぎ、自動対戦も同じ操作境界を通す。
  if (busy) return;
  busy = true;
  controls();
  try { await work(); }
  catch (error) { stopAuto(); notify(error.message, true); }
  finally { busy = false; controls(); }
}
function persist() {
  // AI_NOTE: 再読込時にケースと再生位置を復元でき、保存失敗も利用者へ知らせる。
  try { localStorage.setItem(STORE, JSON.stringify({record:view.record, cursor:view.cursor, selectedCase, reveal:$('reveal').checked})); }
  catch { notify('ブラウザの保存領域が不足しています。「記録を保存」でファイルへ保存してください。', true); }
}
function accept(result) {
  // AI_NOTE: 更新後の盤面・操作一覧・履歴をまとめて切り替える。
  view = result;
  selectedSource = null;
  render();
  persist();
}
function entityName(id) {
  // AI_NOTE: 同名カードを区別するため内部番号を短く添える。
  if (typeof id !== 'string') return String(id ?? '');
  if (id.startsWith('leader:')) return `プレイヤー${Number(id.split(':')[1]) + 1}`;
  for (const player of view.state.players) {
    for (const zone of ['hand','board','deck']) {
      const card = (player[zone] || []).find(card => card.id === id);
      if (card) return `${card.name || card.card_id} [${id}]`;
    }
  }
  return id;
}
function actionLabel(action) {
  // AI_NOTE: 操作対象を日本語で明示し、複数の合法手を区別できるようにする。
  const names = {play:'使用', attack:'攻撃', evolve:'進化', super_evolve:'超進化', end_turn:'ターン終了', extra_pp:'追加PPを使う'};
  return `${names[action.type] || action.type}${action.card || action.source ? '：' + entityName(action.card || action.source) : ''}${action.target ? ' → ' + entityName(action.target) : ''}`;
}
function controls() {
  // AI_NOTE: 状態がない時・自動操作中・履歴端で無効な操作を押せないようにする。
  for (const id of ['start','test','apply-case','test-json','act','case-step','first','back','next','last','scenario','action','scrub']) $(id).disabled = busy || running;
  $('auto').disabled = busy && !running;
  if (!view) return;
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
  const definition = view.record.cards?.[card.card_id] || bootstrap.cards[card.card_id] || {};
  const title = node('div', 'card-name');
  title.append(node('span','cost',card.cost ?? definition.cost ?? '?'), document.createTextNode(card.name || definition.name || card.card_id));
  element.append(title);
  const text = definition.text || '';
  if (text) element.append(node('div','card-text',text));
  if ((card.keywords || []).length) element.append(node('div','keywords',card.keywords.join(' · ')));
  if (card.evolved) element.append(node('div','keywords',card.evolved === 2 ? '超進化' : '進化'));
  if (definition.kind === 'follower' || card.max_health > 0) {
    const stats = node('div','card-stats');
    stats.append(node('span','attack',`⚔ ${card.attack ?? 0}`),node('span','card-health',`♥ ${card.health ?? 0}/${card.max_health ?? 0}`));
    element.append(stats);
  }
  if (card.countdown != null) element.append(node('div','keywords',`残り ${card.countdown}`));
  element.title = `${card.name || card.card_id} [${card.id}]\n${text}\n${available ? 'クリックで操作を絞る' : '現在このカードから行える操作はありません'}`;
  element.onclick = () => {
    if (busy || running) return;
    selectedSource = selectedSource === card.id ? null : card.id;
    renderBoard(); renderActions();
  };
  return element;
}
function renderBoard() {
  // AI_NOTE: 相手側を上、自分側を下へ固定し、手番が変わっても盤面の位置を飛ばさない。
  $('board').replaceChildren();
  for (const index of [1,0]) {
    const player = view.state.players[index];
    const section = node('div','player' + (index === view.state.active_player ? ' active' : ''));
    const head = node('div','player-head');
    head.append(node('span','player-name',`PLAYER ${index + 1}${index === view.state.active_player ? ' · 操作中' : ''}`),node('span','health',`♥ ${player.health}`),node('span','stat',`PP ${player.pp}/${player.max_pp}`),node('span','stat',`進化 ${player.ep} / 超進化 ${player.sep}`),node('span','stat',`山札 ${player.deck.length} · 墓場 ${player.graveyard}`));
    section.append(head);
    for (const zone of index === 1 ? ['hand','board'] : ['board','hand']) {
      section.append(node('div','zone-label',zone === 'hand' ? `手札 ${player.hand.length}枚` : `盤面 ${player.board.length}/5`));
      const cards = node('div','cards');
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
    if (typeof event === 'string') box.append(node('strong','',`${index + 1}. ${event}`));
    else {
      box.append(node('strong','',`${index + 1}. ${event.reason || event.message || event.type || '状態の変化'}`));
      box.append(node('pre','',JSON.stringify(event,null,2)));
    }
    $('events').append(box);
  });
  const previous = view.cursor > 1 ? frames[view.cursor - 2]?.state : view.record.initial;
  showDifferences($('changes'),view.cursor && previous ? differences(previous,state) : []);
  controls();
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
  selectedCase = testCase;
  $('case-json').value = JSON.stringify(testCase || {name:'自由対戦',initial:bootstrap.state,actions:[],expected:{}},null,2);
  $('case-description').textContent = testCase?.description || '';
  $('verdict').textContent = '未実行'; $('test-result').replaceChildren();
  accept(result);
  notify(testCase ? `${testCase.name || testCase.id || '検査ケース'} の開始状態を読み込みました。` : '自由対戦を開始しました。');
}
async function step(action) {
  // AI_NOTE: 過去からの操作はエンジンが履歴を分岐し、元記録は事前に保存できる。
  const branched = view.cursor < view.record.actions.length;
  const result = await api('step',{record:view.record,cursor:view.cursor,action});
  accept(result);
  notify(branched ? 'この位置から別の手順へ分岐しました。' : '操作を実行しました。');
}
async function seek(cursor) {
  // AI_NOTE: 保存された見た目だけを切り替えず、同じ操作をエンジンで再生する。
  stopAuto();
  accept(await api('replay',{record:view.record,cursor}));
  notify(`${cursor}手目を表示しています。`);
}
async function testCase(testCase) {
  // AI_NOTE: 自動試験の記録もそのまま盤面へ開き、失敗局面を調べられるようにする。
  const result = await api('test',{case:testCase});
  if (result.record) {
    selectedCase = testCase;
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
  running = false; $('auto').textContent = '自動対戦';
}
async function autoLoop() {
  // AI_NOTE: 待ち時間は描画用のみで、選択にはLLMや非公開のルール推定を使わない。
  if (running) { stopAuto(); controls(); return; }
  running = true; selectedSource = null; $('auto').textContent = '自動対戦を停止'; controls();
  let count = 0;
  while (running && view.state.winner == null && view.legal_actions.length && count < 500) {
    await guarded(async () => {
      const action = view.legal_actions[Math.floor(Math.random() * view.legal_actions.length)];
      await step(action);
    });
    count++;
    await new Promise(resolve => setTimeout(resolve,Number($('speed').value)));
  }
  const limited = count >= 500;
  stopAuto(); controls();
  if (limited) notify('500操作で一時停止しました。続けるには自動対戦を押してください。');
}
async function init() {
  // AI_NOTE: 保存記録を検証して復元し、壊れた記録は消さず理由を表示する。
  bootstrap = await api('bootstrap');
  $('scenario').append(new Option('5ダメージを試す · 自由操作',''));
  bootstrap.cases.forEach((testCase,index) => $('scenario').append(new Option(testCase.name || testCase.id || `ケース ${index + 1}`,String(index))));
  let saved = null;
  try { saved = localStorage.getItem(STORE); } catch { notify('ブラウザの自動保存を利用できません。ファイル保存は利用できます。',true); }
  if (saved) {
    try {
      const data = JSON.parse(saved);
      selectedCase = data.selectedCase;
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
$('start').onclick = () => guarded(() => startCase($('scenario').value === '' ? null : bootstrap.cases[Number($('scenario').value)]));
$('scenario').onchange = () => { $('case-description').textContent = $('scenario').value === '' ? '' : bootstrap.cases[Number($('scenario').value)]?.description || ''; };
$('act').onclick = () => guarded(() => { const action = view.legal_actions[Number($('action').value)]; if (!action) throw new Error('可能な操作を選んでください。'); return step(action); });
$('case-step').onclick = () => guarded(() => step(selectedCase.actions[view.cursor]));
$('test').onclick = () => guarded(() => testCase(selectedCase));
$('test-json').onclick = () => guarded(() => testCase(JSON.parse($('case-json').value)));
$('apply-case').onclick = () => guarded(() => startCase(JSON.parse($('case-json').value)));
$('first').onclick = () => guarded(() => seek(0));
$('back').onclick = () => guarded(() => seek(view.cursor - 1));
$('next').onclick = () => guarded(() => seek(view.cursor + 1));
$('last').onclick = () => guarded(() => seek(view.record.actions.length));
$('scrub').onchange = () => guarded(() => seek(Number($('scrub').value)));
$('auto').onclick = autoLoop;
$('reveal').onchange = () => { if (view) { renderBoard(); persist(); } };
$('save').onclick = () => {
  const link = node('a'); const url = URL.createObjectURL(new Blob([JSON.stringify(view.record,null,2)],{type:'application/json'}));
  link.href = url; link.download = `battle-${Date.now()}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
  notify('開始状態・操作列・処理履歴を保存しました。');
};
$('import').onchange = () => guarded(async () => {
  stopAuto(); const file = $('import').files[0]; if (!file) return;
  if (file.size > 4 * 1024 * 1024) throw new Error('記録は4MB以内にしてください。');
  const record = JSON.parse(await file.text());
  const result = await api('replay',{record}); selectedCase = null;
  $('case-json').value = JSON.stringify({name:'読み込んだ記録',initial:record.initial,actions:record.actions,expected:{}},null,2);
  $('verdict').textContent = '期待結果なし'; $('test-result').replaceChildren();
  accept(result); $('import').value = ''; notify('記録を開き、操作を再実行しました。');
});
guarded(init);
