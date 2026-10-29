"""Public-information role-guided opponent response policy for playable games."""
from __future__ import annotations

from fractions import Fraction
from time import perf_counter
from typing import TYPE_CHECKING

from svdeck.battle.battle import Battle, Json
from svdeck.battle.battle_ai import evaluate
from svdeck.battle.battle_lookahead import validate_work
from svdeck.battle.battle_role_response import analyze_responses, public_diagnostics, public_world, remaining
from svdeck.battle.battle_role_search import Budget, Plan, Turn
from svdeck.battle.battle_roles import card_roles

if TYPE_CHECKING:
    from svdeck.battle.battle_ai import Player


def continuation(battle: Battle, owner: int, turns: int, player: Player,
                 profiles: dict[str, Json], budget: Budget) -> tuple[float, int]:
    # AI_NOTE: Later turns stay in the same legal witness; never replenish spent hypothetical cards.
    score = evaluate(battle, owner, player.weights)
    reached = 0
    for _ in range(turns):
        if getattr(battle, 'unknown_draw', False) and battle.state['winner'] is None:
            budget.cutoffs.add('future_unknown_draw')
            break
        if battle.state['winner'] is not None or budget.nodes >= budget.maximum or perf_counter() >= budget.deadline:
            break
        turn = Turn(battle, profiles, player.weights, budget, min(64, budget.maximum-budget.nodes), 1, 4)
        plans = turn.options()
        budget.cutoffs.update(turn.cutoffs)
        if not plans:
            break
        selected = max(plans, key=lambda p: p.score)
        score = sum(float(l.probability)*evaluate(l.battle, owner, player.weights) for l in selected.leaves)
        reached += 1
        if len(selected.leaves) != 1:
            # A chance result may be integrated at this boundary, never chosen as a lucky future world.
            budget.cutoffs.add('future_chance_boundary')
            break
        battle = selected.leaves[0].battle
    return score, reached


def choose(player: Player, observation: Json) -> Json:
    # AI_NOTE: Roles replaces hidden-hand sampling with finite deterministic legal witnesses and disjoint weights.
    start = perf_counter()
    validate_work(player.cards)
    world = public_world(observation, player.cards)
    profiles = card_roles(world.cards)
    owner = observation['active_player']
    budget = Budget(player.max_nodes, start+player.seconds)
    own = Turn(world, profiles, player.weights, budget,
               max(40, min(700, player.max_nodes//5)), min(player.role_k, 3))
    plans = own.options()
    budget.cutoffs.update(own.cutoffs)
    # Different first actions and resource-conserving pass remain selectable, with goal representatives.
    selected = own.select(plans, min(player.role_k, 5))
    passing = next((p for p in plans if p.action['type'] == 'end_turn'), None)
    if passing is not None and all(p is not passing for p in selected):
        selected.append(passing)
    if len(selected) < len(plans):
        budget.cutoffs.add('own_top_k')
    has_deck = observation.get('deck_knowledge') is not None
    diagnostics: list[Json] = []
    stages: list[tuple[dict[int, float], Plan, Json]] = []
    for index, plan in enumerate(selected):
        base_score = sum(float(l.probability)*evaluate(l.battle, owner, player.weights) for l in plan.leaves)
        info: Json = {'available': False, 'goals': [], 'candidates': [], 'coverage_exact': '0',
                      'candidate_count': 0, 'scope': 'No opponent response modeled at this budget/horizon.'}
        scores = {1: base_score}
        terminal = all(l.battle.state['winner'] is not None for l in plan.leaves)
        if terminal:
            scores.update({depth: base_score for depth in range(2, player.turns+1)})
        # Each first-action candidate owns its reply AND future budget; earlier candidates cannot starve later ones.
        left = len(selected)-index
        now = perf_counter()
        local = Budget(max(0, (budget.maximum-budget.nodes)//left),
                       min(budget.deadline, now+max(0, budget.deadline-now)/left))
        # An immediate win needs no hypothetical reply, and must survive role/beam selection.
        if player.turns > 1 and not terminal:
            leaf_scores: list[float] = []
            future_scores: list[float] = []
            leaf_infos: list[Json] = []
            for leaf in plan.leaves:
                state = leaf.battle.state
                if state['winner'] is not None or state['active_player'] == owner:
                    leaf_scores.append(evaluate(leaf.battle, owner, player.weights))
                    future_scores.append(leaf_scores[-1])
                    continue
                if local.nodes >= local.maximum or perf_counter() >= local.deadline:
                    local.cutoffs.add('response_budget')
                    break
                if has_deck:
                    # Refresh public consumption for each own-action branch (overflow/discard/known generated cards).
                    pool, known = remaining(leaf.battle.observation(owner), 1-owner)
                    current_ids = {e['id'] for e in state['players'][1-owner]['hand']}
                    retained_known = [e for e in known if e['id'] in current_ids]
                    slots = len(state['players'][1-owner]['hand'])-len(retained_known)
                    allowance = max(1, (local.maximum-local.nodes)//max(1, len(plan.leaves)-len(leaf_scores)))
                    result = analyze_responses(leaf.battle, pool, slots, known_hand=retained_known,
                        role_k=player.role_k, max_nodes=allowance, weights=player.weights,
                        include_records=False, budget=local, profiles=profiles)
                    local.cutoffs.update(result['cutoffs'])
                    leaf_infos.append(public_diagnostics(result))
                    if Fraction(result['fallback_weight_exact']):
                        local.cutoffs.add('unclosed_response')
                        break
                    expected, future_expected = 0.0, 0.0
                    future_complete = True
                    for response in result['candidates']:
                        mass = Fraction(response['weight_exact'])
                        if not mass:
                            continue
                        expected += float(mass)*-float(response['score'])
                        if player.turns > 2:
                            future = 0.0
                            for response_leaf in response['_leaves']:
                                value, depth = continuation(response_leaf.battle, owner, player.turns-2,
                                                            player, profiles, local)
                                future += float(response_leaf.probability)*value
                                if response_leaf.battle.state['winner'] is None and depth < player.turns-2:
                                    future_complete = False
                            future_expected += float(mass)*future
                    leaf_scores.append(expected)
                    if player.turns > 2 and future_complete:
                        future_scores.append(future_expected)
                else:
                    # Missing public deck data is explicit; still consider legal public-board replies.
                    reply = Turn(leaf.battle, profiles, player.weights, local, min(80, local.maximum-local.nodes), 2)
                    choices = reply.options()
                    local.cutoffs.update(reply.cutoffs)
                    if not choices:
                        break
                    best = max(choices, key=lambda p: p.score)
                    leaf_scores.append(sum(float(l.probability)*evaluate(l.battle, owner, player.weights) for l in best.leaves))
                    local.cutoffs.add('unknown_deck')
            if len(leaf_scores) == len(plan.leaves):
                scores[2] = sum(float(leaf.probability)*value for leaf, value in zip(plan.leaves, leaf_scores))
            if player.turns > 2 and len(future_scores) == len(plan.leaves):
                scores[player.turns] = sum(float(leaf.probability)*value for leaf, value in zip(plan.leaves, future_scores))
            if leaf_infos:
                info = leaf_infos[0]
                info['conditional_branches'] = leaf_infos[1:]
        budget.nodes += local.nodes
        budget.cutoffs.update(local.cutoffs)
        stages.append((scores, plan, info))
    if not stages:
        action = observation['legal_actions'][0]
        return {'policy': 'roles', 'action': action, 'reason': '探索予算内に評価できず、未評価の合法手を使用',
                'score': None, 'nodes': budget.nodes, 'depth': 0, 'depth_unit': 'turns', 'complete': False,
                'optimal': False, 'proven_win': False, 'uncertain': True, 'limited': True,
                'cutoffs': sorted(budget.cutoffs | {'no_evaluated_action'}), 'plan': [action],
                'candidates': [], 'elapsed_ms': (perf_counter()-start)*1000,
                'role_search': {'available': False, 'role_k': player.role_k, 'goals': [], 'candidates': [], 'coverage_exact': '0'}}
    # Compare every candidate at the deepest COMMON evaluated boundary, never mix before/after the reply.
    common_depth = max(set.intersection(*(set(scores) for scores, _, _ in stages)))
    if common_depth < min(player.turns, 2):
        budget.cutoffs.add('common_horizon')
    scored = [(scores[common_depth], plan, info) for scores, plan, info in stages]
    for scores, plan, info in stages:
        diagnostics.append({'action': plan.action, 'score': scores[common_depth],
                            'turns_reached': max(scores), 'comparison_depth': common_depth,
                            'response_candidates': info.get('candidate_count', 0),
                            'coverage_exact': info.get('coverage_exact', '0')})
    score, chosen, info = max(scored, key=lambda row: (row[0], -len(row[1].leaves[0].steps)))
    reached = common_depth
    cutoffs = sorted(budget.cutoffs)
    info['own_candidates'] = diagnostics
    info['role_k'] = player.role_k
    info['turns_reached'] = reached
    info['requested_turns'] = player.turns
    info['complete_depth'] = 0 if cutoffs or has_deck else 1
    info['approximate'] = True
    labels = {'heal': '回復', 'remove_one': '単体除去', 'remove_multi': '複数面除去',
              'remove_all': '全体除去', 'damage': '打点', 'resource': 'リソース',
              'defense': '防御', 'develop': '展開', 'support': '補助', 'unknown': 'その他'}
    wanted = '・'.join(labels.get(g, g) for g in info.get('goals', [])[:4])
    reason = (f'公開デッキと盤面から必要な役割（{wanted or "盤面の攻防"}）を調べ、'
              f'{info.get("candidate_count", 0)}通りの返しを比較。{reached}ターン目までの候補を評価。'
              '手札の所持確率を重複なく重み付けした近似で、勝率や最善手の保証ではありません。')
    if cutoffs:
        reason += '候補数・探索予算による省略があります。'
    return {'policy': 'roles', 'action': chosen.action, 'reason': reason, 'score': round(score, 6),
            'nodes': budget.nodes, 'depth': reached, 'depth_unit': 'turns', 'turns_requested': player.turns,
            'complete': False, 'optimal': False, 'proven_win': False, 'uncertain': True,
            'limited': bool(cutoffs), 'cutoffs': cutoffs, 'plan': [chosen.action],
            'candidates': sorted(diagnostics, key=lambda r: r['score'], reverse=True),
            'role_search': info, 'elapsed_ms': (perf_counter()-start)*1000,
            'settings': {'policy_version': 5, 'role_k': player.role_k, 'turns': player.turns,
                         'max_nodes': player.max_nodes, 'seconds': player.seconds, 'seed': player.seed,
                         'opponent_model': 'role-seeded legal witnesses; uniform residual-card availability'}}
