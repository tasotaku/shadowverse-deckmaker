"""Known-deck hand samples and bounded opponent replies after a common own plan.

This is sampled reply search, not exact minimax or a solved imperfect-information game.
"""
from __future__ import annotations

import copy
import json
import time
from collections import Counter
from dataclasses import replace
from typing import Any

from .battle_ai import Node, Player, SearchBattle, evaluate, sample_world

Json = dict[str, Any]
HAND_SAMPLES = 8
OWN_CANDIDATES = 8
REPLY_NODES = 64
REPLY_DEPTH = 6
REPLY_WIDTH = 3


def finish(battle: SearchBattle, actor: int) -> SearchBattle:
    # AI_NOTE: パスした枝と行動途中の枝を、必ず同じ手番終了後まで進めて比較する。
    if battle.state['winner'] is not None or battle.state['active_player'] != actor:
        return battle
    return battle.branch({'type':'end_turn'})


def best_reply(start: SearchBattle, owner: int, weights: dict[str,float],
               max_nodes: int = REPLY_NODES) -> tuple[float, list[Json], int, bool]:
    # AI_NOTE: 各仮定手札の範囲でこちらの評価を最小にする返しを探索。相手は本当のこちらの手札を参照しない。
    actor = 1-owner
    baseline = finish(start,actor)
    best = (evaluate(baseline,owner,weights), [{'type':'end_turn'}])
    if start.state['winner'] is not None or start.state['active_player'] != actor:
        return evaluate(start,owner,weights), [], 0, False
    frontier: list[tuple[SearchBattle,list[Json]]] = [(start,[])]
    seen: set[str] = set()
    count = 0
    limited = False
    for depth in range(REPLY_DEPTH):
        children: list[tuple[float,SearchBattle,list[Json]]] = []
        for battle, plan in frontier:
            for action in battle.legal_actions():
                if count >= max_nodes:
                    limited = True
                    break
                child = battle.branch(action)
                count += 1
                route = plan+[action]
                end = finish(child,actor)
                score = evaluate(end,owner,weights)
                if (score,len(route)) < (best[0],len(best[1])):
                    best = (score,route)
                if child.state['winner']==actor and not child.uncertain:
                    return best[0],best[1],count,limited
                # Unseen draws/random results stop a contingent route; they never certify a root forced loss.
                if child.uncertain or child.state['winner'] is not None or child.state['active_player'] != actor:
                    continue
                key = json.dumps(child.state,sort_keys=True,separators=(',',':'))
                if key not in seen:
                    seen.add(key)
                    children.append((score,child,route))
            if limited:
                break
        if limited or not children:
            break
        frontier = [(battle,route) for _,battle,route in sorted(children,key=lambda row:row[0])[:REPLY_WIDTH]]
        if depth == REPLY_DEPTH-1:
            limited = True
    return best[0],best[1],count,limited


def apply_common_plan(world: SearchBattle, node: Node, owner: int) -> SearchBattle:
    # AI_NOTE: 隠れた手札ごとにこちらの手順を変えず、同じ公開手順を全サンプルへ適用する。
    mapping: dict[str,str] = {}
    def translate(value: Any) -> Any:
        # AI_NOTE: 複数対象の配列や辞書も、生成個体の対応を再帰的に適用する。
        if isinstance(value,str):
            return mapping.get(value,value)
        if isinstance(value,list):
            return [translate(item) for item in value]
        if isinstance(value,dict):
            return {key:translate(item) for key,item in value.items()}
        return copy.deepcopy(value)
    for action, layout in zip(node.plan,node.layouts):
        translated = translate(action)
        if translated not in world.legal_actions():
            raise ValueError('共通手順と仮定盤面の合法手が一致しません')
        world = world.branch(translated)
        if world.uncertain or world.state['winner'] is not None or world.state['active_player'] != owner:
            break
        for expected in layout:
            zone = world.state['players'][expected['owner']][expected['zone']]
            if expected['index'] >= len(zone) or zone[expected['index']]['card_id'] != expected['card_id']:
                raise ValueError('共通手順の生成カードを対応づけられません')
            mapping[expected['id']] = zone[expected['index']]['id']
    return finish(world,owner)


def choose_response(player: Player, observation: Json, results: list[Node], own_nodes: int,
                    started: float, limited: bool) -> Json:
    # AI_NOTE: 同一の8手札を全候補に使い、各手札で最も厳しい返しを平均する。珍しい組合せを常備扱いしない。
    owner = observation['active_player']
    ranked = sorted(results,key=lambda node:node.score,reverse=True)
    selected: list[Node] = []
    roots: set[str] = set()
    # Always compare passing, even when the preliminary heuristic dislikes it.
    passing = next((node for node in results if node.plan==[{'type':'end_turn'}]),None)
    if passing is not None:
        selected.append(passing)
        roots.add(json.dumps(passing.plan[0],sort_keys=True))
    for node in ranked:
        root = json.dumps(node.plan[0],sort_keys=True)
        if root not in roots:
            selected.append(node)
            roots.add(root)
            # Spending fewer cards after the same first move must remain an option against board clears.
            shortest = min((other for other in results if other.plan[0]==node.plan[0]),key=lambda other:len(other.plan))
            if shortest.plan != node.plan and len(selected)<OWN_CANDIDATES:
                selected.append(shortest)
        if len(selected)>=OWN_CANDIDATES:
            break
    worlds = [sample_world(observation,player.cards,player.seed+i*7919) for i in range(HAND_SAMPLES)]
    evaluated: list[Node] = []
    diagnostics: list[Json] = []
    reply_nodes = 0
    for node in selected:
        samples: list[Json] = []
        for world in worlds:
            after = apply_common_plan(world,node,owner)
            hand = {e['id']:e['card_id'] for e in after.state['players'][1-owner]['hand']}
            score, reply, count, cutoff = best_reply(after,owner,player.weights)
            reply_nodes += count
            limited = limited or cutoff
            required = Counter(hand[action['card']] for action in reply
                               if action['type']=='play' and action['card'] in hand)
            samples.append({'score':score,'reply':reply,'required_cards':dict(required),
                            'sampled_hand':dict(Counter(hand.values())),'limited':cutoff})
        mean = sum(sample['score'] for sample in samples)/HAND_SAMPLES
        evaluated.append(replace(node,score=mean-.001*len(node.plan)))
        diagnostics.append({'action':node.plan[0],'mean':mean,'worst':min(sample['score'] for sample in samples),
                            'losing_samples':sum(sample['score']<=-100000 for sample in samples),
                            'sample_scores':[sample['score'] for sample in samples],
                            'worst_reply':min(samples,key=lambda sample:sample['score'])})
    best_index = max(range(len(evaluated)),key=lambda i:evaluated[i].score)
    report = player.report(evaluated[best_index],evaluated,own_nodes+reply_nodes,started,False,limited,observation)
    info = diagnostics[best_index]
    report['reason'] = (f'公開デッキから{HAND_SAMPLES}通りの手札を仮定し、各手札で相手の厳しい返しを比較。'
                        f'返し後の平均評価 {info["mean"]:.1f}、最低 {info["worst"]:.1f}。'
                        f'敗北する仮定 {info["losing_samples"]}/{HAND_SAMPLES}（実際の勝率ではありません）')
    report['response_search'] = {'available':True,'hand_samples':HAND_SAMPLES,'own_candidates':len(selected),
                                 'reply_nodes':reply_nodes,'reply_depth':REPLY_DEPTH,'reply_width':REPLY_WIDTH,
                                 'max_reply_nodes_per_sample':REPLY_NODES,'aggregation':'mean of sampled worst replies',
                                 'horizon':'start of our next turn','candidates':diagnostics}
    report['elapsed_ms'] = round((time.perf_counter()-started)*1000,2)
    return report
