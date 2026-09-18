"""Finite current-turn expectimax with explicit chance outcomes and replayable policy."""
from __future__ import annotations

import argparse
import copy
import json
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from typing import Any

from .battle import Battle, Json, integer, replay
from .battle_rules import definition
from .battle_compact import Compact, eligible
from .combat_benchmark import peak_memory, save_result

KEYWORDS = {'バリア', '必殺', '疾走', '突進', '守護'}
OPS = {'damage', 'split_damage', 'destroy', 'grant', 'buff', 'summon', 'repeat'}
WEIGHTS = {'leader': 1, 'attack': 2, 'health': 1, 'body': 2, 'hand': 3,
           'pp': 1, 'ep': 3, 'sep': 5, 'keyword': 2, 'win': 10000, 'own_board_health': 0}
OBJECTIVES = ('lethal', 'value')


class Chance(Exception):
    def __init__(self, size: int):
        # AI_NOTE: 未観測の抽選を実乱数で決めず、呼出側へ全分岐の列挙を要求する。
        self.size = size


class Limit(Exception):
    """Incomplete search, never a proof that unexplored actions are inferior."""


class ChanceBattle(Battle):
    draws: tuple[int, ...] = ()
    draw_at: int = 0
    sizes: tuple[int, ...] = ()
    deadline: float = float('inf')

    def resolve(self, effects: list[Json], owner: int, source: Json, chosen: Any = None) -> None:
        # AI_NOTE: ランダムを含まない多重repeatも効果単位で中断し、1操作の内部で時間制限を無視させない。
        for effect in effects:
            if perf_counter() >= self.deadline:
                raise Limit('time')
            super().resolve([effect], owner, source, chosen)

    def random_index(self, length: int) -> int:
        # AI_NOTE: 隠れたrngは読まない。確率1の抽選も記録し、再生で消費個数まで照合する。
        if self.draw_at == len(self.draws):
            raise Chance(length)
        choice = integer(self.draws[self.draw_at], 'random choice', 0, length-1)
        self.draw_at += 1
        self.sizes += (length,)
        return choice

    def branch(self, action: Json, draws: tuple[int, ...]) -> ChanceBattle:
        # AI_NOTE: カード定義だけを共有し、状態・処理中キュー・抽選位置は各枝で独立させる。
        child = copy.copy(self)
        child.state = copy.deepcopy(self.state)
        child.events, child.frames, child.actions = [], [], []
        child.pending, child.destroyed_in_action = [], set()
        child.draws, child.draw_at, child.sizes = draws, 0, ()
        child.execute(action)
        if child.draw_at != len(draws):
            raise ValueError('余分な抽選結果があります')
        return child


def validate_scope(battle: Battle) -> None:
    # AI_NOTE: 未対応の能力を黙って剥がさず拒否し、有限な手札使用と通常戦闘のモデルを守る。
    owner = battle.state['active_player']
    pending = []
    for who, player in enumerate(battle.state['players']):
        if player.get('crests') or player.get('damage_shield'):
            raise ValueError('実戦探索はクレスト・リーダー保護に未対応です')
        if any(definition(battle, entity).get('hand_triggers') for entity in player['hand']):
            raise ValueError('実戦探索は両者の手札誘発に未対応です')
        for entity in player['board'] + (player['hand'] if who == owner else []):
            if set(entity['keywords']) - KEYWORDS:
                raise ValueError('実戦探索の対象能力はバリア・必殺・疾走・突進・守護です')
            pending.append(entity['card_id'])
    visited: set[str] = set()
    while pending:
        cid = pending.pop()
        if cid in visited:
            continue
        visited.add(cid)
        card = battle.cards[cid]
        if card['kind'] not in ('follower', 'spell') or set(card.get('keywords', [])) - KEYWORDS:
            raise ValueError(f'実戦探索の対象外カードです: {cid}')
        for phase in ('forms', 'modes', 'triggers', 'hand_triggers', 'on_discard', 'on_evolved',
                      'leave_banish', 'last_words', 'end_turn', 'attack_effects', 'spellboost'):
            if card.get(phase):
                raise ValueError(f'実戦探索の対象外能力です: {cid}/{phase}')
        effects = [(effect, 1) for phase in ('effects', 'fanfare', 'evolve', 'super_evolve', 'enhance_effects')
                   for effect in card.get(phase, [])]
        work = 0
        choices: set[str] = set()
        while effects:
            effect, multiplier = effects.pop()
            work += multiplier
            if str(effect.get('target', '')).startswith('chosen_'):
                choices.add(effect.get('choice', 'target'))
            if work > 100000 or len(choices) > 2:
                raise ValueError('実戦探索はカード当たり効果展開10万・対象選択欄2種以内です')
            if effect['op'] not in OPS or set(effect.get('keywords', [])) - KEYWORDS:
                raise ValueError(f'実戦探索の対象外効果です: {cid}/{effect["op"]}')
            effects.extend((child, multiplier*(effect.get('count', 1) if effect['op'] == 'repeat' else 1))
                           for child in effect.get('effects', []))
            if effect['op'] == 'summon':
                pending.append(effect['card_id'])
                if set(effect.get('modifiers', {}).get('keywords', [])) - KEYWORDS:
                    raise ValueError('召喚時の能力変更が実戦探索の対象外です')


def state_key(state: Json) -> str:
    # AI_NOTE: 抽選seedだけは同一視する。盤面の順番・個体ID・攻撃権・能力は一切並べ替えない。
    return json.dumps({k: v for k, v in state.items() if k != 'rng'}, sort_keys=True, separators=(',', ':'))


def summary(battle: Battle) -> Json:
    # AI_NOTE: 残存能力と行動権を表示し、数値だけが同じ盤面を利用者が混同しないようにする。
    owner = battle.state['active_player']
    own, enemy = (battle.state['players'][i] for i in (owner, 1-owner))
    return {'own_board': copy.deepcopy(own['board']), 'enemy_board': copy.deepcopy(enemy['board']),
            'own_hand': copy.deepcopy(own['hand']), 'own_health': own['health'], 'enemy_health': enemy['health'],
            'pp': own['pp'], 'ep': own['ep'], 'sep': own['sep'], 'win': battle.state['winner'] == owner}


def value(battle: Battle, weights: dict[str, int]) -> tuple[Fraction, Fraction]:
    # AI_NOTE: 勝利確率と説明可能な仮の盤面点を分離し、この点を対戦全体の勝率とは呼ばない。
    owner = battle.state['active_player']
    own, enemy = (battle.state['players'][i] for i in (owner, 1-owner))
    score = weights['leader']*(own['health']-enemy['health'])
    for sign, player in ((1, own), (-1, enemy)):
        for entity in player['board']:
            score += sign*(weights['body']+weights['attack']*entity['attack']+weights['health']*entity['health']
                           +weights['keyword']*len(entity['keywords']))
    score += weights['hand']*len(own['hand']) + sum(weights[k]*own[k] for k in ('pp', 'ep', 'sep'))
    score += weights['own_board_health']*sum(entity['health'] for entity in own['board'])
    won = battle.state['winner'] == owner
    score += weights['win']*int(won)
    return Fraction(int(won)), Fraction(score)


def metrics(pair: tuple[Fraction, Fraction]) -> Json:
    # AI_NOTE: 丸め表示とは別に有理数を保存し、確率や期待値を厳密に再照合できるようにする。
    return {'win_probability': float(pair[0]), 'win_probability_exact': str(pair[0]),
            'expected_value': float(pair[1]), 'expected_value_exact': str(pair[1])}


def analyze(battle: Battle, *, objective: str = 'lethal', weights: dict[str, int] | None = None,
            max_states: int | None = None, max_outcomes: int = 4096, max_depth: int = 64,
            seconds: float = 10.0) -> Json:
    # AI_NOTE: 状態ごとの意思決定と抽選を分離し、抽選後だけ次の最善手を選ぶexpectimaxを行う。
    if objective not in OBJECTIVES:
        raise ValueError('objectiveはlethalまたはvalueです')
    if max_states is not None:
        integer(max_states, 'max_states', 1, 1000000)
    integer(max_outcomes, 'max_outcomes', 1, 10000)
    integer(max_depth, 'max_depth', 1, 128)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 60:
        raise ValueError('secondsは0より大きく60以下です')
    chosen_weights = dict(WEIGHTS)
    if weights is not None:
        if not isinstance(weights, dict) or set(weights)-set(WEIGHTS):
            raise ValueError('未知の評価重みです')
        for name, weight in weights.items():
            chosen_weights[name] = integer(weight, name, 0, 100000)
    started = perf_counter()
    validate_scope(battle)
    if battle.state['winner'] is not None:
        raise ValueError('対戦中の盤面を選んでください')
    compact = sum(len(p['board']) for p in battle.state['players']) >= 7 and eligible(battle)
    max_states = max_states if max_states is not None else 500000 if compact else 10000
    if compact:
        return analyze_compact(battle, chosen_weights, objective, max_states, max_depth, max_outcomes, seconds, started)
    initial = copy.deepcopy(battle.state)
    initial['rng'] = 1
    root = ChanceBattle(initial, battle.cards, record=False)
    root.deadline = started + seconds
    nodes: list[Json] = []
    cache: dict[tuple[str, int], tuple[int, tuple[Fraction, Fraction]]] = {}
    incomplete: set[str] = set()
    transitions, draws_seen, duplicates = 0, 0, 0

    def rank(pair: tuple[Fraction, Fraction]) -> tuple[Fraction, Fraction]:
        # AI_NOTE: 評価順は公開パラメータで固定し、結果を見て都合のよい優先順位へ変えない。
        return pair if objective == 'lethal' else (pair[1], pair[0])

    def outcomes(current: ChanceBattle, action: Json) -> list[tuple[ChanceBattle, Fraction, tuple[int, ...]]]:
        # AI_NOTE: 操作途中の全抽選を列挙する。途中打切りの確率質量を再正規化して成功扱いしない。
        nonlocal draws_seen
        pending: list[tuple[tuple[int, ...], Fraction]] = [((), Fraction(1))]
        finished: list[tuple[ChanceBattle, Fraction, tuple[int, ...]]] = []
        while pending:
            if perf_counter()-started >= seconds:
                raise Limit('time')
            draws, probability = pending.pop()
            try:
                child = current.branch(action, draws)
            except Chance as chance:
                draws_seen += 1
                if len(pending)+len(finished)+chance.size > max_outcomes or len(draws) >= 128:
                    raise Limit('chance outcomes')
                pending.extend((draws+(index,), probability/chance.size) for index in reversed(range(chance.size)))
            else:
                finished.append((child, probability, draws))
        return finished

    def visit(current: ChanceBattle, depth: int) -> tuple[int, tuple[Fraction, Fraction]]:
        # AI_NOTE: 完全一致する状態だけ再利用する。能力付き盤面へ従来のスタッツ優越枝刈りを流用しない。
        nonlocal transitions, duplicates
        key = (state_key(current.state), depth)
        if key in cache:
            duplicates += 1
            return cache[key]
        index = len(nodes)
        best = value(current, chosen_weights)
        node: Json = {'id': index, 'state': copy.deepcopy(current.state), 'position': summary(current),
                      'actions': [], 'best_action': None, 'stop': metrics(best), 'value': metrics(best)}
        nodes.append(node)
        if current.state['winner'] is not None:
            cache[key] = (index, best)
            return index, best
        if len(nodes) >= max_states or depth >= max_depth or perf_counter()-started >= seconds:
            incomplete.add('states' if len(nodes) >= max_states else 'depth' if depth >= max_depth else 'time')
            node['cutoff'] = True
            return index, best
        for action in current.legal_actions():
            if action['type'] == 'end_turn':
                continue
            if len(nodes) >= max_states or perf_counter()-started >= seconds:
                incomplete.add('states' if len(nodes) >= max_states else 'time')
                break
            try:
                branches = outcomes(current, action)
            except Limit as reason:
                incomplete.add(str(reason))
                continue
            # Reserve one node per outcome before entering the action, keeping the public node cap strict.
            if len(nodes)+len(branches) > max_states:
                incomplete.add('states')
                continue
            edges: list[Json] = []
            expected = (Fraction(0), Fraction(0))
            for child, probability, draws in branches:
                if len(nodes) >= max_states:
                    # AI_NOTE: 残りの抽選結果も操作中に停止せず表現するため、枝は未採用として全体を打切る。
                    incomplete.add('states')
                    edges = []
                    break
                target, child_value = visit(child, depth+1)
                transitions += 1
                edges.append({'node': target, 'probability': str(probability), 'draws': list(draws)})
                expected = (expected[0]+probability*child_value[0], expected[1]+probability*child_value[1])
            if not edges:
                continue
            choice = {'action': copy.deepcopy(action), 'outcomes': edges, **metrics(expected)}
            node['actions'].append(choice)
            if rank(expected) > rank(best):
                best = expected
                node['best_action'] = len(node['actions'])-1
        node['value'] = metrics(best)
        cache[key] = (index, best)
        return index, best

    root_id, best = visit(root, 0)
    elapsed = (perf_counter()-started)*1000
    peak, method = peak_memory()
    selected = nodes[root_id]['best_action']
    return {'version': 1, 'strategy': 'practical-expectimax', 'objective': objective, 'weights': chosen_weights,
            'complete': not incomplete, 'optimal': not incomplete, 'cutoffs': sorted(incomplete),
            'scope': 'current turn before end-turn effects; uniform independent random choices; heuristic value, not full-game win rate',
            'root': root_id, 'record': root.export(), 'policy': nodes,
            'recommended_action': None if selected is None else nodes[root_id]['actions'][selected]['action'],
            **metrics(best), 'stats': {'states': len(nodes), 'transitions': transitions, 'chance_nodes': draws_seen,
                                     'duplicates': duplicates, 'elapsed_ms': elapsed, 'peak_rss_bytes': peak,
                                     'memory_method': method, 'memory_scope': 'whole process peak, including prior requests',
                                     'max_states': max_states, 'max_outcomes': max_outcomes, 'max_depth': max_depth,
                                     'seconds': seconds, 'budget_unit': 'policy state nodes'}}


def analyze_compact(battle: Battle, weights: dict[str, int], objective: str, max_states: int,
                    max_depth: int, max_outcomes: int, seconds: float, started: float) -> Json:
    # AI_NOTE: 計算用メモと公開方策を分離する。最適な条件別手順だけを通常Battleで再構成し全状態を正確に保存する。
    initial = copy.deepcopy(battle.state)
    initial['rng'] = 1
    root = ChanceBattle(initial, battle.cards, record=False)
    solver = Compact(root, weights, objective, max_states, max_depth, max_outcomes, started+seconds)
    try:
        best = solver.solve(solver.initial)
    except RuntimeError:
        if not solver.cutoffs:
            raise
        best = solver.score(solver.initial)
    nodes: list[Json] = []
    exported: dict[tuple[str, int], int] = {}
    policy_limit = min(max_states, 10000)

    def export(current: ChanceBattle, state: tuple[int, ...], depth: int) -> int:
        # AI_NOTE: 実状態が完全一致する枝だけ合流し、条件別方策の展開にも時間・出力状態上限を適用する。
        marker = (state_key(current.state), depth)
        if marker in exported:
            return exported[marker]
        if not solver.cutoffs:
            if perf_counter() >= started+seconds:
                raise Limit('time')
            if len(nodes) >= policy_limit:
                raise Limit('policy states')
        index = len(nodes)
        pair = solver.score(state) if solver.cutoffs else solver.cache[state if max_depth >= solver.horizon else state+(depth,)][0]
        node: Json = {'id': index, 'state': copy.deepcopy(current.state), 'position': summary(current),
                      'actions': [], 'best_action': None, 'stop': metrics(value(current, weights)), 'value': metrics(pair)}
        nodes.append(node)
        exported[marker] = index
        if solver.cutoffs:
            node['cutoff'] = True
            return index
        selected = solver.choice(state, depth)
        if selected is None:
            return index
        action = solver.public_action(selected)
        if action not in current.legal_actions():
            raise ValueError('高速探索の操作が公開エンジンで不正です')
        branches = solver.children(state, selected)
        edges = []
        is_random = selected[0] == 0 and selected[2] == -1
        for number, child_state in enumerate(branches):
            draws = (number,) if is_random and any(state[i] > 0 for i in range(solver.n, solver.count)) else ()
            child = current.branch(action, draws)
            encoded = solver.encode(child)
            # The selected evolution may already have died; its resource cost remains in the memo key.
            adjusted = list(encoded)
            adjusted[solver.count+2] = child_state[solver.count+2]
            if tuple(adjusted) != child_state or solver.score(child_state) != value(child, weights):
                raise ValueError('高速探索の遷移または評価が公開エンジンと一致しません')
            target = export(child, child_state, depth+1)
            edges.append({'node': target, 'probability': str(Fraction(1, len(branches))), 'draws': list(draws)})
        node['best_action'] = 0
        node['actions'] = [{'action': action, 'outcomes': edges, **metrics(pair)}]
        return index

    try:
        export(root, solver.initial, 0)
    except Limit as reason:
        # AI_NOTE: 出力途中の確率分布を返さず、完全な停止方策と未完了理由へ戻す。
        solver.cutoffs.add(str(reason))
        nodes.clear()
        exported.clear()
        best = solver.score(solver.initial)
        export(root, solver.initial, 0)
    elapsed = (perf_counter()-started)*1000
    peak, method = peak_memory()
    return {'version': 1, 'strategy': 'practical-compact-expectimax', 'objective': objective, 'weights': weights,
            'complete': not solver.cutoffs, 'optimal': not solver.cutoffs, 'cutoffs': sorted(solver.cutoffs),
            'scope': 'current turn before end-turn effects; uniform independent random choices; heuristic value, not full-game win rate',
            'policy_scope': 'selected optimal policy only; all legal alternatives evaluated in compact memo',
            'root': 0, 'record': root.export(), 'policy': nodes,
            'recommended_action': nodes[0]['actions'][0]['action'] if nodes[0]['actions'] else None,
            **metrics(best), 'stats': {'states': len(solver.cache), 'transitions': solver.transitions,
                'duplicates': solver.hits, 'policy_nodes': len(nodes), 'elapsed_ms': elapsed, 'peak_rss_bytes': peak,
                'memory_method': method, 'memory_scope': 'whole process peak, including prior requests',
                'max_states': max_states, 'max_outcomes': max_outcomes, 'max_depth': max_depth,
                'max_policy_nodes': policy_limit,
                'seconds': seconds, 'budget_unit': 'compact evaluated state records'}}


def replay_branch(record: Json, steps: list[Json]) -> Json:
    # AI_NOTE: 抽選結果は利用者が選べる操作ではなく条件付き再生資料。合法手と各抽選の範囲を再検査する。
    base = replay(record)
    validate_scope(base)
    current = ChanceBattle(base.state, base.cards, record=False)
    probability = Fraction(1)
    if not isinstance(steps, list) or len(steps) > 128:
        raise ValueError('条件付き再生は128操作以内です')
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'action', 'draws'} or not isinstance(step['draws'], list):
            raise ValueError('再生にはactionとdrawsが必要です')
        if step['action'] not in current.legal_actions() or step['action']['type'] == 'end_turn':
            raise ValueError('不正な操作・対象です')
        try:
            current = current.branch(step['action'], tuple(step['draws']))
        except Chance as error:
            raise ValueError('抽選結果が不足しています') from error
        for size in current.sizes:
            probability /= size
    return {'conditional': True, 'probability': str(probability), 'state': current.state,
            'position': summary(current)}


def verify_policy(result: Json) -> Json:
    # AI_NOTE: 出力した全辺を公開の条件付き再生で確認し、確率質量と適応後の期待値も独立に読み戻す。
    checked = 0
    for node in result['policy']:
        for choice in node['actions']:
            total = Fraction(0)
            expected = (Fraction(0), Fraction(0))
            for edge in choice['outcomes']:
                record = {**result['record'], 'initial': node['state'], 'actions': [], 'frames': []}
                actual = replay_branch(record, [{'action': choice['action'], 'draws': edge['draws']}])
                target = result['policy'][edge['node']]
                probability = Fraction(edge['probability'])
                if state_key(actual['state']) != state_key(target['state']) or Fraction(actual['probability']) != probability:
                    raise ValueError('再生状態または確率が一致しません')
                total += probability
                expected = (expected[0]+probability*Fraction(target['value']['win_probability_exact']),
                            expected[1]+probability*Fraction(target['value']['expected_value_exact']))
                checked += 1
            if total != 1 or metrics(expected) != {k: choice[k] for k in metrics(expected)}:
                raise ValueError('分岐の確率質量または期待値が一致しません')
    return {'status': 'PASS', 'edges_checked': checked, 'coverage': 'all exported action outcomes'}


def main() -> None:
    # AI_NOTE: CLIも通常HTTPと同じ入口を使い、測定・全分岐再生・入力を新しい出力先へ保存する。
    parser = argparse.ArgumentParser(description='能力・カード使用・ランダム結果込みの現在ターン探索')
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--objective', choices=OBJECTIVES, default='lethal')
    parser.add_argument('--weights', type=json.loads, help='評価重みのJSONオブジェクト。省略項目は既定値')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-states', type=int, help='状態上限。省略時は一般探索10000、高速探索500000')
    parser.add_argument('--max-outcomes', type=int, default=4096)
    parser.add_argument('--max-depth', type=int, default=64)
    parser.add_argument('--seconds', type=float, default=10)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    if isinstance(cases, dict):
        cases = [cases]
    case = next((case for case in cases if case['id'] == args.case), None)
    if case is None:
        parser.error('指定ケースがありません')
    if args.output.exists():
        parser.error('保存先は未使用のディレクトリを指定してください')
    result = analyze(Battle(case['state'], case['cards']), objective=args.objective, weights=args.weights,
                     max_states=args.max_states, max_outcomes=args.max_outcomes, max_depth=args.max_depth, seconds=args.seconds)
    result['case_id'] = case['id']
    args.output.mkdir(parents=True)
    save_result(args.output/'case.json', case)
    save_result(args.output/'report.json', result)
    result['replay'] = verify_policy(result)
    save_result(args.output/'report.json', result)
    text = (f"# 実戦盤面探索: {case['id']}\n\n"
            f"探索完了: {result['complete']} / 最適性確認: {result['optimal']}\n\n"
            f"目的: {result['objective']}（lethal=今ターン勝利確率優先、value=仮の評価点期待値優先）\n\n"
            f"今ターン勝利確率: {result['win_probability_exact']} / 期待評価点: {result['expected_value_exact']}\n\n"
            f"解析時間: {result['stats']['elapsed_ms']:.3f} ms / プロセス最大常駐メモリ: {result['stats']['peak_rss_bytes']/1048576:.2f} MiB\n\n"
            f"全分岐再生: {result['replay']['status']} ({result['replay']['edges_checked']}辺)\n\n"
            "時間は解析のみ。メモリはプロセス全体。再生検証は計測外。未完了時は最善手の保証なし。\n\n"
            "[入力](case.json) / [全分岐・確率・条件別推奨手・評価重み](report.json)\n")
    (args.output/'report.md').write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
