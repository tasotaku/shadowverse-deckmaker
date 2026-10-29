"""Bounded multi-turn expectiminimax and observation-only sampled AI integration."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from fractions import Fraction
from math import comb
from pathlib import Path
from time import perf_counter
from typing import Any

from svdeck.battle.battle import Battle, Json, integer
from svdeck.battle.battle_ai import BASE_WEIGHTS, Player, features, sample_world
from svdeck.battle.battle_practical import Chance, ChanceBattle, Limit, state_key
from svdeck.battle.combat_benchmark import peak_memory, save_result

Value = tuple[Fraction, Fraction, Fraction]


def validate_work(cards: dict[str, Json]) -> None:
    # AI_NOTE: eagerな合法手の直積と空repeatも事前に制限し、時間検査に到達しない巨大展開を拒否する。
    for card in cards.values():
        pending: list[tuple[Any, int]] = [(card, 1)]
        choices: dict[str, int] = {}
        work = 0
        while pending:
            item, factor = pending.pop()
            if isinstance(item, dict):
                if 'op' in item:
                    work += factor*int(item.get('count', 1) if item['op'] == 'repeat' else 1)
                    if work > 100000:
                        raise ValueError('先読みはカードごとの効果展開10万以内です')
                    if str(item.get('target', '')).startswith('chosen_'):
                        count = item.get('select_count', 1)
                        choices[item.get('choice', 'target')] = max(choices.get(item.get('choice', 'target'), 1), comb(9, count) if 0 <= count <= 9 else 1)
                        size = 1
                        for number in choices.values():
                            size *= number
                        if len(choices) > 2 or size > 4096:
                            raise ValueError('先読みは対象選択欄2種・選択組合せ4096以内です')
                multiplier = factor*(item.get('count', 1) if item.get('op') == 'repeat' else 1)
                pending.extend((child, multiplier) for child in item.values() if isinstance(child, (dict, list)))
            elif isinstance(item, list):
                pending.extend((child, factor) for child in item)


def value(battle: Battle, owner: int, weights: dict[str, float]) -> Value:
    # AI_NOTE: 勝率・敗率・盤面点を分離し、端数を丸めず確率付きの相手最善応答を比較する。
    winner = battle.state['winner']
    score = sum((Fraction(str(weights[k]))*Fraction(str(v)) for k, v in features(battle, owner).items()), Fraction(0))
    return Fraction(int(winner == owner)), Fraction(-int(winner == 1-owner)), score


def metrics(score: Value) -> Json:
    # AI_NOTE: 点数を勝率と呼ばず、有限の仮定局面での勝敗確率を別々に公開する。
    return {'win_probability_exact': str(score[0]), 'loss_probability_exact': str(-score[1]),
            'expected_value_exact': str(score[2]), 'expected_value': float(score[2])}


@dataclass
class Budget:
    maximum: int
    deadline: float
    states: int = 0

    def check(self, consume: bool = False) -> None:
        # AI_NOTE: 仮定手札と反復深さをまたいで同じ予算を使い、実行時間を掛け算で増やさない。
        if perf_counter() >= self.deadline:
            raise Limit('time')
        if consume:
            if self.states >= self.maximum:
                raise Limit('states')
            self.states += 1


class Search:
    def __init__(self, battle: Battle, turns: int, weights: dict[str, float], budget: Budget,
                 max_actions: int, max_outcomes: int):
        # AI_NOTE: 手札使用・攻撃・終了を同じ木で扱い、盤面評価で候補を先に落とさない。
        self.root = ChanceBattle(battle.state, battle.cards, record=False)
        self.root.deadline = budget.deadline
        self.owner = battle.state['active_player']
        self.turns, self.weights, self.budget = turns, weights, budget
        self.max_actions, self.max_outcomes = max_actions, max_outcomes
        self.cache: dict[tuple[str, int, int], tuple[Value, Json | None]] = {}
        self.root_values: list[Json] = []
        self.patterns: dict[tuple[str, ...], int] = {}
        self.hand = {e['id']: e['name'] for e in battle.state['players'][self.owner]['hand']}
        self.initial_turn = battle.state['players'][self.owner]['turn']
        self.transitions, self.hits = 0, 0

    def branches(self, battle: ChanceBattle, action: Json) -> list[tuple[ChanceBattle, Fraction, tuple[int, ...]]]:
        # AI_NOTE: 未観測の抽選を全て積分する。出目ごとの次手はvisit内で改めて選択する。
        pending: list[tuple[tuple[int, ...], Fraction]] = [((), Fraction(1))]
        result: list[tuple[ChanceBattle, Fraction, tuple[int, ...]]] = []
        while pending:
            self.budget.check()
            draws, probability = pending.pop()
            try:
                child = battle.branch(action, draws)
            except Chance as chance:
                if len(result)+len(pending)+chance.size > self.max_outcomes or len(draws) >= 128:
                    raise Limit('chance outcomes')
                pending.extend((draws+(i,), probability/chance.size) for i in reversed(range(chance.size)))
            else:
                result.append((child, probability, draws))
        return result

    def visit(self, battle: ChanceBattle, turns: int, actions: int) -> Value:
        # AI_NOTE: 全状態・残りターン・残り操作数が一致した場合だけ合流し、資源や能力が違う候補を残す。
        key = (state_key(battle.state), turns, actions)
        if key in self.cache:
            self.hits += 1
            return self.cache[key][0]
        self.budget.check(consume=True)
        if battle.state['winner'] is not None or turns == 0:
            score = value(battle, self.owner, self.weights)
            self.cache[key] = score, None
            return score
        if actions >= self.max_actions:
            raise Limit('actions per turn')
        own = battle.state['active_player'] == self.owner
        best: Value | None = None
        selected = None
        for action in battle.legal_actions():
            ending = action['type'] == 'end_turn'
            expected = [Fraction(0), Fraction(0), Fraction(0)]
            for child, probability, _ in self.branches(battle, action):
                score = self.visit(child, turns-int(ending), 0 if ending else actions+1)
                self.transitions += 1
                for i in range(3):
                    expected[i] += probability*score[i]
            result = (expected[0], expected[1], expected[2])
            if best is None or (result > best if own else result < best):
                best, selected = result, action
            if turns == self.turns and actions == 0 and battle is self.root:
                self.root_values.append({'action': copy.deepcopy(action), **metrics(result)})
            if ending and own and battle.state['players'][self.owner]['turn'] == self.initial_turn:
                remaining = {e['id'] for e in battle.state['players'][self.owner]['hand']}
                used = tuple(sorted(set(self.hand)-remaining))
                self.patterns[used] = self.patterns.get(used, 0)+1
        assert best is not None
        self.cache[key] = best, selected
        return best

    def policy(self) -> list[Json]:
        # AI_NOTE: 最善応答と確率分岐を通常状態で出力し、方策の構築にも同じ時間制限を適用する。
        nodes: list[Json] = []
        seen: dict[tuple[str, int, int], int] = {}
        def emit(battle: ChanceBattle, turns: int, actions: int) -> int:
            # AI_NOTE: 実状態が同じ場合だけ再利用し、手順再生で隠れた履歴が食い違わないようにする。
            self.budget.check()
            key = (state_key(battle.state), turns, actions)
            if key in seen:
                return seen[key]
            if len(nodes) >= 10000:
                raise Limit('policy states')
            score, action = self.cache[key]
            index = len(nodes)
            seen[key] = index
            node: Json = {'id': index, 'state': copy.deepcopy(battle.state), 'turns_remaining': turns,
                          'action': copy.deepcopy(action), 'outcomes': [], **metrics(score)}
            nodes.append(node)
            if action is not None:
                ending = action['type'] == 'end_turn'
                for child, probability, draws in self.branches(battle, action):
                    target = emit(child, turns-int(ending), 0 if ending else actions+1)
                    node['outcomes'].append({'node': target, 'probability': str(probability), 'draws': list(draws)})
            return index
        emit(self.root, self.turns, 0)
        return nodes


def settings(turns: int, max_states: int, seconds: float, max_actions: int, max_outcomes: int) -> None:
    # AI_NOTE: 外部入力を境界で検査し、深さや予算の無効値を途中探索の失敗と混同しない。
    integer(turns, 'turns', 1, 5)
    integer(max_states, 'max_states', 1, 100000)
    integer(max_actions, 'max_actions', 1, 64)
    integer(max_outcomes, 'max_outcomes', 1, 4096)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 60:
        raise ValueError('secondsは0より大きく60以下です')


def analyze(battle: Battle, *, turns: int = 3, max_states: int = 10000, seconds: float = 10,
            max_actions: int = 20, max_outcomes: int = 128) -> Json:
    # AI_NOTE: 固定手札・固定山札の診断入口。実対戦の非公開情報推定とは明示的に分ける。
    settings(turns, max_states, seconds, max_actions, max_outcomes)
    validate_work(battle.cards)
    if battle.state['winner'] is not None:
        raise ValueError('対戦中の局面が必要です')
    start = perf_counter()
    budget = Budget(max_states, start+seconds)
    search = Search(battle, turns, BASE_WEIGHTS, budget, max_actions, max_outcomes)
    cutoff: list[str] = []
    policy: list[Json] = []
    score = value(battle, search.owner, BASE_WEIGHTS)
    try:
        score = search.visit(search.root, turns, 0)
        policy = search.policy()
    except Limit as reason:
        cutoff.append(str(reason))
        score = value(battle, search.owner, BASE_WEIGHTS)
    peak, method = peak_memory()
    action = policy[0]['action'] if policy else {'type': 'end_turn'}
    return {'version': 1, 'strategy': 'turn-expectiminimax', 'scope': 'fixed hand and deck scenario; not hidden-information game optimality',
            'turns': turns, 'boundary': 'full end_turn including next turn start and draw',
            'complete': not cutoff, 'optimal': not cutoff, 'cutoffs': cutoff, 'recommended_action': action,
            'fallback': bool(cutoff), 'record': battle.export(), 'policy': policy, 'candidates': search.root_values,
            'hand_patterns': [{'used': list(ids), 'names': [search.hand[i] for i in ids], 'positions': count}
                              for ids, count in sorted(search.patterns.items())],
            'hand_patterns_scope': 'reachable conditional turn endings; no immediate-score pruning', **metrics(score),
            'stats': {'states': budget.states, 'transitions': search.transitions, 'duplicates': search.hits,
                      'elapsed_ms': (perf_counter()-start)*1000, 'peak_rss_bytes': peak, 'memory_method': method,
                      'memory_scope': 'whole process peak', 'max_states': max_states, 'seconds': seconds,
                      'max_actions': max_actions, 'max_outcomes': max_outcomes}}


def choose(player: Player, observation: Json) -> Json:
    # AI_NOTE: 実手札・山札を受け取らず同一の仮定群で全初手を比較。完了した最深段階だけを採用する。
    start = perf_counter()
    validate_work(player.cards)
    budget = Budget(player.max_nodes, start+player.seconds)
    worlds = [sample_world(observation, player.cards, player.seed+i*7919, use_known=True) for i in range(2)]
    fallback_action = observation['legal_actions'][0]
    fallback_score: Value | None = None
    try:
        # AI_NOTE: 本探索前に同じ予算内で一手評価を用意し、打切りで常にパスする退化を防ぐ。
        probes = [Search(world, 1, player.weights, budget, 20, 128) for world in worlds]
        for action in observation['legal_actions']:
            expected = [Fraction(0), Fraction(0), Fraction(0)]
            for probe in probes:
                for child, probability, _ in probe.branches(probe.root, action):
                    budget.check(consume=True)
                    score = value(child, probe.owner, player.weights)
                    for i in range(3):
                        expected[i] += probability*score[i]/len(probes)
            total = (expected[0], expected[1], expected[2])
            if fallback_score is None or total > fallback_score:
                fallback_score, fallback_action = total, action
    except Limit:
        pass  # Fully evaluated earlier actions remain a legal one-step fallback, never a completed horizon.
    last: list[Json] = []
    patterns: set[tuple[str, ...]] = set()
    completed = 0
    cutoff: list[str] = []
    for horizon in range(1, player.turns+1):
        stage: list[Search] = []
        try:
            for world in worlds:
                search = Search(world, horizon, player.weights, budget, 20, 128)
                search.visit(search.root, horizon, 0)
                stage.append(search)
        except Limit as limit:
            cutoff.append(str(limit))
            break
        rows = []
        for action in observation['legal_actions']:
            scores = [next(r for r in search.root_values if r['action'] == action) for search in stage]
            pair: Value = (sum((Fraction(r['win_probability_exact']) for r in scores), Fraction(0))/len(scores),
                           -sum((Fraction(r['loss_probability_exact']) for r in scores), Fraction(0))/len(scores),
                           sum((Fraction(r['expected_value_exact']) for r in scores), Fraction(0))/len(scores))
            rows.append({'action': copy.deepcopy(action), **metrics(pair), 'rank': pair})
        last = sorted(rows, key=lambda r: r['rank'], reverse=True)
        completed = horizon
        patterns = {pattern for search in stage for pattern in search.patterns}
    selected = last[0] if last else None
    action = selected['action'] if selected else fallback_action
    for row in last:
        row.pop('rank')
    hand = {e['id']: e['name'] for e in observation['players'][observation['active_player']]['hand']}
    reason = f'手札の使用候補を残し、{completed}/{player.turns}ターン先まで比較。相手手札・ドローは公開情報から2通りを仮定'
    if cutoff:
        reason += '。上限到達：'+', '.join(cutoff)+'。'+('完了済みの深さの判断を使用' if completed else '完了した一手評価へ切替' if fallback_score else '評価を完了できなかったため未評価の合法手を使用')
    return {'policy': 'lookahead', 'action': action, 'reason': reason,
            'score': selected['expected_value'] if selected else float(fallback_score[2]) if fallback_score else None, 'plan': [action],
            'nodes': budget.states, 'depth': completed, 'turns_requested': player.turns, 'depth_unit': 'turns',
            'uncertain': True, 'proven_win': False, 'limited': bool(cutoff), 'cutoffs': cutoff,
            'complete': completed == player.turns, 'optimal': False, 'fallback': completed == 0,
            'fallback_evaluated': fallback_score is not None,
            'candidates': [{'action': r['action'], 'score': r['expected_value'], **r} for r in last],
            'hand_patterns': [{'used': list(p), 'names': [hand.get(i, i) for i in p]} for p in sorted(patterns)],
            'scope': 'sampled hidden worlds; future per-world optimal responses are an approximation',
            'settings': {'policy_version': 4, 'turns': player.turns, 'max_nodes': player.max_nodes, 'seconds': player.seconds,
                         'seed': player.seed, 'hand_samples': 2}, 'elapsed_ms': (perf_counter()-start)*1000}


def verify_policy(result: Json) -> Json:
    # AI_NOTE: 全出力辺を合法手・通常ターン処理で再生し、確率と有理数の期待値を検算する。
    checked = 0
    for node in result['policy']:
        action = node['action']
        if action is None:
            continue
        battle = ChanceBattle(node['state'], result['record']['cards'], record=False)
        if action not in battle.legal_actions():
            raise ValueError('方策に不正な手があります')
        expected = [Fraction(0), Fraction(0), Fraction(0)]
        mass = Fraction(0)
        for edge in node['outcomes']:
            child = battle.branch(action, tuple(edge['draws']))
            probability = Fraction(1)
            for size in child.sizes:
                probability /= size
            target = result['policy'][edge['node']]
            if state_key(child.state) != state_key(target['state']) or probability != Fraction(edge['probability']):
                raise ValueError('方策の状態または抽選確率が一致しません')
            scores = (Fraction(target['win_probability_exact']), -Fraction(target['loss_probability_exact']), Fraction(target['expected_value_exact']))
            for i in range(3):
                expected[i] += probability*scores[i]
            mass += probability
            checked += 1
        if mass != 1 or metrics((expected[0], expected[1], expected[2])) != {k: node[k] for k in metrics((expected[0], expected[1], expected[2]))}:
            raise ValueError('方策の期待値が一致しません')
    return {'status': 'PASS', 'edges_checked': checked, 'coverage': 'all exported policy edges'}


def main() -> None:
    # AI_NOTE: 公開CLIで入力・結果・実時間/メモリ・全方策再生を保存し、既存出力は上書きしない。
    parser = argparse.ArgumentParser(description='手札候補を保持するnターン先読み（固定シナリオ診断）')
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', type=Path, required=True)
    for name, default in (('turns', 3), ('max-states', 10000), ('max-actions', 20), ('max-outcomes', 128)):
        parser.add_argument('--'+name, type=int, default=default)
    parser.add_argument('--seconds', type=float, default=10)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    cases = [cases] if isinstance(cases, dict) else cases
    case = next((c for c in cases if c['id'] == args.case), None)
    if case is None or args.output.exists():
        parser.error('ケースが存在し、保存先が未使用である必要があります')
    result = analyze(Battle(case['state'], case['cards']), turns=args.turns, max_states=args.max_states,
                     max_actions=args.max_actions, max_outcomes=args.max_outcomes, seconds=args.seconds)
    result['replay'] = verify_policy(result)
    args.output.mkdir(parents=True)
    save_result(args.output/'case.json', case)
    save_result(args.output/'report.json', result)
    text = f"# {case['id']}\n\n{args.turns}ターン / 完了: {result['complete']} / 固定シナリオ最適性: {result['optimal']}\n\n勝率 {result['win_probability_exact']} / 敗率 {result['loss_probability_exact']} / 評価 {result['expected_value_exact']}\n\n{result['stats']['elapsed_ms']:.2f} ms / プロセス最大 {result['stats']['peak_rss_bytes']/1048576:.2f} MiB\n\n全出力辺再生: {result['replay']['status']} ({result['replay']['edges_checked']})\n\n非公開情報を推定する通常AIの最適性保証ではありません。\n"
    (args.output/'report.md').write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    # AI_NOTE: 入力対象外は長いtracebackでなく、完了していないことと原因を同じJSONで通知する。
    try:
        main()
    except (ValueError, KeyError, TypeError) as error:
        print(json.dumps({'complete': False, 'optimal': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None
