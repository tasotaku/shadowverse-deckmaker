"""Structural response hints and exact availability under a uniform hidden-hand prior.

Roles describe possible uses, not currently legal actions. Their paths retain timing,
conditions and generated-card dependencies; the battle engine decides feasibility.
Availability is exact for the supplied card requirements only. It does not make a
response score, hidden discounts, random effects or an incomplete search exact.
"""
from __future__ import annotations

import copy
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from math import comb
from typing import Any

from svdeck.battle_env.battle_rules import PHASES

Json = dict[str, Any]
ENEMY_TARGETS = {'chosen_enemy', 'chosen_any_enemy', 'random_enemy', 'all_enemy',
                 'all_enemy_characters', 'all'}
AREA_TARGETS = {'all_enemy', 'all_enemy_characters', 'all'}
FACE_TARGETS = {'enemy_leader', 'chosen_any_enemy', 'all_enemy_characters', 'all_leaders'}
DEFENSE_KEYWORDS = {'守護', 'バリア', '潜伏', 'オーラ', '威圧', '破壊耐性'}
SUPPORT_OPS = {'discard', 'pp', 'ep', 'cost', 'combo', 'necro', 'evolve', 'ramp',
               'generate', 'summon', 'deck_summon', 'reanimate', 'bounce', 'countdown'}
KNOWN_OPS = SUPPORT_OPS | {'damage', 'heal', 'draw', 'buff', 'grant', 'destroy',
                           'banish', 'if', 'repeat', 'remove_keywords', 'leader_max',
                           'shield', 'split_damage', 'copy_banish', 'crest'}


def keyword_roles(keywords: list[str]) -> set[str]:
    # AI_NOTE: 能力名から可能な用途を分類し、攻撃可能かどうかは実行時の盤面へ委ねる。
    result: set[str] = set()
    if set(keywords) & DEFENSE_KEYWORDS:
        result.add('defense')
    if set(keywords) & {'疾走', '突進', '必殺'}:
        result.add('remove_one')
    if '疾走' in keywords:
        result.add('damage')
    if 'ドレイン' in keywords:
        result.add('heal')
    return result


def effect_roles(effect: Json, repetitions: int, reversed_owner: bool) -> set[str]:
    # AI_NOTE: 選択・複数・全体を対象構造から区別し、自己へのダメージを打点へ混ぜない。
    op, target = effect.get('op'), effect.get('target', 'self')
    result: set[str] = set()
    enemy_target = target in ENEMY_TARGETS if not reversed_owner else target in {'self', 'all_ally'}
    face_target = target in FACE_TARGETS if not reversed_owner else target in {'own_leader', 'all_leaders'}
    negative_health = op == 'buff' and effect.get('health', 0) < 0
    if enemy_target and (op in {'damage', 'destroy', 'banish', 'bounce', 'copy_banish', 'split_damage'} or negative_health):
        if op == 'split_damage':
            result.add('remove_multi')
        elif target in AREA_TARGETS or (reversed_owner and target == 'all_ally'):
            result.add('remove_all')
        elif effect.get('count', 1) * repetitions > 1:
            result.add('remove_multi')
        else:
            result.add('remove_one')
    if op == 'damage' and face_target:
        result.add('damage')
    if op == 'heal' and target == ('enemy_leader' if reversed_owner else 'own_leader'):
        result.add('heal')
    if op in {'draw', 'generate', 'ramp', 'pp', 'ep', 'cost'}:
        result.add('resource')
    if op in {'summon', 'deck_summon', 'reanimate', 'copy_banish'}:
        result.add('develop')
    if op == 'shield':
        result.add('defense')
    if op in {'buff', 'grant'} and not enemy_target:
        result.update(keyword_roles(effect.get('keywords', [])))
        if op == 'buff' and (effect.get('attack', 0) > 0 or effect.get('health', 0) > 0):
            result.add('develop')
    if op in SUPPORT_OPS or op in {'buff', 'grant', 'remove_keywords', 'leader_max', 'crest'}:
        result.add('support')
    if op not in KNOWN_OPS:
        result.add('unknown')
    return result


def card_roles(cards: dict[str, Json]) -> dict[str, Json]:
    """Return role unions plus explicit paths; no card definitions are mutated.

    Each path keeps the original effect fields and adds phase/form/mode/conditions,
    roles, support, source_card_id and card_ids (referenced-card dependencies).
    A phase containing ``generate`` needs a later legal play. A summon inherits no
    fanfare. Cyclic references remain as dependency edges instead of expanding forever.
    """
    # AI_NOTE: タグは探索順のヒントだけにし、条件を消した単一能力として実行させない。
    profiles: dict[str, Json] = {}
    for root_id, root in cards.items():
        paths: list[Json] = []

        def append_path(effect: Json, context: Json, repetitions: int = 1) -> None:
            # AI_NOTE: 元の対象数・ランダム指定・付与と解除を残し、説明で同時発動を約束しない。
            roles = effect_roles(effect, repetitions, bool(context.get('reversed_owner')))
            if effect['op'] == 'keyword':
                roles = keyword_roles(effect.get('keywords', []))
            elif effect['op'] == 'body':
                roles = {'develop'}
            path = {**copy.deepcopy(effect), **copy.deepcopy(context), 'roles': sorted(roles),
                    'support': [effect['op']] if effect['op'] in SUPPORT_OPS else [],
                    'repetitions': repetitions}
            path.setdefault('target', 'self')
            if effect['op'] == 'remove_keywords':
                path['removes_roles'] = sorted(keyword_roles(effect.get('keywords', [])))
            paths.append(path)

        def walk_effects(effects: list[Json], context: Json, ancestry: frozenset[str],
                         repetitions: int = 1) -> None:
            # AI_NOTE: 入れ子の条件と繰返しを継承し、生成先・クレストは所有者と発動経路を保持する。
            for effect in effects:
                current = copy.deepcopy(context)
                if effect.get('condition') is not None:
                    current['conditions'].append(copy.deepcopy(effect['condition']))
                op = effect['op']
                append_path(effect, current, repetitions)
                if 'effects' in effect:
                    nested = repetitions * effect.get('count', 1) if op == 'repeat' else repetitions
                    if op == 'necro':
                        current['conditions'].append({'necro': effect.get('amount', 0)})
                    walk_effects(effect['effects'], current, ancestry, nested)
                if op in {'generate', 'summon'}:
                    referenced = str(effect['card_id'])
                    current['card_ids'].append(referenced)
                    current['phase'] += '.' + op + '.'
                    current['conditions'].append({'requires': op, 'card_id': referenced,
                                                  'count': effect.get('count', 1)})
                    if referenced in cards and referenced not in ancestry:
                        summoned = copy.deepcopy(cards[referenced])
                        if op == 'summon':
                            modifiers = effect.get('modifiers', {})
                            summoned['keywords'] = list(dict.fromkeys(summoned.get('keywords', []) + modifiers.get('keywords', [])))
                            if modifiers.get('lost_last_words'):
                                summoned.pop('last_words', None)
                        walk_card(referenced, summoned, current, ancestry | {referenced}, op == 'summon')
                if op == 'crest':
                    current['phase'] += '.crest'
                    if effect.get('target') == 'enemy_leader':
                        current['reversed_owner'] = not current.get('reversed_owner', False)
                    walk_triggers(effect.get('crest', {}).get('triggers', []), current, ancestry)

        def walk_triggers(triggers: list[Json], context: Json, ancestry: frozenset[str]) -> None:
            # AI_NOTE: 常在効果のイベント・対象条件を経路へ残し、今すぐ発動する能力と分ける。
            for trigger in triggers:
                current = copy.deepcopy(context)
                current['phase'] += '.' + trigger['event']
                current['conditions'].append({key: copy.deepcopy(value) for key, value in trigger.items() if key != 'effects'})
                walk_effects(trigger.get('effects', []), current, ancestry)

        def walk_card(card_id: str, card: Json, context: Json, ancestry: frozenset[str],
                      summoned: bool = False) -> None:
            # AI_NOTE: 別形態は本体の能力を継承せず、召喚ではファンファーレを発動扱いにしない。
            current = {**copy.deepcopy(context), 'source_card_id': card_id}
            entry = {**current, 'phase': current['phase'] + 'play'}
            if card.get('kind') == 'follower':
                append_path({'op': 'body'}, entry)
            if card.get('keywords'):
                append_path({'op': 'keyword', 'keywords': card['keywords']}, entry)
            for phase in PHASES:
                if summoned and phase in {'fanfare', 'effects', 'enhance_effects', 'on_discard'}:
                    continue
                phase_context = {**copy.deepcopy(current), 'phase': current['phase'] + phase}
                if phase == 'enhance_effects':
                    phase_context['conditions'].append({'enhance': card.get('enhance')})
                walk_effects(card.get(phase, []), phase_context, ancestry)
                for mode, effects in enumerate(card.get('modes', {}).get(phase, [])):
                    walk_effects(effects, {**phase_context, 'mode': mode}, ancestry)
            for key in ('triggers', 'hand_triggers'):
                walk_triggers(card.get(key, []), {**current, 'phase': current['phase'] + key}, ancestry)
            if not summoned:
                for form, definition in card.get('forms', {}).items():
                    form_context = {**copy.deepcopy(current), 'form': form}
                    form_context['conditions'].append({'form': form, 'cost': definition['cost']})
                    walk_card(card_id, definition, form_context, ancestry)

        walk_card(root_id, root, {'phase': '', 'form': None, 'mode': None, 'conditions': [],
                                 'card_ids': [], 'reversed_owner': False}, frozenset({root_id}))
        roles = sorted({role for path in paths for role in path['roles']})
        profiles[root_id] = {'roles': roles or ['unknown'], 'paths': paths,
                             'support': sorted({op for path in paths for op in path['support']}),
                             'unknown': not roles or 'unknown' in roles,
                             'scope': 'possible structural roles; engine legality and all path conditions still apply'}
    return profiles


def response_weights(pool: Counter[str], hand_size: int,
                     requirements: list[dict[str, int]]) -> list[Fraction]:
    """Exclusive best-first availability masses, followed by the fallback mass.

    Draw ``hand_size`` cards uniformly without replacement from ``pool``. Entry i is
    the probability that requirement i is met and no earlier requirement is met.
    The caller subtracts known hand cards and includes initial discard dependencies;
    cards generated during a plan are not unknown-hand requirements. Impossible
    requirements have zero mass. Negative/noninteger counts are invalid input.
    These are card-availability probabilities, not win rates or exact response scores.
    """
    # AI_NOTE: 最良からの和集合の増分を使い、同じ手札・多役割カードの確率を二重計上しない。
    if type(hand_size) is not int or hand_size < 0:
        raise ValueError('hand_size must be a nonnegative integer')
    if any(type(n) is not int or n < 0 for n in pool.values()):
        raise ValueError('pool counts must be nonnegative integers')
    if any(type(n) is not int or n < 0 for requirement in requirements for n in requirement.values()):
        raise ValueError('requirement counts must be nonnegative integers')
    total = sum(pool.values())
    if hand_size > total:
        raise ValueError('hand_size exceeds the remaining pool')
    types = sorted({cid for requirement in requirements for cid, n in requirement.items() if n})
    counts = [pool[cid] for cid in types]
    neutral = total - sum(counts)
    needs = [[requirement.get(cid, 0) for cid in types] for requirement in requirements]
    valid = {i for i, row in enumerate(needs) if sum(row) <= hand_size and all(n <= count for n, count in zip(row, counts))}
    masks = [[sum(1 << i for i in valid if needs[i][j] <= n) for n in range(count + 1)]
             for j, count in enumerate(counts)]
    finished = [sum(1 << i for i in valid if not any(needs[i][j:])) for j in range(len(types) + 1)]
    suffix = [sum(counts[j:]) + neutral for j in range(len(types) + 1)]

    @lru_cache(maxsize=None)
    def ways(index: int, slots: int, active: int) -> int:
        # AI_NOTE: 要求を満たせる候補だけ保持し、残りが自由になった部分は組合せ数へ畳む。
        if not active or slots < 0 or slots > suffix[index]:
            return 0
        if active & finished[index]:
            return comb(suffix[index], slots)
        result = 0
        for count in range(max(0, slots - suffix[index + 1]), min(counts[index], slots) + 1):
            result += comb(counts[index], count) * ways(index + 1, slots - count, active & masks[index][count])
        return result

    denominator = comb(total, hand_size)
    previous = 0
    minimal: list[int] = []
    weights: list[Fraction] = []
    for i, requirement in enumerate(needs):
        if i in valid and not any(all(a <= b for a, b in zip(needs[j], requirement)) for j in minimal):
            minimal = [j for j in minimal if not all(a <= b for a, b in zip(requirement, needs[j]))] + [i]
        current = ways(0, hand_size, sum(1 << j for j in minimal))
        weights.append(Fraction(current - previous, denominator))
        previous = current
    return weights + [Fraction(denominator - previous, denominator)]
