"""Role-seeded legal witness hands and overlap-safe response diagnostics.

Only availability of declared card requirements is exact under a uniform unseen
allocation model. Witness completions, hidden modifiers and bounded play scores
are approximations, never a posterior win probability.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from time import perf_counter

from svdeck.battle_env.battle import Battle, Json, integer
from svdeck.battle_env.battle_ai import BASE_WEIGHTS, evaluate
from svdeck.battle_env.battle_role_search import Budget, Turn, goals
from svdeck.battle_env.battle_roles import card_roles, response_weights


def remaining(observation: Json, who: int) -> tuple[Counter[str], list[Json]]:
    # AI_NOTE: Revealed originals are removed once; generated known cards do not consume deck copies.
    knowledge = observation.get('deck_knowledge')
    if knowledge is None:
        return Counter(), []
    info = knowledge[who]
    pool = Counter(info['deck_list'])
    pool.subtract(info['revealed'].values())
    if isinstance(observation['players'][who]['hand'], list):
        originals = observation.get('own_hand_originals', {})
        pool.subtract(e['card_id'] for e in observation['players'][who]['hand']
                      if e['id'] in originals and originals[e['id']] not in info['revealed'])
    if any(n < 0 for n in pool.values()):
        raise ValueError('公開デッキと既知カードの残数が一致しません')
    return +pool, copy.deepcopy(info['known_hand'])


def public_world(observation: Json, cards: dict[str, Json]) -> Battle:
    # AI_NOTE: Construct solely from the public view; deterministic completion is not actual hidden knowledge.
    state = copy.deepcopy(observation)
    if any(k in state for k in ('rng', 'next_id', 'deck_origins')):
        raise ValueError('rolesには全状態ではなく公開observationを渡してください')
    actor = state['active_player']
    state.pop('legal_actions', None)
    state.pop('own_hand_originals', None)
    origins: list[dict[str, str]] = [{}, {}]
    state['rng'] = 1
    visible = {e['id'] for p in state['players'] for zone in ('hand', 'board')
               if isinstance(p[zone], list) for e in p[zone]}
    prefix = 'role-hidden:'
    while any(x.startswith(prefix) for x in visible):
        prefix += ':'
    # Without a public deck, placeholders preserve zone counts but cannot invent playable hidden spells.
    fallback = 'role-unknown-slot'
    if observation.get('deck_knowledge') is None:
        while fallback in cards:
            fallback += ':'
        cards = dict(cards) | {fallback: {'name': '非公開カード', 'kind': 'spell', 'cost': 99, 'effects': []}}
    for who, player in enumerate(state['players']):
        if not isinstance(player['deck'], dict) or set(player['deck']) != {'count'}:
            raise ValueError('AI観測に山札の中身を含めないでください')
        pool, known = remaining(observation, who)
        values = sorted(pool.elements())
        deck_count = integer(player['deck']['count'], 'deck.count', 0, 200)
        if who != actor:
            if not isinstance(player['hand'], dict) or set(player['hand']) != {'count'}:
                raise ValueError('AI観測に相手の実手札を含めないでください')
            count = integer(player['hand']['count'], 'hand.count', 0, 9)-len(known)
            if count < 0:
                raise ValueError('既知手札が手札枚数を超えています')
            if observation.get('deck_knowledge') is None:
                values = [fallback]*(count+deck_count)
            if len(values) != count+deck_count:
                raise ValueError('公開残数と非公開領域の枚数が一致しません')
            player['hand'] = known+[{'id': f'{prefix}{who}:hand:{i}', 'card_id': cid}
                                    for i, cid in enumerate(values[:count])]
            values = values[count:]
        elif observation.get('deck_knowledge') is None:
            values = [fallback]*deck_count
        if len(values) != deck_count:
            raise ValueError('公開残数と山札枚数が一致しません')
        player['deck'] = [{'id': f'{prefix}{who}:deck:{i}', 'card_id': cid} for i, cid in enumerate(values)]
        if observation.get('deck_knowledge') is not None:
            for zone in ('hand', 'deck', 'board'):
                for entity in player[zone]:
                    eid = entity['id']
                    if eid.startswith(prefix) or eid in observation['deck_knowledge'][who]['revealed']:
                        origins[who][eid] = eid
            if who == actor:
                origins[who].update(observation.get('own_hand_originals', {}))
    if observation.get('deck_knowledge') is not None:
        # Synthetic origins only: public burns/discards update this hypothesis without reading real hidden IDs.
        state['deck_origins'] = origins
    return Battle(state, cards, record=False)


def hand_patterns(pool: Counter[str], slots: int, profiles: dict[str, Json],
                  cards: dict[str, Json], priorities: list[str], role_k: int) -> list[tuple[str, ...]]:
    # AI_NOTE: Seed by each role plus enabling pairs, then complete real legal hands without replacement.
    if slots == 0:
        return [()]
    types = sorted(cid for cid, n in pool.items() if n)
    minimum = {cid: min([cards[cid]['cost']]+[v['cost'] for v in cards[cid].get('forms', {}).values()]) for cid in types}
    seeds: list[tuple[tuple[str, ...], str]] = [((), 'develop')]
    for role in priorities:
        relevant = sorted((cid for cid in types if role in profiles[cid]['roles']), key=lambda cid: (minimum[cid], cid))
        seeds.extend(((cid,), role) for cid in relevant[:role_k])
    supports = sorted((cid for cid in types if set(profiles[cid]['roles']) & {'support', 'resource'}),
                      key=lambda cid: (minimum[cid], cid))[:role_k]
    if slots > 1:
        seeds += [(seed+(support,), role) for seed, role in list(seeds) if seed
                  for support in supports if support != seed[0] or pool[support] >= 2]
    result: list[tuple[str, ...]] = []
    for seed, role in seeds:
        counts = Counter(seed)
        if len(seed) > slots or any(n > pool[cid] for cid, n in counts.items()):
            continue
        order = sorted(types, key=lambda cid: (role not in profiles[cid]['roles'],
                       'support' not in profiles[cid]['roles'], minimum[cid], cid))
        while sum(counts.values()) < slots:
            added = False
            for cid in order:
                if counts[cid] < pool[cid] and sum(counts.values()) < slots:
                    counts[cid] += 1
                    added = True
            if not added:
                raise ValueError('残存カードより手札枚数が多いです')
        hand = tuple(sorted(counts.elements()))
        if hand not in result:
            result.append(hand)
    return result


def witness(battle: Battle, pool: Counter[str], hand: tuple[str, ...], known: list[Json]) -> Battle:
    # AI_NOTE: A witness never holds more than nine cards or more copies than the public residual deck.
    raw = copy.deepcopy(battle.state)
    raw.pop('deck_knowledge', None)
    raw.pop('deck_origins', None)
    actor = raw['active_player']
    rest = pool-Counter(hand)
    ids = {e['id'] for p in raw['players'] for zone in ('hand', 'board', 'deck') for e in p[zone]}
    prefix = 'role-witness:'
    while any(x.startswith(prefix) for x in ids):
        prefix += ':'
    raw['players'][actor]['hand'] = copy.deepcopy(known)+[
        {'id': f'{prefix}hand:{i}', 'card_id': cid} for i, cid in enumerate(hand)]
    raw['players'][actor]['deck'] = [{'id': f'{prefix}deck:{i}', 'card_id': cid}
                                    for i, cid in enumerate(sorted(rest.elements()))]
    raw['rng'] = 1
    return Battle(raw, battle.cards, record=False)


def trace_labels(start: Battle, steps: list[Json]) -> list[str]:
    # AI_NOTE: Explanations use card names; conditional chance traces retain explicit draws separately.
    names = {e['id']: e['name'] for p in start.state['players'] for z in ('hand', 'board', 'deck') for e in p[z]}
    verbs = {'play': '使用', 'attack': '攻撃', 'evolve': '進化', 'super_evolve': '超進化',
             'end_turn': 'ターン終了', 'extra_pp': '追加PP'}
    return [verbs.get(s['action']['type'], s['action']['type'])+
            (('：'+names.get(s['action'].get('card', s['action'].get('source')), '生成カード'))
             if s['action']['type'] not in {'end_turn', 'extra_pp'} else '') for s in steps]


def analyze_responses(battle: Battle, pool: Counter[str] | dict[str, int], hand_size: int, *,
                      known_hand: list[Json] | None = None, role_k: int = 5,
                      max_nodes: int = 6000, seconds: float = 10,
                      weights: dict[str, float] | None = None, include_records: bool = True,
                      budget: Budget | None = None, profiles: dict[str, Json] | None = None) -> Json:
    # AI_NOTE: Public diagnostics expose hypotheses, requirements and disjoint weights, not fictional certainty.
    integer(role_k, 'role_k', 1, 20)
    integer(hand_size, 'hand_size', 0, 9)
    integer(max_nodes, 'max_nodes', 1, 1000000)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds <= 3600:
        raise ValueError('secondsは0より大きく3600以下です')
    pool = Counter(pool)
    if any(type(n) is not int or n < 0 or cid not in battle.cards for cid, n in pool.items()):
        raise ValueError('残存カード枚数が不正です')
    known = [] if known_hand is None else known_hand
    if hand_size+len(known) > 9 or hand_size > sum(pool.values()):
        raise ValueError('手札枚数と公開残数が一致しません')
    start = perf_counter()
    budget = Budget(max_nodes, start+seconds) if budget is None else budget
    before = budget.nodes
    cap = min(budget.maximum, before+max_nodes)
    profiles = card_roles(battle.cards) if profiles is None else profiles
    priorities = goals(battle, battle.state['active_player'])
    patterns = hand_patterns(pool, hand_size, profiles, battle.cards, priorities, role_k)
    maximum_hands = max(3, role_k*3)
    cutoffs = {'role_hands'} if len(patterns) > maximum_hands else set()
    if any(sum(role in profiles[cid]['roles'] for cid, n in pool.items() if n) > role_k for role in priorities):
        cutoffs.add('role_types')
    patterns = patterns[:maximum_hands]
    rows: list[Json] = []
    seen: set[str] = set()
    weights = BASE_WEIGHTS if weights is None else weights
    for index, hand in enumerate(patterns):
        if budget.nodes >= cap or perf_counter() >= budget.deadline:
            cutoffs.add('response_budget')
            break
        world = witness(battle, pool, hand, known)
        allowance = max(1, (cap-budget.nodes)//(len(patterns)-index))
        turn = Turn(world, profiles, weights, budget, allowance, min(role_k, 3))
        plans = turn.options()
        cutoffs.update(turn.cutoffs)
        actor = world.state['active_player']
        originals = {e['id']: e['card_id'] for e in world.state['players'][actor]['hand']}
        known_ids = {e['id'] for e in known}
        choices = turn.select(plans, role_k)
        no_card = max((p for p in plans if not p.used), key=lambda p: p.score, default=None)
        if no_card is not None and all(p is not no_card for p in choices):
            choices.append(no_card)
        for plan in choices:
            required = Counter(originals[i] for i in plan.used if i in originals)
            hidden = Counter(originals[i] for i in plan.used if i in originals and i not in known_ids)
            # Hidden filler cards are a score hypothesis, not extra copies offered freely to the engine.
            signature = json.dumps([dict(sorted(required.items())),
                [(str(l.probability), [(p['health'], p['board']) for p in l.battle.state['players']]) for l in plan.leaves]],
                sort_keys=True, separators=(',', ':'))
            if signature in seen:
                continue
            seen.add(signature)
            representative = max(plan.leaves, key=lambda leaf: leaf.probability)
            score = -sum(float(l.probability)*evaluate(l.battle, 1-actor, weights) for l in plan.leaves)
            row: Json = {'required_cards': dict(required), 'required_unknown': dict(hidden),
                         'roles': sorted(plan.roles), 'score': score, 'steps': representative.steps,
                         'labels': trace_labels(world, representative.steps), 'assumed_hand': dict(Counter(hand)),
                         'unknown_draw': plan.unknown, 'outcomes': [
                             {'probability_exact': str(l.probability), 'steps': l.steps,
                              'winner': l.battle.state['winner'],
                              'health': [p['health'] for p in l.battle.state['players']]} for l in plan.leaves],
                         '_leaves': plan.leaves, '_world': world}
            if include_records:
                row['witness_record'] = world.export()
                for outcome, leaf in zip(row['outcomes'], plan.leaves):
                    outcome['state'] = leaf.battle.state
            rows.append(row)
    rows.sort(key=lambda r: (-r['score'], json.dumps(r['required_cards'], sort_keys=True)))
    # Keep incomparable role families, and the best no-card continuation as the fallback event.
    selected: list[Json] = []
    for role in priorities:
        selected += [r for r in rows if role in r['roles'] and all(r is not old for old in selected)][:role_k]
    empty = next((r for r in rows if not r['required_unknown']), None)
    if empty is not None and all(empty is not r for r in selected):
        selected.append(empty)
    if len(selected) < len(rows):
        cutoffs.add('response_top_k')
    selected.sort(key=lambda r: (-r['score'], json.dumps(r['required_cards'], sort_keys=True)))
    masses = response_weights(pool, hand_size, [r['required_unknown'] for r in selected])
    card_mass = response_weights(pool, hand_size, [r['required_unknown'] for r in selected if r['required_unknown']])
    for row, mass in zip(selected, masses):
        row['weight_exact'] = str(mass)
        row['availability_exact'] = str(response_weights(pool, hand_size, [row['required_unknown']])[0])
    evidence: Json = {'available': True, 'role_k': role_k, 'goals': priorities,
                     'profiles': {cid: profiles[cid] for cid, count in pool.items() if count},
                     'candidates': selected, 'hand_size': hand_size, 'pool': dict(pool),
                     'witness_hands': min(index+1, len(patterns)) if patterns else 0,
                     'candidate_count': len(selected), 'nodes': budget.nodes-before,
                     'coverage_exact': str(1-card_mass[-1]), 'fallback_weight_exact': str(masses[-1]),
                     'coverage_scope': 'Probability of holding a declared nonempty required-card set, not tactical search completeness.',
                     'cutoffs': sorted(cutoffs | budget.cutoffs), 'complete': False,
                     'witness_search_complete': not cutoffs and not budget.cutoffs,
                     'depth': 1 if selected else 0, 'depth_unit': 'turns',
                     'elapsed_ms': (perf_counter()-start)*1000,
                     'scope': 'Role-seeded witness scores are approximate. Exact weights only describe uniform unseen-card availability; overlapping hands are counted once. No actual hidden hand, modifiers or deck order are observed.'}
    if include_records:
        for row in selected:
            row.pop('_leaves')
            row.pop('_world')
    return evidence


def public_diagnostics(info: Json) -> Json:
    # AI_NOTE: Live decisions keep compact explanations, not private engine objects or multi-megabyte worlds.
    return {key: ([{k: v for k, v in row.items() if not k.startswith('_')} for row in value]
                  if key == 'candidates' else value) for key, value in info.items()}
