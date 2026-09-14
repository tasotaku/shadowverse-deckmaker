"""Exact-state combat enumeration in an explicitly ability-free, current-turn model.

No intermediate score/beam pruning. Endpoint dominance describes the declared
board/resource criteria, not strategic dominance against future card effects.
"""
from __future__ import annotations

from collections import deque
from functools import lru_cache
from time import perf_counter
from typing import Callable, Iterator, NamedTuple

from .battle import Battle, Json, integer
from .battle_rules import definition


class Body(NamedTuple):
    attack: int
    health: int
    max_health: int
    evolved: int
    attacks: int
    ready: bool


class Position(NamedTuple):
    own: tuple[Body | None, ...]
    enemy: tuple[Body | None, ...]
    face: int
    ep: int
    sep: int
    used: bool
    win: bool


def project(battle: Battle) -> Battle:
    # AI_NOTE: 元の対戦を変更せず、能力が復活しない専用カード定義で再生可能な検証状態を作る。
    cards: dict[str, Json] = {}
    players: list[Json] = []
    for owner, player in enumerate(battle.state['players']):
        projected = {k: player[k] for k in ('health', 'max_health', 'turn', 'ep', 'sep', 'evolved_this_turn')}
        projected['board'] = []
        for index, entity in enumerate(player['board']):
            if definition(battle, entity)['kind'] != 'follower':
                continue
            cid = f'combat-{owner}-{index}'
            cards[cid] = {'card_id': cid, 'kind': 'follower', 'name': entity['name'],
                          'cost': entity['cost'], 'attack': entity['attack'], 'health': entity['max_health'],
                          'text': '能力なしの検証用。基本の進化・超進化だけを適用。', 'synthetic': True}
            body = {k: entity[k] for k in ('id', 'attack', 'health', 'max_health', 'evolved', 'attacks', 'entered_turn')}
            projected['board'].append({**body, 'card_id': cid, 'keywords': []})
        players.append(projected)
    return Battle({'players': players, 'active_player': battle.state['active_player'],
                   'winner': battle.state['winner']}, cards)


def position(battle: Battle) -> Position:
    # AI_NOTE: 個体の位置を固定し、死んだ個体はNoneにすることで攻撃順の違いを同じキーで照合する。
    owner = battle.state['active_player']
    own, enemy = (battle.state['players'][i] for i in (owner, 1-owner))
    boards = [tuple(Body(e['attack'], e['health'], e['max_health'], e['evolved'], e['attacks'],
                         e['entered_turn'] < p['turn']) for e in p['board']) for p in (own, enemy)]
    return Position(boards[0], boards[1], enemy['health'], own['ep'], own['sep'],
                    own['evolved_this_turn'], battle.state['winner'] == owner)


def successors(state: Position, owner: int, turn: int, mode: str,
               own_ids: tuple[str, ...], enemy_ids: tuple[str, ...]) -> Iterator[tuple[Position, Json]]:
    # AI_NOTE: 進化前後の攻撃順をどちらも生成する。攻撃済みかと、顔を殴れるかは別の条件。
    if state.win:
        return
    for i, body in enumerate(state.own):
        if body is None:
            continue
        if not body.attacks and (body.ready or body.evolved):
            if body.ready:
                own = list(state.own)
                own[i] = body._replace(attacks=1)
                face = max(0, state.face-body.attack)
                yield state._replace(own=tuple(own), face=face, win=face == 0), {
                    'type': 'attack', 'source': own_ids[i], 'target': f'leader:{1-owner}'}
            for j, target in enumerate(state.enemy):
                if target is None:
                    continue
                own, enemy = list(state.own), list(state.enemy)
                health = body.health-(0 if body.evolved == 2 else target.attack)
                own[i] = body._replace(health=health, attacks=1) if health > 0 else None
                health = target.health-body.attack
                enemy[j] = target._replace(health=health) if health > 0 else None
                face = max(0, state.face-int(health <= 0 and body.evolved == 2))
                yield state._replace(own=tuple(own), enemy=tuple(enemy), face=face, win=face == 0), {
                    'type': 'attack', 'source': own_ids[i], 'target': enemy_ids[j]}
        if body.evolved or state.used or mode == 'attack':
            continue
        for kind, resource, threshold, evolved, amount in (
                ('evolve', state.ep, 5-owner, 1, 2), ('super_evolve', state.sep, 7-owner, 2, 3)):
            if resource <= 0 or turn < threshold or (kind == 'super_evolve' and mode != 'super'):
                continue
            own = list(state.own)
            own[i] = body._replace(attack=body.attack+amount, health=body.health+amount,
                                   max_health=body.max_health+amount, evolved=evolved)
            yield state._replace(own=tuple(own), used=True, ep=state.ep-int(evolved == 1),
                                 sep=state.sep-int(evolved == 2)), {'type': kind, 'source': own_ids[i]}


def endpoint(state: Position) -> Position:
    # AI_NOTE: ここで攻撃を止める結果の比較だけでは残り攻撃権を使わない。探索中のキーからは除かない。
    boards = [tuple(b._replace(attacks=0, ready=False) if b else None for b in board)
              for board in (state.own, state.enemy)]
    return state._replace(own=boards[0], enemy=boards[1], used=False)


def canonical(state: Position) -> Position:
    # AI_NOTE: 能力なしでは同じ数値の個体の入替えは同一局面。再生する個体IDは代表経路側に保持する。
    return state._replace(own=tuple(sorted(b for b in state.own if b)),
                          enemy=tuple(sorted(b for b in state.enemy if b)))


@lru_cache(maxsize=100000)
def board_dominates(larger: tuple[Body | None, ...], smaller: tuple[Body | None, ...]) -> bool:
    # AI_NOTE: 個体を重複利用せず対応付ける。貪欲に一体ずつ選ぶと正しい対応を見逃すため全組合せで確認。
    supplies = [b for b in larger if b]
    demands = [b for b in smaller if b]
    if len(supplies) < len(demands):
        return False
    choices = [sum(1 << i for i, a in enumerate(supplies) if a.evolved == b.evolved and
                   a.attack >= b.attack and a.health >= b.health and a.max_health >= b.max_health)
               for b in demands]
    choices.sort(key=int.bit_count)
    available = {0}
    for options in choices:
        following: set[int] = set()
        for used in available:
            remaining = options & ~used
            while remaining:
                bit = remaining & -remaining
                following.add(used | bit)
                remaining ^= bit
        if not following:
            return False
        available = following
    return True


def dominates(a: Position, b: Position) -> bool:
    # AI_NOTE: 大型一体と小型複数やEPとSEPを合計点で潰さず、個体同士の対応がある場合だけ除く。
    if a.win or b.win:
        return a.win
    return (a.face <= b.face and a.ep >= b.ep and a.sep >= b.sep and
            board_dominates(a.own, b.own) and board_dominates(b.enemy, a.enemy))


def masks(states: list[Position], value: Callable[[Position], int], cumulative: bool = False) -> dict[int, int]:
    # AI_NOTE: 条件を満たす候補の集合を整数のビットで持ち、数万件同士のPythonループ比較を避ける。
    groups: dict[int, bytearray] = {}
    size = (len(states)+7)//8
    for i, state in enumerate(states):
        v = value(state)
        if v not in groups:
            groups[v] = bytearray(size)
        groups[v][i//8] |= 1 << (i % 8)
    result, combined = {}, 0
    for v in sorted(groups, reverse=True):
        bits = int.from_bytes(groups[v], 'little')
        combined = combined | bits if cumulative else bits
        result[v] = combined
    return result


def frontier(states: list[Position]) -> list[int]:
    # AI_NOTE: 数値の必要条件を集合演算で絞り、最後に個体同士の対応を厳密に検査する。近似枝刈りはしない。
    if not states:
        return []
    for i, state in enumerate(states):
        if state.win:
            return [i]
    vectors = []
    for state in states:
        values = [-state.face, state.ep, state.sep]
        for side, sign in ((state.own, 1), (state.enemy, -1)):
            for evolved in range(3):
                group = [b for b in side if b and b.evolved == evolved]
                for prop in ('health', 'attack', 'max_health'):
                    ordered = sorted((int(getattr(b, prop)) for b in group), reverse=True)
                    values.extend(sign * v for v in ordered + [0]*(5-len(ordered)))
        vectors.append(tuple(values))
    indexed = {s: i for i, s in enumerate(states)}
    criteria: list[tuple[int, dict[int, int]]] = []
    for column in range(len(vectors[0])):
        def coordinate(s: Position, column: int = column) -> int:
            # AI_NOTE: 同じ進化状態の数値を大きい順に比較するのは必要条件だけ。対応付けの代用にはしない。
            return vectors[indexed[s]][column]
        index = masks(states, coordinate, True)
        if len(index) > 1:
            criteria.append((column, index))
    criteria.sort(key=lambda entry: len(entry[1]), reverse=True)
    all_bits = (1 << len(states))-1
    kept = []
    for i, state in enumerate(states):
        possible = all_bits ^ (1 << i)
        for column, index in criteria:
            possible &= index[vectors[i][column]]
            if not possible:
                break
        beaten = False
        while possible:
            bit = possible & -possible
            j = bit.bit_length()-1
            if dominates(states[j], state):
                beaten = True
                break
            possible ^= bit
        if not beaten:
            kept.append(i)
    return kept


def analyze(battle: Battle, mode: str = 'super', max_states: int | None = 50000) -> Json:
    # AI_NOTE: 件数上限は結果の完全性フラグに反映する。上限内の候補を全候補と偽らない。
    if mode not in ('attack', 'evolve', 'super'):
        raise ValueError('探索範囲は attack / evolve / super です')
    if max_states is not None:
        integer(max_states, 'max_states', 1, 200000)
    if battle.state['winner'] is not None or any(p['health'] <= 0 for p in battle.state['players']):
        raise ValueError('対戦中の盤面を選んでください')
    started = perf_counter()
    projected = project(battle)
    owner = projected.state['active_player']
    own, enemy = (projected.state['players'][i] for i in (owner, 1-owner))
    own_ids, enemy_ids = (tuple(e['id'] for e in p['board']) for p in (own, enemy))
    initial = position(projected)
    parents: dict[Position, tuple[Position, Json] | None] = {canonical(initial): None}
    queue = deque([initial])
    endpoints: dict[Position, Position] = {canonical(endpoint(initial)): initial}
    complete, transitions, duplicates = True, 0, 0
    while queue and complete:
        current = queue.popleft()
        for child, action in successors(current, owner, own['turn'], mode, own_ids, enemy_ids):
            transitions += 1
            child_key = canonical(child)
            if child_key in parents:
                duplicates += 1
                continue
            if max_states is not None and len(parents) >= max_states:
                complete = False
                break
            parents[child_key] = (canonical(current), action)
            queue.append(child)
            endpoints.setdefault(canonical(endpoint(child)), child)
    search_ms = (perf_counter()-started)*1000
    states = list(endpoints)
    kept = frontier(states)
    candidates: list[Json] = []
    for index in kept:
        representative = endpoints[states[index]]
        end = endpoint(representative)
        cursor = canonical(representative)
        actions = []
        while (parent := parents[cursor]) is not None:
            cursor, action = parent
            actions.append(action)
        actions.reverse()
        boards = [[{'id': source['id'], 'name': source['name'], 'attack': b.attack,
                    'health': b.health, 'max_health': b.max_health, 'evolved': b.evolved}
                   for source, b in zip(p['board'], bodies) if b]
                  for p, bodies in ((own, end.own), (enemy, end.enemy))]
        candidates.append({'actions': actions, 'own_board': boards[0], 'enemy_board': boards[1],
                           'enemy_health': end.face, 'ep': end.ep, 'sep': end.sep, 'win': end.win})
    candidates.sort(key=lambda c: (not c['win'], c['enemy_health'], -len(c['own_board']), len(c['actions'])))
    return {'mode': mode, 'complete': complete, 'record': projected.export(), 'candidates': candidates,
            'stats': {'states': len(parents), 'transitions': transitions, 'duplicates': duplicates,
                      'endpoints': len(states), 'dominated': len(states)-len(kept),
                      'search_ms': round(search_ms, 3), 'elapsed_ms': round((perf_counter()-started)*1000, 3)}}
