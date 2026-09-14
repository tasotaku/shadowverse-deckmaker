"""Public-information turn search and a small, trainable position evaluator.

The player accepts observations, never a live Battle or its hidden state.
Unknown draws stop a plan; sampled cards are not treated as known future cards.
"""
from __future__ import annotations

import copy
import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .battle import Battle, integer
from . import battle_rules as rules

Json = dict[str, Any]
BASE_WEIGHTS = {'health': 1.0, 'pressure': 1.7, 'attack': 1.3, 'body': 0.65,
                'hand': 1.5, 'ramp': 2.8, 'reserve': 1.4, 'guard': 1.5,
                'ability': 1.2, 'danger': 4.0, 'grave': 0.12}
POLICIES = ('random', 'greedy', 'search', 'trained')
MODEL_PATH = Path(__file__).with_name('data') / 'battle_ai_model.json'


class SearchBattle(Battle):
    """An isolated branch with uncertainty tracking but no replay allocation."""

    uncertain = False

    def emit(self, kind: str, message: str, **values: Any) -> None:
        # AI_NOTE: record=Falseでも未知情報に触れた事実を検知し、架空のドロー先を読み切らない。
        if kind == 'random' or (kind == 'effect' and values['effect']['op'] in {'draw', 'deck_summon'}):
            self.uncertain = True

    def branch(self, action: Json) -> SearchBattle:
        # AI_NOTE: 呼出側で列挙済みの合法手だけを、独立した状態に同じexecuteで試す。
        child = copy.copy(self)
        child.state = copy.deepcopy(self.state)
        child.pending = []
        child.destroyed_in_action = set()
        child.uncertain = False
        child.execute(action)
        return child

    def random_index(self, length: int) -> int:
        # AI_NOTE: リアニメイト等のログを出さない抽選も含め、未知の結果を確定扱いしない。
        if length > 1:
            self.uncertain = True
        return super().random_index(length)


def sample_world(observation: Json, cards: dict[str, Json], seed: int) -> SearchBattle:
    # AI_NOTE: 本物の山札/相手手札/乱数は受け取れない境界。枚数を保持して山札切れの誤判定を防ぐ。
    state = copy.deepcopy(observation)
    state.pop('legal_actions', None)
    if 'rng' in state or 'next_id' in state:
        raise ValueError('AIには全状態ではなくobservationを渡してください')
    actor = state['active_player']
    generator = random.Random(seed)
    state['rng'] = generator.randrange(1, 2**32)
    visible_ids = {e['id'] for p in state['players'] for zone in ('hand', 'board')
                   if isinstance(p[zone], list) for e in p[zone]}
    prefix = 'ai-hidden:'
    while any(ident.startswith(prefix) for ident in visible_ids):
        prefix += ':'
    for who, player in enumerate(state['players']):
        if not isinstance(player['deck'], dict) or set(player['deck']) != {'count'}:
            raise ValueError('AI観測に山札の内容を含めないでください')
        if who != actor and (not isinstance(player['hand'], dict) or set(player['hand']) != {'count'}):
            raise ValueError('AI観測に相手の手札を含めないでください')
        visible = player['board'] + (player['hand'] if who == actor else [])
        classes = {cards[e['card_id']].get('class_name') for e in visible} - {None, 'ニュートラル'}
        pool = [cid for cid, card in cards.items() if not card.get('synthetic') and not card.get('token')
                and (not classes or card.get('class_name') in classes | {'ニュートラル'})]
        pool = pool or list(cards)
        for zone in ('deck', 'hand'):
            if isinstance(player[zone], list):
                continue
            count = integer(player[zone]['count'], f'{zone}.count', 0, 200 if zone == 'deck' else 9)
            player[zone] = [{'id': f'{prefix}{who}:{zone}:{i}', 'card_id': generator.choice(pool)} for i in range(count)]
    return SearchBattle(state, cards, record=False)


def features(battle: Battle, owner: int) -> dict[str, float]:
    # AI_NOTE: カード名専用の手順でなく、盤面・資源・危険を共通の数値で評価する。
    own, enemy = battle.state['players'][owner], battle.state['players'][1-owner]
    def side(player: Json) -> dict[str, float]:
        result = dict.fromkeys(BASE_WEIGHTS, 0.0)
        result.update(health=float(player['health']), hand=float(len(player['hand'])),
                      ramp=float(player['max_pp']), reserve=float(player['ep'] + 1.7*player['sep'] + (not player['extra_pp_used'])),
                      grave=float(min(player['graveyard'], 20)))
        for e in player['board']:
            card = rules.definition(battle, e)
            if card['kind'] == 'follower':
                result['attack'] += e['attack']
                result['body'] += min(e['health'], 10) + 1
                result['guard'] += min(e['health'], 6)*0.35 if '守護' in e['keywords'] else 0
                result['ability'] += sum(k in e['keywords'] for k in ('バリア', '必殺', 'ドレイン', '潜伏', '破壊耐性'))
            result['ability'] += bool(card.get('last_words') and not e.get('lost_last_words'))
            result['ability'] += bool(card.get('end_turn')) + len(card.get('triggers', []))
        result['ability'] += 2*len(player.get('crests', []))
        return result
    a, b = side(own), side(enemy)
    result = {key: a[key]-b[key] for key in BASE_WEIGHTS}
    result['pressure'] = float(enemy['max_health'] - enemy['health'])
    # Public board reach is deliberately an estimate, not a claim about the opponent's hand.
    attacks = sorted((e['attack'] for e in enemy['board'] if rules.definition(battle,e)['kind']=='follower'), reverse=True)
    guards = [e for e in own['board'] if '守護' in e['keywords'] and '潜伏' not in e['keywords']]
    blocked = sum(max(e['health'], 1) + (3 if 'バリア' in e['keywords'] else 0) for e in guards)
    incoming = max(0, sum(attacks)-blocked)
    if own.get('damage_shield'):
        incoming = 0
    result['danger'] = -max(0, incoming - own['health'] + 5)
    if incoming >= own['health'] and incoming:
        result['danger'] -= 30
    return result


def evaluate(battle: Battle, owner: int, weights: dict[str, float]) -> float:
    # AI_NOTE: 勝敗は評価重みによる調整対象から外し、物量より終局を優先する。
    winner = battle.state['winner']
    if winner is not None:
        return 0.0 if winner == -1 else (100000.0 if winner == owner else -100000.0)
    return sum(weights[key]*value for key, value in features(battle, owner).items())


def load_weights() -> dict[str, float]:
    # AI_NOTE: 学習結果は版付きファイルから読み、存在しないモデルを学習済みと呼ばない。
    data = json.loads(MODEL_PATH.read_text())
    weights = data['weights']
    if data.get('version') != 1 or set(weights) != set(BASE_WEIGHTS) or any(
            not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in weights.values()):
        raise ValueError('AI評価重みの形式が不正です')
    return {key: float(value) for key,value in weights.items()}


@dataclass
class Node:
    worlds: list[SearchBattle]
    plan: list[Json]
    score: float
    uncertain: bool
    layouts: list[list[Json]]


class Player:
    def __init__(self, cards: dict[str, Json], policy: str = 'search', weights: dict[str, float] | None = None,
                 max_nodes: int = 160, width: int = 6, depth: int = 6, seed: int = 0):
        # AI_NOTE: 同じ共通処理に探索量・評価重みだけを差し替えて比較できる。
        if policy not in POLICIES:
            raise ValueError(f'未対応のAI方式: {policy}')
        self.cards = cards
        self.policy = policy
        self.weights = dict(weights if weights is not None else load_weights() if policy == 'trained' else BASE_WEIGHTS)
        if set(self.weights) != set(BASE_WEIGHTS) or any(not math.isfinite(v) for v in self.weights.values()):
            raise ValueError('評価重みが不正です')
        self.max_nodes = integer(max_nodes, 'max_nodes', 1, 10000)
        self.width = integer(width, 'width', 1, 100)
        self.depth = integer(depth, 'depth', 1, 20)
        self.seed = seed
        self.random = random.Random(seed)

    def choose(self, observation: Json) -> Json:
        # AI_NOTE: 判断理由・候補・探索限界を残し、悪い手を選んだ局面を再検証できる。
        started = time.perf_counter()
        legal = observation['legal_actions']
        if observation.get('winner') is not None or not legal:
            raise ValueError('終局または手番外のため選択できません')
        if self.policy == 'random':
            action = copy.deepcopy(self.random.choice(legal))
            return {'action': action, 'policy': self.policy, 'reason': '合法手から無作為に選択',
                    'score': None, 'nodes': 0, 'depth': 1, 'uncertain': False, 'plan': [action], 'candidates': [],
                    'elapsed_ms': (time.perf_counter()-started)*1000}
        owner = observation['active_player']
        worlds = [sample_world(observation,self.cards,self.seed+i*7919) for i in range(2)]
        frontier = [Node(worlds, [], 0, False, [])]
        results: list[Node] = []
        seen: set[str] = set()
        nodes = 0
        limited = False
        max_depth = 1 if self.policy == 'greedy' else self.depth
        for level in range(max_depth):
            next_nodes: list[Node] = []
            for parent in frontier:
                choices = legal if not parent.plan else parent.worlds[0].legal_actions()
                for action in choices:
                    if nodes >= self.max_nodes:
                        limited = True
                        break
                    if any(action not in world.legal_actions() for world in parent.worlds):
                        continue
                    children = [world.branch(action) for world in parent.worlds]
                    nodes += 1
                    uncertain = any(child.uncertain for child in children)
                    scores = [evaluate(child,owner,self.weights) for child in children]
                    score = sum(scores)/len(scores)
                    # Uncertain outcomes cannot be labelled a proven win; replan after seeing the result.
                    plan = parent.plan+[action]
                    layout = [{'id':e['id'],'card_id':e['card_id'],'name':e['name'],'owner':who,'zone':zone,'index':index}
                              for who,p in enumerate(children[0].state['players'])
                              for zone in ('board','hand') if zone=='board' or who==owner
                              for index,e in enumerate(p[zone])]
                    item = Node(children,plan,score-0.001*len(plan),uncertain,parent.layouts+[layout])
                    results.append(item)
                    if all(child.state['winner']==owner for child in children) and not uncertain:
                        return self.report(item,results,nodes,started,True,limited)
                    terminal = uncertain or any(child.state['winner'] is not None or child.state['active_player'] != owner for child in children)
                    if not terminal:
                        key = json.dumps(children[0].state,sort_keys=True,separators=(',',':'))
                        if key not in seen:
                            seen.add(key)
                            next_nodes.append(item)
                if limited:
                    break
            if not next_nodes or limited:
                break
            frontier = sorted(next_nodes,key=lambda item:item.score,reverse=True)[:self.width]
            if level == max_depth-1:
                limited = True
        if not results:
            raise ValueError('観測の合法手と探索状態が一致しません')
        best = max(results,key=lambda item:item.score)
        return self.report(best,results,nodes,started,False,limited)

    def report(self, best: Node, results: list[Node], nodes: int, started: float, win: bool, limited: bool) -> Json:
        # AI_NOTE: 評価値を勝率と偽らず、未探索の手や未知のドローがあることを記録する。
        candidates: dict[str, Json] = {}
        for item in results:
            action = item.plan[0]
            key = json.dumps(action,sort_keys=True)
            if key not in candidates or item.score > candidates[key]['score']:
                candidates[key] = {'action':action,'score':round(item.score,3)}
        reason = '公開情報だけで勝ち切れる手順を発見' if win else '盤面・体力・残り資源と、相手盤面からの危険を比較'
        if best.uncertain:
            reason += '。ドローやランダム結果は仮定を含むため、実行後に考え直します'
        return {'action': best.plan[0], 'policy':self.policy,'reason':reason,'score':round(best.score,3),
                'nodes':nodes,'depth':len(best.plan),'uncertain':best.uncertain,'proven_win':win,
                'limited':limited,'plan':best.plan,
                'plan_layouts':best.layouts,
                'plan_entities':{e['id']:e['name'] for layout in best.layouts for e in layout},
                'candidates': sorted(candidates.values(),key=lambda item:item['score'],reverse=True)[:5],
                'elapsed_ms':round((time.perf_counter()-started)*1000,2)}


def execute_plan(battle: Battle, decision: Json) -> list[Json]:
    # AI_NOTE: 隠れたnext_idを予知せず、生成後の公開位置とカード種から仮番号を実番号へ対応づける。
    if decision.get('uncertain') or len(decision.get('plan_layouts', [])) != len(decision['plan']):
        raise ValueError('未知の結果を含む手順は一手ずつ選び直してください')
    mapping: dict[str,str] = {}
    def translate(value: Any) -> Any:
        if isinstance(value,str):
            return mapping.get(value,value)
        if isinstance(value,list):
            return [translate(item) for item in value]
        if isinstance(value,dict):
            return {key:translate(item) for key,item in value.items()}
        return value
    actions = []
    for planned,layout in zip(decision['plan'],decision['plan_layouts']):
        action = translate(planned)
        battle.step(action)
        actions.append(action)
        for expected in layout:
            zone = battle.state['players'][expected['owner']][expected['zone']]
            if expected['index'] >= len(zone) or zone[expected['index']]['card_id'] != expected['card_id']:
                raise ValueError('実際の公開盤面が予想と異なるため、手順の実行を停止しました')
            mapping[expected['id']] = zone[expected['index']]['id']
    return actions
