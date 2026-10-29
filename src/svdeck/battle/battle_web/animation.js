'use strict';
// 表示済みの確定結果に演出を重ねる。ルールや盤面の値は変更しない。
class BattleAnimation {
  constructor(board, caption) {
    this.board = board;
    this.caption = caption;
    this.animations = new Set();
    this.ghosts = new Set();
    // AI_NOTE: 旧配置の演出中に隠す確定盤面を保持し、中断時にも表示を復元する。
    this.hidden = new Map();
    this.generation = 0;
    this.active = false;
    this.enabled = true;
    this.motion = matchMedia('(prefers-reduced-motion: reduce)');
    this.motion.addEventListener('change', () => { if (this.motion.matches) this.cancel(); });
    window.addEventListener('resize', () => this.cancel());
  }
  capture() {
    // AI_NOTE: 盤面からの退場と手札への移動を区別するため、元の列も記録する。
    return new Map([...this.board.querySelectorAll('[data-entity]')].map(element => [element.dataset.entity, {
      element: element.cloneNode(true), rect: element.getBoundingClientRect(),
      zone: element.closest('.board-cards') ? [...this.board.querySelectorAll('.board-cards')].indexOf(element.closest('.board-cards')) : -1
    }]));
  }
  cancel() {
    // AI_NOTE: 巻き戻し・演出OFF・画面サイズ変更では確定盤面に即時復帰する。
    this.generation++;
    for (const animation of this.animations) animation.cancel();
    this.animations.clear();
    for (const ghost of this.ghosts) ghost.remove();
    this.ghosts.clear();
    for (const [element, visibility] of this.hidden) element.style.visibility = visibility;
    this.hidden.clear();
    this.active = false;
    this.caption.hidden = true;
    this.board.removeAttribute('aria-busy');
  }
  async animate(element, frames, duration = 360) {
    if (!element) return;
    const animation = element.animate(frames, {duration, easing:'ease-out', fill:'none'});
    this.animations.add(animation);
    try { await animation.finished; } catch (error) { if (error.name !== 'AbortError') throw error; }
    finally { this.animations.delete(animation); }
  }
  ghost(snapshot) {
    if (!snapshot) return null;
    const element = snapshot.element;
    element.removeAttribute('data-entity');
    element.removeAttribute('id');
    element.classList.add('battle-ghost');
    element.setAttribute('aria-hidden','true');
    Object.assign(element.style, {left:snapshot.rect.left + 'px', top:snapshot.rect.top + 'px', width:snapshot.rect.width + 'px', height:snapshot.rect.height + 'px'});
    document.body.append(element);
    this.ghosts.add(element);
    return element;
  }
  async number(element, text, healing = false) {
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const label = document.createElement('span');
    label.className = 'battle-number' + (healing ? ' healing' : '');
    label.textContent = text;
    label.setAttribute('aria-hidden','true');
    Object.assign(label.style,{left:rect.left + rect.width / 2 + 'px',top:rect.top + rect.height / 3 + 'px'});
    document.body.append(label); this.ghosts.add(label);
    await this.animate(label,[{opacity:1,transform:'translate(-50%,0) scale(.8)'},{opacity:1,offset:.3,transform:'translate(-50%,-12px) scale(1.2)'},{opacity:0,transform:'translate(-50%,-45px) scale(1)'}],520);
    label.remove(); this.ghosts.delete(label);
  }
  async play(events, before) {
    this.cancel();
    if (!this.enabled || this.motion.matches || !events.length) return;
    const generation = this.generation;
    this.active = true;
    this.board.setAttribute('aria-busy','true');
    const current = new Map([...this.board.querySelectorAll('[data-entity]')].map(element => [element.dataset.entity,element]));
    const departed = new Map();
    // AI_NOTE: 退場がある列は旧配置の表示を保ち、確定盤面の左詰めを演出終了まで見せない。
    const rows = [...this.board.querySelectorAll('.board-cards')];
    const changedZones = new Set([...before].filter(([id, snapshot]) => snapshot.zone >= 0 && current.get(id)?.closest('.board-cards') !== rows[snapshot.zone]).map(([,snapshot]) => snapshot.zone));
    const staged = new Map();
    for (const zone of changedZones) {
      for (const element of rows[zone]?.querySelectorAll('[data-entity]') || []) {
        this.hidden.set(element,element.style.visibility);
        element.style.visibility = 'hidden';
      }
      for (const [id,snapshot] of before) if (snapshot.zone === zone) staged.set(id,this.ghost(snapshot));
    }
    const locate = id => {
      if (staged.has(id)) return staged.get(id);
      if (this.hidden.has(current.get(id))) return null;
      if (current.has(id)) return current.get(id);
      if (!departed.has(id) && before.has(id)) departed.set(id,this.ghost(before.get(id)));
      return departed.get(id);
    };
    try {
      for (const event of events) {
        if (generation !== this.generation) break;
        const kind = event.kind || event.type;
        this.caption.textContent = event.message || event.reason || '状態が変化しました';
        this.caption.hidden = false;
        const target = locate(event.target), source = locate(event.source);
        if (kind === 'attack' && source && target) {
          const from = source.getBoundingClientRect(), to = target.getBoundingClientRect();
          const x = (to.left + to.width / 2 - from.left - from.width / 2) * .65;
          const y = (to.top + to.height / 2 - from.top - from.height / 2) * .65;
          const moving = this.ghost({element:source.cloneNode(true),rect:from});
          await this.animate(moving,[{transform:'translate(0,0)'},{transform:`translate(${x}px,${y}px)`,offset:.55},{transform:'translate(0,0)'}],430);
          moving.remove(); this.ghosts.delete(moving);
        } else if (kind === 'damage' || kind === 'heal') {
          const amount = kind === 'heal' ? event.after - event.before : event.amount;
          await Promise.all([this.number(target,(kind === 'heal' ? '+' : '−') + amount,kind === 'heal'),this.animate(target,[{boxShadow:`0 0 0 4px ${kind === 'heal' ? '#75dbc0' : '#ff727b'}`,filter:'brightness(1.6)'},{boxShadow:'0 0 0 0 transparent',filter:'brightness(1)'}],480)]);
        } else if (['death','destroy','banish','bounce'].includes(kind)) {
          await this.animate(target,[{opacity:1,transform:'scale(1)'},{opacity:0,transform:kind === 'bounce' ? 'translateY(45px) scale(.7)' : 'scale(.75)'}],380);
          // 退場の後に同じカードが戻る場合でも、確定盤面の要素を削除しない。
          if (departed.get(event.target) === target) { target?.remove(); this.ghosts.delete(target); }
          if (staged.get(event.target) === target && target) {
            target.remove(); this.ghosts.delete(target); staged.set(event.target,null);
          }
        } else if (kind === 'summon' || kind === 'hand' || kind === 'play') {
          await this.animate(target || source,[{opacity:.25,transform:'translateY(14px) scale(.88)'},{opacity:1,transform:'translateY(0) scale(1)'}],300);
          if (kind === 'play' && departed.has(event.source)) { source?.remove(); this.ghosts.delete(source); }
        } else {
          // 新しい種類の処理も説明と強調で表示できる。
          await this.animate(target || source || this.caption,[{filter:'brightness(1.8)'},{filter:'brightness(1)'}],kind === 'effect' ? 130 : 240);
        }
      }
      if (generation !== this.generation) return;
      // AI_NOTE: 退場をすべて消してから残存カードを詰め、最後に新しく出たカードを表示する。
      for (const [id,element] of staged) if (!current.has(id) && element) { element.remove(); this.ghosts.delete(element); }
      await Promise.all([...staged].map(async ([id,element]) => {
        if (!element || !current.has(id)) return;
        const from = element.getBoundingClientRect(), to = current.get(id).getBoundingClientRect();
        element.style.transformOrigin = 'top left';
        await this.animate(element,[{transform:'translate(0,0) scale(1)'},
          {transform:`translate(${to.left - from.left}px,${to.top - from.top}px) scale(${to.width / from.width},${to.height / from.height})`}],220);
      }));
      if (generation !== this.generation) return;
      const entering = [...this.hidden.keys()].filter(element => !before.has(element.dataset.entity));
      for (const [element,visibility] of this.hidden) element.style.visibility = visibility;
      this.hidden.clear();
      for (const element of staged.values()) if (element) { element.remove(); this.ghosts.delete(element); }
      await Promise.all(entering.map(element => this.animate(element,[{opacity:0},{opacity:1}],220)));
    } finally { if (generation === this.generation) this.cancel(); }
  }
}
