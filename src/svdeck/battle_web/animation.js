'use strict';
// 表示済みの確定結果に演出を重ねる。ルールや盤面の値は変更しない。
class BattleAnimation {
  constructor(board, caption) {
    this.board = board;
    this.caption = caption;
    this.animations = new Set();
    this.ghosts = new Set();
    this.generation = 0;
    this.active = false;
    this.enabled = true;
    this.motion = matchMedia('(prefers-reduced-motion: reduce)');
    this.motion.addEventListener('change', () => { if (this.motion.matches) this.cancel(); });
  }
  capture() {
    return new Map([...this.board.querySelectorAll('[data-entity]')].map(element => [element.dataset.entity, {
      element: element.cloneNode(true), rect: element.getBoundingClientRect()
    }]));
  }
  cancel() {
    this.generation++;
    for (const animation of this.animations) animation.cancel();
    this.animations.clear();
    for (const ghost of this.ghosts) ghost.remove();
    this.ghosts.clear();
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
    const locate = id => {
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
        } else if (kind === 'summon' || kind === 'hand' || kind === 'play') {
          await this.animate(target || source,[{opacity:.25,transform:'translateY(14px) scale(.88)'},{opacity:1,transform:'translateY(0) scale(1)'}],300);
          if (kind === 'play' && departed.has(event.source)) { source?.remove(); this.ghosts.delete(source); }
        } else {
          // 新しい種類の処理も説明と強調で表示できる。
          await this.animate(target || source || this.caption,[{filter:'brightness(1.8)'},{filter:'brightness(1)'}],kind === 'effect' ? 130 : 240);
        }
      }
    } finally { if (generation === this.generation) this.cancel(); }
  }
}
