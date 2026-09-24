"""All decisions in the current turn, with shared states and explicit chance edges.

The frontier is a board/resource Pareto view of STOP positions, not a list of
selectable lucky outcomes. The unpruned decision graph is retained in full.
"""
from __future__ import annotations

import argparse
import copy
import json
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from typing import Any

from .battle import Battle, Json, integer
from .battle_practical import Chance, ChanceBattle, Limit, validate_scope
from .combat_benchmark import peak_memory

ENTITY_FIELDS = frozenset(('id', 'card_id', 'name', 'cost', 'attack', 'health', 'max_health',
                          'keywords', 'evolved', 'attacks', 'entered_turn', 'countdown'))
PLAYER_FIELDS = ('health', 'max_health', 'pp', 'max_pp', 'turn', 'ep', 'sep',
                 'evolved_this_turn', 'extra_pp_used', 'graveyard', 'combo')
PLAYER_KNOWN = frozenset(PLAYER_FIELDS) | {'board', 'hand', 'deck', 'destroyed'}


def clone_entity(entity: Json) -> Json:
    # AI_NOTE: 通常個体はkeywordsだけが可変配列。追加の可変値は省略せず深く複製する。
    result = dict(entity)
    result['keywords'] = list(entity['keywords'])
    if len(entity) != len(ENTITY_FIELDS):
        for key, value in entity.items():
            if key not in ENTITY_FIELDS and isinstance(value, (dict, list)):
                result[key] = copy.deepcopy(value)
    return result


def entity_key(entity: Json) -> tuple[Any, ...]:
    # AI_NOTE: 正規化済みの固定列を直接読む。任意の追加列も残し、未知能力を同一視しない。
    extras = (() if len(entity) == len(ENTITY_FIELDS) else
              tuple((k, freeze(v)) for k, v in sorted(entity.items()) if k not in ENTITY_FIELDS))
    return (entity['id'], entity['card_id'], entity['name'], entity['cost'], entity['attack'],
            entity['health'], entity['max_health'], tuple(sorted(entity['keywords'])),
            entity['evolved'], entity['attacks'], entity['entered_turn'], entity['countdown'], extras)


def freeze(value: Any) -> Any:
    # AI_NOTE: ハッシュだけで同一視せず、JSON値全体を不変の比較キーにする。
    if isinstance(value, dict):
        return tuple((k, freeze(v)) for k, v in sorted(value.items()))
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    return value


class Pool:
    def __init__(self) -> None:
        # AI_NOTE: 反復する個体・盤面・プレイヤーを共有し、全状態のdeepcopy保持を避ける。
        self.values: list[Any] = []
        self.ids: dict[Any, int] = {}

    def add(self, key: Any, value: Any = None) -> int:
        # AI_NOTE: 値は登録後不変。キー衝突はPythonの完全等価比較で解決する。
        found = self.ids.get(key)
        if found is not None:
            return found
        found = len(self.values)
        self.ids[key] = found
        self.values.append(key if value is None else value)
        return found


class TurnBattle(ChanceBattle):
    def branch(self, action: Json, draws: tuple[int, ...]) -> TurnBattle:
        # AI_NOTE: scope検査済みの効果は山札を変更しない。変更される個体・公開履歴だけを分離する。
        child = copy.copy(self)
        child.state = dict(self.state)
        child.state['players'] = []
        for player in self.state['players']:
            other = dict(player)
            for zone in ('board', 'hand'):
                other[zone] = [clone_entity(e) for e in player[zone]]
            other['destroyed'] = list(player['destroyed'])
            if len(player) != len(PLAYER_KNOWN):
                for key, value in player.items():
                    if key not in PLAYER_KNOWN and isinstance(value, (dict, list)):
                        other[key] = copy.deepcopy(value)
            child.state['players'].append(other)
        if 'deck_knowledge' in self.state:
            child.state['deck_knowledge'] = copy.deepcopy(self.state['deck_knowledge'])
        child.events, child.frames, child.actions = [], [], []
        child.pending, child.destroyed_in_action = [], set()
        child.draws, child.draw_at, child.sizes = draws, 0, ()
        child.execute(action)
        if child.draw_at != len(draws):
            raise ValueError('余分な抽選結果があります')
        return child


class Positions:
    def __init__(self, root: TurnBattle) -> None:
        # AI_NOTE: 固定部分は開始記録に一度だけ保存し、可変部分は番号で参照する。
        self.root = root
        self.entities, self.zones, self.players, self.metadata = Pool(), Pool(), Pool(), Pool()
        self.positions = Pool()

    def encode(self, state: Json) -> tuple[int, bool]:
        # AI_NOTE: 盤面順・ID・攻撃権・全資源を保存。破壊順だけは現scopeで参照されないため多重集合化する。
        key = self.key(state)
        count = len(self.positions.values)
        index = self.positions.add(key)
        return index, index == count

    def key(self, state: Json) -> tuple[Any, ...]:
        # AI_NOTE: 共有部品だけ先に登録し、抽選の全結果が状態上限へ収まるか正確に調べる。
        player_ids = []
        for player in state['players']:
            zone_ids = []
            for zone in ('board', 'hand'):
                entities = []
                for entity in player[zone]:
                    entity_marker = entity_key(entity)
                    entity_id = self.entities.ids.get(entity_marker)
                    if entity_id is None:
                        normalized = {**entity, 'keywords': sorted(entity['keywords'])}
                        entity_id = self.entities.add(entity_marker, normalized)
                    entities.append(entity_id)
                zone_ids.append(self.zones.add(tuple(entities)))
            extras = (() if len(player) == len(PLAYER_KNOWN) else
                      tuple((k, freeze(v)) for k, v in sorted(player.items()) if k not in PLAYER_KNOWN))
            meta_marker = tuple(player[k] for k in PLAYER_FIELDS) + (tuple(sorted(player['destroyed'])), extras)
            metadata = self.metadata.ids.get(meta_marker)
            if metadata is None:
                meta = {k: v for k, v in player.items() if k not in ('board', 'hand', 'deck', 'destroyed')}
                meta['destroyed'] = sorted(player['destroyed'])
                metadata = self.metadata.add(meta_marker, meta)
            player_ids.append(self.players.add((metadata, *zone_ids)))
        knowledge = self.metadata.add(freeze(state.get('deck_knowledge')), state.get('deck_knowledge'))
        return (state['winner'], state['next_id'], *player_ids, knowledge)

    def decode(self, index: int) -> TurnBattle:
        # AI_NOTE: 正規化した代表状態を復元する。元の履歴順が必要な利用者はwitnessを再生する。
        winner, next_id, first, second, knowledge = self.positions.values[index]
        current = copy.copy(self.root)
        current.state = dict(self.root.state, winner=winner, next_id=next_id)
        current.state['players'] = []
        for owner, player_id in enumerate((first, second)):
            meta, board, hand = self.players.values[player_id]
            player = dict(self.metadata.values[meta], deck=self.root.state['players'][owner]['deck'])
            for name, zone in (('board', board), ('hand', hand)):
                player[name] = [self.entities.values[e] for e in self.zones.values[zone]]
            current.state['players'].append(player)
        if 'deck_knowledge' in current.state:
            current.state['deck_knowledge'] = self.metadata.values[knowledge]
        return current

    def export(self) -> Json:
        # AI_NOTE: JSONでも共有表を保持し、大きい盤面の同じ個体を各nodeへ複製しない。
        return {'positions': self.positions.values, 'players': self.players.values,
                'zones': self.zones.values, 'entities': self.entities.values, 'metadata': self.metadata.values}


def endpoint_key(current: Battle) -> tuple[Any, tuple[int, ...]]:
    # AI_NOTE: 停止盤面だけを比較する。手札の包含は別途調べ、能力・並び・効果が違う盤面は比べない。
    owner = current.state['active_player']
    own, enemy = (current.state['players'][i] for i in (owner, 1-owner))
    shapes = []
    values = [own['health'], -enemy['health'], own['pp'], own['ep'], own['sep']]
    for sign, player in ((1, own), (-1, enemy)):
        board = []
        for entity in player['board']:
            card = current.cards[entity['card_id']]
            behavior = {k: v for k, v in card.items() if k not in ('card_id', 'name', 'text', 'attack', 'health', 'synthetic')}
            # AI_NOTE: 未攻撃・召喚酔いも比較条件に残す。顔打点を増やす代わりに失う行動権は優越ではない。
            traits = {k: v for k, v in entity.items()
                      if k not in ('id', 'card_id', 'name', 'attack', 'health', 'max_health')}
            traits['keywords'] = sorted(traits['keywords'])
            board.append((freeze(behavior), freeze(traits)))
            values.extend(sign*entity[k] for k in ('attack', 'health', 'max_health'))
        shapes.append(tuple(board))
    return (current.state['winner'], tuple(shapes)), tuple(values)


def pareto(positions: Positions, deadline: float) -> tuple[list[int], bool]:
    # AI_NOTE: 探索後の表示だけを成分比較で絞る。抽選辺と探索中の状態は一つも削除しない。
    owner = positions.root.state['active_player']
    behaviors: dict[str, Any] = {}
    body_shapes = Pool()
    bodies: dict[int, tuple[int, tuple[int, ...]]] = {}
    zones: dict[int, tuple[tuple[int, ...], tuple[int, ...]]] = {}
    hand_bits: dict[int, int] = {}
    hand_masks: dict[int, int] = {}

    def hand_mask(zone: int) -> int:
        # AI_NOTE: 同じ個体の全特性が一致した時だけ同じbitにする。異なるカードの交換を優越とはしない。
        cached = hand_masks.get(zone)
        if cached is not None:
            return cached
        mask = 0
        for entity_id in positions.zones.values[zone]:
            bit = hand_bits.get(entity_id)
            if bit is None:
                bit = len(hand_bits)
                hand_bits[entity_id] = bit
            mask |= 1 << bit
        hand_masks[zone] = mask
        return mask

    def zone_parts(zone: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
        # AI_NOTE: 個体・盤面は共有表ごとに一度だけ比較用へ変換する。並びと全特性は保持する。
        cached = zones.get(zone)
        if cached is not None:
            return cached
        shapes: list[int] = []
        values: list[int] = []
        for entity_id in positions.zones.values[zone]:
            body = bodies.get(entity_id)
            if body is None:
                entity = positions.entities.values[entity_id]
                cid = entity['card_id']
                if cid not in behaviors:
                    behaviors[cid] = freeze({k: v for k, v in positions.root.cards[cid].items()
                                            if k not in ('card_id', 'name', 'text', 'attack', 'health', 'synthetic')})
                # AI_NOTE: 共有表で比較するときも公開endpoint_keyと同じ攻撃権・登場ターンを保持する。
                traits = {k: v for k, v in entity.items()
                          if k not in ('id', 'card_id', 'name', 'attack', 'health', 'max_health')}
                traits['keywords'] = sorted(traits['keywords'])
                shape = body_shapes.add((behaviors[cid], freeze(traits)))
                body = shape, tuple(entity[k] for k in ('attack', 'health', 'max_health'))
                bodies[entity_id] = body
            shapes.append(body[0])
            values.extend(body[1])
        result = tuple(shapes), tuple(values)
        zones[zone] = result
        return result

    groups: dict[Any, dict[tuple[tuple[int, ...], int], int]] = {}
    for index in range(len(positions.positions.values)):
        if perf_counter() >= deadline:
            return list(range(len(positions.positions.values))), False
        position = positions.positions.values[index]
        own_meta, own_board, hand = positions.players.values[position[2+owner]]
        enemy_meta, enemy_board, _ = positions.players.values[position[3-owner]]
        own, enemy = positions.metadata.values[own_meta], positions.metadata.values[enemy_meta]
        own_shape, own_values = zone_parts(own_board)
        enemy_shape, enemy_values = zone_parts(enemy_board)
        shape = position[0], (own_shape, enemy_shape)
        values = (own['health'], -enemy['health'], own['pp'], own['ep'], own['sep']) + own_values + tuple(-v for v in enemy_values)
        groups.setdefault(shape, {}).setdefault((values, hand_mask(hand)), index)
    selected = []
    for group in groups.values():
        # Lexicographic values then hand cardinality place every possible dominator first.
        skyline: list[tuple[tuple[int, ...], int]] = []
        for values, hand in sorted(group, key=lambda item: (item[0], item[1].bit_count()), reverse=True):
            if perf_counter() >= deadline:
                return list(range(len(positions.positions.values))), False
            if not any(prior_hand & hand == hand and all(a >= b for a, b in zip(prior, values))
                       for prior, prior_hand in skyline):
                skyline.append((values, hand))
                selected.append(group[values, hand])
    return sorted(selected), True


def analyze(battle: Battle, *, max_states: int = 100000, max_outcomes: int = 4096,
            seconds: float = 10.0) -> Json:
    # AI_NOTE: end_turnは実行せず全nodeを停止可能とする。深さ制限や評価点のbeamで合法な候補を落とさない。
    integer(max_states, 'max_states', 1, 10000000)
    integer(max_outcomes, 'max_outcomes', 1, 10000)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 600:
        raise ValueError('secondsは0より大きく600以下です')
    validate_scope(battle)
    started = perf_counter()
    root = TurnBattle(battle.state, battle.cards, record=False)
    root.deadline = started + seconds
    positions = Positions(root)
    positions.encode(root.state)
    actions, probabilities, tapes = Pool(), Pool(), Pool()
    # Each choice is [source node, action ID, first outcome, end outcome]; outcomes are [node, probability ID, tape ID].
    choices: list[tuple[int, int, int, int]] = []
    outcomes: list[tuple[int, int, int]] = []
    witnesses: list[tuple[int, int, int] | None] = [None]
    expanded: list[int] = []
    pending = [0]
    cutoffs: set[str] = set()
    duplicates = 0
    while pending and not cutoffs:
        index = pending.pop()
        current = positions.decode(index)
        for action in current.legal_actions():
            if action['type'] == 'end_turn':
                continue
            work: list[tuple[tuple[int, ...], Fraction]] = [((), Fraction(1))]
            branches: list[tuple[TurnBattle, Fraction, tuple[int, ...]]] = []
            try:
                while work:
                    if perf_counter() >= root.deadline:
                        raise Limit('time')
                    draws, probability = work.pop()
                    try:
                        child = current.branch(action, draws)
                    except Chance as chance:
                        if len(branches) + len(work) + chance.size > max_outcomes or len(draws) >= 128:
                            raise Limit('chance outcomes')
                        work.extend((draws+(i,), probability/chance.size) for i in reversed(range(chance.size)))
                    else:
                        branches.append((child, probability, draws))
                # All chance outcomes are committed together; an incomplete distribution is never exported.
                branch_keys = [positions.key(child.state) for child, _, _ in branches]
                fresh_keys = {key for key in branch_keys if key not in positions.positions.ids}
                if len(positions.positions.values) + len(fresh_keys) > max_states:
                    raise Limit('states')
            except Limit as reason:
                cutoffs.add(str(reason))
                break
            action_id = actions.add(freeze(action), action)
            offset = len(outcomes)
            for (_, probability, draws), key in zip(branches, branch_keys):
                count = len(positions.positions.values)
                target = positions.positions.add(key)
                fresh = target == count
                tape = tapes.add(draws)
                if fresh:
                    witnesses.append((index, action_id, tape))
                    pending.append(target)
                else:
                    duplicates += 1
                outcomes.append((target, probabilities.add(str(probability)), tape))
            choices.append((index, action_id, offset, len(outcomes)))
        else:
            expanded.append(index)
    search_elapsed = perf_counter()-started
    candidates, frontier_complete = pareto(positions, root.deadline)
    if not frontier_complete:
        cutoffs.add('frontier time')
    peak, method = peak_memory()
    return {'version': 1, 'strategy': 'current-turn-frontier', 'complete': not cutoffs,
            'enumeration_complete': not pending and len(expanded) == len(positions.positions.values),
            'frontier_complete': frontier_complete, 'cutoffs': sorted(cutoffs),
            'scope': 'Own current turn before end-turn effects. Every node allows STOP. Uniform chance outcomes, not selectable actions.',
            'dominance_scope': 'Endpoint board stats and own resources, with exact remaining-hand containment and identical ordered board traits; not future-game dominance. Full decision graph is unpruned.',
            'record': root.export(), 'root': 0, **positions.export(), 'actions': actions.values,
            'probabilities': probabilities.values, 'draws': tapes.values, 'choices': choices,
            'outcomes': outcomes, 'witnesses': witnesses, 'expanded': expanded, 'candidates': candidates,
            'stats': {'states': len(positions.positions.values), 'choices': len(choices), 'outcomes': len(outcomes),
                      'duplicates': duplicates, 'candidates': len(candidates), 'search_ms': search_elapsed*1000,
                      'elapsed_ms': (perf_counter()-started)*1000, 'peak_rss_bytes': peak, 'memory_method': method,
                      'memory_scope': 'whole process peak', 'max_states': max_states, 'max_outcomes': max_outcomes,
                      'seconds': seconds}}


def state_at(result: Json, index: int) -> Json:
    # AI_NOTE: 共有表の番号を復元し、呼出側が編集しても解析結果に波及させない。
    integer(index, 'node', 0, len(result['positions'])-1)
    state: Json = copy.deepcopy(result['record']['initial'])
    winner, next_id, first, second, knowledge = result['positions'][index]
    state.update(winner=winner, next_id=next_id)
    for owner, player_id in enumerate((first, second)):
        meta, board, hand = result['players'][player_id]
        player = copy.deepcopy(result['metadata'][meta])
        player['deck'] = state['players'][owner]['deck']
        for name, zone in (('board', board), ('hand', hand)):
            player[name] = [copy.deepcopy(result['entities'][e]) for e in result['zones'][zone]]
        state['players'][owner] = player
    if 'deck_knowledge' in state:
        state['deck_knowledge'] = copy.deepcopy(result['metadata'][knowledge])
    return state


def witness_steps(result: Json, index: int) -> list[Json]:
    # AI_NOTE: 最初に到達した合法経路を返す。抽選テープは条件付き再生用で、選択可能な運ではない。
    integer(index, 'node', 0, len(result['positions'])-1)
    steps = []
    while index:
        parent, action, tape = result['witnesses'][index]
        steps.append({'action': copy.deepcopy(result['actions'][action]), 'draws': list(result['draws'][tape])})
        index = parent
    return list(reversed(steps))


def main() -> None:
    # AI_NOTE: 同じ公開入口を別プロセスで実行し、全候補と計測値を再利用可能なJSONへ保存する。
    parser = argparse.ArgumentParser(description='自分の1ターン内の全候補・条件付き抽選グラフ')
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-states', type=int, default=100000)
    parser.add_argument('--max-outcomes', type=int, default=4096)
    parser.add_argument('--seconds', type=float, default=10)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    case = next((c for c in cases if c['id'] == args.case), None)
    if case is None or args.output.exists():
        parser.error('ケースIDと未使用の出力ディレクトリを指定してください')
    result = analyze(Battle(case['state'], case['cards']), max_states=args.max_states,
                     max_outcomes=args.max_outcomes, seconds=args.seconds)
    args.output.mkdir(parents=True)
    with (args.output/'graph.json').open('w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, separators=(',', ':'))
    report = {k: result[k] for k in ('complete', 'enumeration_complete', 'frontier_complete', 'cutoffs', 'scope', 'dominance_scope', 'stats')}
    report['case_id'] = case['id']
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
