"""Regression oracles for chance boundaries, legal residual hands and no hidden draws."""
from collections import Counter
from fractions import Fraction
from time import perf_counter

from svdeck.battle_env.battle import Battle
from svdeck.battle_env.battle_ai import BASE_WEIGHTS, Player, evaluate
from svdeck.battle_env.battle_role_ai import continuation
from svdeck.battle_env.battle_role_response import analyze_responses, public_world, remaining
from svdeck.battle_env.battle_role_search import Budget, Turn
from svdeck.battle_env.battle_roles import card_roles


def test_random_action_is_discarded_when_only_one_sibling_can_close() -> None:
    # AI_NOTE: One affordable sibling cannot make an incompletely evaluated random action selectable.
    cards = {'blank': {'name': 'blank', 'kind': 'spell', 'cost': 99},
             'dice': {'name': 'dice', 'kind': 'spell', 'cost': 0, 'effects': [{'op': 'damage', 'target': 'random_enemy', 'amount': 1}]},
             'body': {'name': 'body', 'kind': 'follower', 'cost': 1, 'attack': 0, 'health': 2}}
    battle = Battle({'players': [{'hand': [{'id': 'dice', 'card_id': 'dice'}], 'extra_pp_used': True, 'deck': ['blank']*3},
                                {'board': ['body', 'body'], 'deck': ['blank']*3}]}, cards)
    turn = Turn(battle, card_roles(battle.cards), BASE_WEIGHTS, Budget(4, perf_counter()+10), 4, 3)
    plans = turn.options()
    assert [p.action for p in plans] == [{'type': 'end_turn'}]
    assert all(l.battle.state['active_player'] == 1 for p in plans for l in p.leaves)
    assert all(sum(l.probability for l in p.leaves) == 1 for p in plans)


def test_unknown_natural_draw_cannot_be_played_as_a_known_finisher() -> None:
    # AI_NOTE: A hypothetical top card must not become evidence of a guaranteed future win.
    cards = {'blank': {'name': 'blank', 'kind': 'spell', 'cost': 99},
             'burn': {'name': 'burn', 'kind': 'spell', 'cost': 0, 'effects': [{'op': 'damage', 'target': 'enemy_leader', 'amount': 20}]}}
    battle = Battle({'active_player': 1, 'players': [{'deck': ['burn', 'blank']}, {'deck': ['blank']*3}]}, cards)
    budget = Budget(100, perf_counter()+10)
    profiles = card_roles(battle.cards)
    turn = Turn(battle, profiles, BASE_WEIGHTS, budget, 50, 3)
    leaf = turn.finish(turn.root).leaves[0]
    assert leaf.battle.unknown_draw
    player = Player(battle.cards, 'roles')
    score, depth = continuation(leaf.battle, 0, 1, player, profiles, budget)
    assert depth == 0 and score == evaluate(leaf.battle, 0, BASE_WEIGHTS)
    assert 'future_unknown_draw' in budget.cutoffs


def test_no_usable_card_event_has_a_legal_closed_turn() -> None:
    # AI_NOTE: The one zzz hand out of twenty belongs to a real no-card reply, not an unclosed fallback score.
    cards = {cid: {'name': cid, 'kind': 'spell', 'cost': cost, 'effects': [{'op': 'damage', 'target': 'enemy_leader', 'amount': 3}]}
             for cid, cost in [('a', 1), ('b', 1), ('c', 1), ('z', 99)]}
    battle = Battle({'players': [{'pp': 1, 'max_pp': 1, 'extra_pp_used': True}, {'deck': ['z']*3}]}, cards)
    info = analyze_responses(battle, Counter(a=1, b=1, c=1, z=3), 3, role_k=3, max_nodes=1000)
    empty = [r for r in info['candidates'] if not r['required_unknown']]
    assert empty and Fraction(empty[0]['weight_exact']) == Fraction(1, 20)
    assert info['fallback_weight_exact'] == '0'
    assert empty[0]['steps'][-1]['action'] == {'type': 'end_turn'}
    assert all(o['state']['active_player'] == 1 for o in empty[0]['outcomes'])
    assert not info['complete'] and 'role_types' in info['cutoffs']


def test_overflow_is_removed_from_public_residual_pool() -> None:
    # AI_NOTE: A burned original is publicly consumed and cannot reappear in a reconstructed witness deck.
    cards = {'blank': {'name': 'blank', 'kind': 'spell', 'cost': 99}}
    battle = Battle({'players': [{'deck': ['blank']*3}, {'hand': ['blank']*9, 'deck': ['blank']*2}],
                     'deck_knowledge': [{'deck_list': {'blank': 3}, 'revealed': {}, 'known_hand': []},
                                        {'deck_list': {'blank': 11}, 'revealed': {}, 'known_hand': []}]}, cards)
    world = public_world(battle.observation(0), battle.cards)
    turn = Turn(world, card_roles(world.cards), BASE_WEIGHTS, Budget(30, perf_counter()+10), 30, 3)
    after = turn.finish(turn.root).leaves[0].battle
    pool, known = remaining(after.observation(0), 1)
    assert pool == Counter(blank=10) and not known
    info = analyze_responses(after, pool, 9, max_nodes=100)
    assert all(len(r['witness_record']['initial']['players'][1]['deck']) == 1 for r in info['candidates'])


def test_budget_limited_candidates_share_the_same_comparison_boundary() -> None:
    # AI_NOTE: Tight budgets may reduce depth, but must not compare candidates before and after different replies.
    battle = Battle({'players': [{'board': [{'id': 'body', 'card_id': 'test-body'}], 'deck': ['test-body']*3},
                                {'board': ['test-body'], 'deck': ['test-body']*3}]})
    for nodes in (10, 40, 150):
        result = Player(battle.cards, 'roles', max_nodes=nodes, seconds=5).choose(battle.observation(0))
        assert result['action'] in battle.legal_actions()
        assert result['nodes'] <= nodes
        assert all(c['comparison_depth'] == result['depth'] for c in result['candidates'])


def test_missing_public_deck_cannot_invent_a_hidden_spell() -> None:
    # AI_NOTE: Unknown cards preserve counts without turning an absent deck model into fabricated removal.
    battle = Battle({'players': [{'deck': ['test-body']*3},
                                {'hand': ['test-damage-5'], 'pp': 10, 'max_pp': 10, 'deck': ['test-body']*3}]})
    world = public_world(battle.observation(0), battle.cards)
    world.step({'type': 'end_turn'})
    assert not any(a['type'] == 'play' for a in world.legal_actions())
