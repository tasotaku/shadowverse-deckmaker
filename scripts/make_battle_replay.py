"""公開40枚同士を終局まで動かし、対戦ラボ用の再生例を保存する。"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from svdeck.battle import replay
from svdeck.battle_decks import new_match


def make_record(seed: int, action_seed: int) -> dict[str, Any]:
    # AI_NOTE: 対戦内の乱数と操作選択の乱数を分け、同じ一試合を再生成できる。
    battle = new_match('ramp-dragon', 'last-words-nightmare', seed=seed)
    chooser = random.Random(action_seed)
    for _ in range(2000):
        if battle.state['winner'] is not None:
            break
        actions = battle.legal_actions()
        active = [action for action in actions if action['type'] != 'end_turn']
        battle.step(chooser.choice(active or actions))
    if battle.state['winner'] is None:
        raise ValueError('2000手以内に終局しませんでした')
    record = battle.export()
    record['meta'] = {
        'title': 'ランプドラゴン vs ラストワードナイトメア',
        'players': ['ランプドラゴン', 'ラストワードナイトメア'],
        'decks': ['ramp-dragon', 'last-words-nightmare'],
        'policy': '合法な操作から無作為に選択。ターン終了以外が可能ならそちらを優先。学習済みAIではありません。',
        'seed': seed,
        'action_seed': action_seed,
    }
    if replay(record).frames != battle.frames:
        raise ValueError('保存記録と再計算した状態・処理履歴が一致しません')
    return record


def main() -> None:
    # AI_NOTE: 配布するファイルは終局・再実行一致・読込上限を確認してから書き出す。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=14)
    parser.add_argument('--action-seed', type=int, default=14)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'src/svdeck/data/battle_example_replay.json')
    args = parser.parse_args()
    try:
        record = make_record(args.seed, args.action_seed)
        payload = (json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
        if len(payload) >= 4_000_000:
            raise ValueError('再生記録が4MBを超えています')
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    final = record['frames'][-1]['state']
    winner = final['winner']
    print(json.dumps({'output': str(args.output), 'actions': len(record['actions']),
                      'turns': [player['turn'] for player in final['players']],
                      'winner': '引き分け' if winner == -1 else record['meta']['players'][winner],
                      'bytes': len(payload)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
