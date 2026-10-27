"""Combat combinations in an explicitly ability-free, current-turn model.

No intermediate score/beam pruning. Endpoint dominance describes the declared
board/resource criteria, not strategic dominance against future card effects.
"""
from __future__ import annotations

from collections import deque
from functools import lru_cache
from itertools import combinations
from time import perf_counter
from typing import Callable, Iterator, NamedTuple

from svdeck.battle_env.battle import Battle, Json, integer
from svdeck.battle_env.battle_rules import definition


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
def board_dominates(larger: tuple[Body | None, ...], smaller: tuple[Body | None, ...],
                    continuation: bool = False, preserve_damage: bool = False) -> bool:
    # AI_NOTE: 個体を重複利用せず対応付ける。貪欲に一体ずつ選ぶと正しい対応を見逃すため全組合せで確認。
    supplies = [b for b in larger if b]
    demands = [b for b in smaller if b]
    if len(supplies) < len(demands):
        return False
    choices = [sum(1 << i for i, a in enumerate(supplies) if a.evolved == b.evolved and
                   a.attack >= b.attack and a.health >= b.health and a.max_health >= b.max_health and
                   (not continuation or (a.attacks <= b.attacks and a.ready >= b.ready)) and
                   (not preserve_damage or b.attacks > 0 or a.attack == b.attack))
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


def dominates(a: Position, b: Position, continuation: bool = False) -> bool:
    # AI_NOTE: 大型一体と小型複数やEPとSEPを合計点で潰さず、個体同士の対応がある場合だけ除く。
    if a.win or b.win:
        return a.win
    # AI_NOTE: 超進化の最後の一撃を残す場面では、打点増加で先に倒してしまう取り方も別候補にする。
    preserve_damage = continuation and any(body and body.evolved == 2 and not body.attacks
                                          for body in (*a.own, *b.own))
    return (a.face <= b.face and a.ep >= b.ep and a.sep >= b.sep and
            (not continuation or (a.used == b.used and a.enemy == b.enemy)) and
            board_dominates(a.own, b.own, continuation, preserve_damage) and board_dominates(b.enemy, a.enemy))


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


def frontier(states: list[Position], continuation: bool = False) -> list[int]:
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
            if dominates(states[j], state, continuation) and (j < i or not dominates(state, states[j], continuation)):
                beaten = True
                break
            possible ^= bit
        if not beaten:
            kept.append(i)
    return kept


def target_combinations(state: Position, target_index: int, own_ids: tuple[str, ...],
                        enemy_ids: tuple[str, ...]) -> Iterator[tuple[Position, list[Json]]]:
    # AI_NOTE: 敵一体への攻撃を組合せで生成。倒す場合だけ最後の一体を区別し、途中の並べ替えを省く。
    yield state, []
    target = state.enemy[target_index]
    if target is None or state.win:
        return
    available = [i for i, b in enumerate(state.own) if b and b.attack > 0 and
                 not b.attacks and (b.ready or b.evolved)]
    seen: set[Position] = {canonical(state)}
    for size in range(1, len(available)+1):
        for selected in combinations(available, size):
            bodies = [state.own[i] for i in selected]
            damage = sum(b.attack for b in bodies if b)
            # A lethal prefix must not be followed by another attack on the removed target.
            lasts = [i for i in selected if (b := state.own[i]) is not None and
                     damage-b.attack < target.health] if damage >= target.health else [selected[-1]]
            for last in lasts:
                own, enemy = list(state.own), list(state.enemy)
                order = [i for i in selected if i != last] + [last]
                for i in order:
                    body = own[i]
                    assert body is not None
                    health = body.health-(0 if body.evolved == 2 else target.attack)
                    own[i] = body._replace(health=health, attacks=1) if health > 0 else None
                enemy[target_index] = target._replace(health=target.health-damage) if damage < target.health else None
                last_body = state.own[last]
                face = max(0, state.face-int(damage >= target.health and last_body is not None and last_body.evolved == 2))
                child = state._replace(own=tuple(own), enemy=tuple(enemy), face=face, win=face == 0)
                key = canonical(child)
                if key in seen:
                    continue
                seen.add(key)
                yield child, [{'type': 'attack', 'source': own_ids[i], 'target': enemy_ids[target_index]} for i in order]


def grouped_search(initial: Position, owner: int, turn: int, mode: str,
                   own_ids: tuple[str, ...], enemy_ids: tuple[str, ...], max_states: int | None
                   ) -> tuple[dict[Position, tuple[Position, list[Json]]], bool, Json]:
    # AI_NOTE: 残り攻撃者の集合をキーに敵一体分の取り方を再利用し、完成した盤面だけを蓄積する。
    variants: list[tuple[Position, list[Json], int | None, Json | None]] = [(initial, [], None, None)]
    for child, action in successors(initial, owner, turn, mode, own_ids, enemy_ids):
        if action['type'] == 'attack':
            continue
        variants.append((child, [action], None, None))
        # A stronger early hit can steal another super body's finishing ping: keep late evolution too.
        index = own_ids.index(action['source'])
        body = initial.own[index]
        if body and body.ready and not body.attacks and any(b and b.evolved == 2 and not b.attacks for b in initial.own):
            variants.append((initial._replace(ep=child.ep, sep=child.sep, used=True), [], index, action))
    order = sorted(range(len(initial.enemy)), key=lambda i: b.health if (b := initial.enemy[i]) else 0)
    results: dict[Position, tuple[Position, list[Json]]] = {}
    complete, nodes, duplicates, pruned, allocations = True, 0, 0, 0, 0
    id_index = {ident: i for i, ident in enumerate(own_ids)}

    def retain(state: Position, actions: list[Json]) -> None:
        # AI_NOTE: 勝利後に計算上続いた操作は切り、実行可能な勝利直後の状態に戻して記録する。
        nonlocal complete, duplicates, allocations
        allocations += 1
        if state.win:
            actual = initial
            witness = []
            for action in actions:
                actual = next(child for child, legal in successors(actual, owner, turn, mode, own_ids, enemy_ids) if legal == action)
                witness.append(action)
                if actual.win:
                    break
            state, actions = actual, witness
        key = canonical(endpoint(state))
        if key in results:
            duplicates += 1
            return
        if max_states is not None and len(results) >= max_states:
            complete = False
            return
        results[key] = (state, actions)

    for root, opening, late_index, late_action in variants:
        if not complete or any(key.win for key in results):
            break
        mask = sum(1 << i for i, b in enumerate(root.own) if b and not b.attacks and
                   b.attack > 0 and (b.ready or b.evolved))
        cache: dict[tuple[int, int], list[tuple[Position, list[Json], int]]] = {}

        def choices(target: int, available: int) -> list[tuple[Position, list[Json], int]]:
            # AI_NOTE: 既に別の敵へ割り当てた個体は比較から外し、未使用の同じ部分問題を一度だけ解く。
            nonlocal pruned
            cache_key = (target, available)
            if cache_key in cache:
                return cache[cache_key]
            local = root._replace(own=tuple(b if available & (1 << i) else None for i, b in enumerate(root.own)))
            options = list(target_combinations(local, target, own_ids, enemy_ids))
            if late_index is None:
                groups: dict[tuple[Body | None, ...], list[int]] = {}
                for i, (child, _) in enumerate(options):
                    groups.setdefault(child.enemy, []).append(i)
                kept = [indices[j] for indices in groups.values() for j in frontier(
                    [canonical(options[i][0]) for i in indices], continuation=True)]
                pruned += len(options)-len(kept)
                options = [options[i] for i in kept]
            cache[cache_key] = [(child, actions, sum(1 << id_index[a['source']] for a in actions)) for child, actions in options]
            return cache[cache_key]

        def visit(depth: int, available: int, state: Position, actions: list[Json], late_done: bool) -> None:
            # AI_NOTE: 攻撃先ごとの割当を深さ優先で合成し、巨大な途中盤面の一覧を保持しない。
            nonlocal nodes
            if not complete:
                return
            if state.win:
                retain(state, actions)
                return
            if depth == len(order):
                own = list(state.own)
                face = state.face
                for i, body in enumerate(own):
                    if body and not body.attacks and body.ready and body.attack > 0:
                        face = max(0, face-body.attack)
                        own[i] = body._replace(attacks=1)
                        actions = actions+[{'type': 'attack', 'source': own_ids[i], 'target': f'leader:{1-owner}'}]
                if late_index is not None and not late_done:
                    body = own[late_index]
                    if body is None:
                        return
                    assert late_action is not None
                    amount = 2 if late_action['type'] == 'evolve' else 3
                    own[late_index] = body._replace(attack=body.attack+amount, health=body.health+amount,
                        max_health=body.max_health+amount, evolved=amount-1)
                    actions = actions+[late_action]
                retain(state._replace(own=tuple(own), face=face, win=face == 0), actions)
                return
            target = order[depth]
            for local, attacks, spent in choices(target, available):
                nodes += 1
                own, enemy = list(state.own), list(state.enemy)
                for i in range(len(own)):
                    if spent & (1 << i):
                        own[i] = local.own[i]
                enemy[target] = local.enemy[target]
                child_done = late_done
                if late_index is not None and not late_done and spent & (1 << late_index):
                    body = own[late_index]
                    if body is None:
                        continue
                    assert late_action is not None
                    amount = 2 if late_action['type'] == 'evolve' else 3
                    own[late_index] = body._replace(attack=body.attack+amount, health=body.health+amount,
                        max_health=body.max_health+amount, evolved=amount-1)
                    # Its post-attack evolution can be placed after this independent target's other attacks.
                    attacks = attacks+[late_action]
                    child_done = True
                face = max(0, state.face-(root.face-local.face))
                visit(depth+1, available & ~spent, state._replace(own=tuple(own), enemy=tuple(enemy), face=face,
                      win=face == 0), actions+attacks, child_done)
                if not complete:
                    break
        visit(0, mask, root, opening, False)
    return results, complete, {'states': len(results), 'transitions': nodes, 'duplicates': duplicates,
                              'group_pruned': pruned, 'allocations': allocations,
                              'budget_unit': 'unique completed endpoints'}


def analyze(battle: Battle, mode: str = 'super', max_states: int | None = 50000,
            strategy: str = 'grouped') -> Json:
    # AI_NOTE: 件数上限は結果の完全性フラグに反映する。上限内の候補を全候補と偽らない。
    if mode not in ('attack', 'evolve', 'super'):
        raise ValueError('探索範囲は attack / evolve / super です')
    if strategy not in ('grouped', 'exhaustive'):
        raise ValueError('探索方式は grouped / exhaustive です')
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
    grouped: dict[Position, tuple[Position, list[Json]]] = {}
    group_stats: Json = {}
    if strategy == 'grouped':
        grouped, complete, group_stats = grouped_search(initial, owner, own['turn'], mode, own_ids, enemy_ids, max_states)
    parents: dict[Position, tuple[Position, Json] | None] = {canonical(initial): None}
    queue = deque([initial] if strategy == 'exhaustive' else [])
    endpoints: dict[Position, Position] = {canonical(endpoint(initial)): initial}
    if strategy == 'exhaustive':
        complete = True
    transitions, duplicates = 0, 0
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
    if strategy == 'grouped':
        endpoints = {key: value[0] for key, value in grouped.items()}
    states = list(endpoints)
    kept = frontier(states)
    candidates: list[Json] = []
    for index in kept:
        representative = endpoints[states[index]]
        end = endpoint(representative)
        cursor = canonical(representative)
        actions = []
        while strategy == 'exhaustive' and (parent := parents[cursor]) is not None:
            cursor, action = parent
            actions.append(action)
        actions.reverse()
        if strategy == 'grouped':
            actions = grouped[states[index]][1]
        boards = [[{'id': source['id'], 'name': source['name'], 'attack': b.attack,
                    'health': b.health, 'max_health': b.max_health, 'evolved': b.evolved}
                   for source, b in zip(p['board'], bodies) if b]
                  for p, bodies in ((own, end.own), (enemy, end.enemy))]
        candidates.append({'actions': actions, 'own_board': boards[0], 'enemy_board': boards[1],
                           'enemy_health': end.face, 'ep': end.ep, 'sep': end.sep, 'win': end.win})
    candidates.sort(key=lambda c: (not c['win'], c['enemy_health'], -len(c['own_board']), len(c['actions'])))
    return {'mode': mode, 'strategy': strategy, 'complete': complete, 'record': projected.export(), 'candidates': candidates,
            'stats': {'states': len(parents), 'transitions': transitions, 'duplicates': duplicates,
                      'endpoints': len(states), 'dominated': len(states)-len(kept),
                      'search_ms': round(search_ms, 3), 'elapsed_ms': round((perf_counter()-started)*1000, 3),
                      **group_stats}}
