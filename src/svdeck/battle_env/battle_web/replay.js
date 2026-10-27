'use strict';
const BattleReplay = {
  turns(record) {
    // AI_NOTE: 手数からターンを推測せず、各操作後の手番と本人のターン数から移動先を作る。
    const points = [];
    let previous = null;
    [record.initial, ...(record.frames || []).map(frame => frame.state)].forEach((state, cursor) => {
      if (!state || cursor > record.actions.length) return;
      const player = state.active_player, turn = state.players[player].turn;
      const key = `${player}:${turn}`;
      if (key !== previous) points.push({cursor, player, turn,
        label: `${player === 0 ? '先攻' : '後攻'} ${turn}ターン目 · ${cursor}手目`});
      previous = key;
    });
    return points;
  },
  currentTurn(points, cursor) {
    // AI_NOTE: ターン途中を表示している場合も、そのターンの開始位置を選択状態にする。
    return points.filter(point => point.cursor <= cursor).at(-1)?.cursor ?? 0;
  }
};
