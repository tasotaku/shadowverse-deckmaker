"""効果の選択・発動を共有する。描画やカード名に依存しない対戦部品。"""
from __future__ import annotations

import copy
import itertools
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from svdeck.battle import Battle

Json = dict[str, Any]
EXTRA_OPS = {'repeat', 'discard', 'pp', 'ep', 'cost', 'remove_keywords', 'leader_max', 'shield',
             'split_damage', 'deck_summon', 'reanimate', 'copy_banish', 'crest'}
EXTRA_TARGETS = {'chosen_hand', 'event', 'all_enemy_characters', 'all_leaders', 'random_ally', 'all_other_ally'}
PHASES = ('effects', 'fanfare', 'evolve', 'super_evolve', 'last_words', 'end_turn', 'attack_effects', 'enhance_effects', 'on_discard', 'on_evolved')


def validate_condition(value: Any) -> None:
    # AI_NOTE: 未知条件を常に真として実行せず、保存定義の誤記を登録時に止める。
    if value in (None, 'awakening', 'combo3', 'max_pp10'):
        return
    if not isinstance(value, dict):
        raise ValueError('未対応の発動条件です')
    if set(value) == {'all'} and isinstance(value['all'], list) and value['all']:
        for child in value['all']:
            validate_condition(child)
        return
    if set(value) in ({'own_turn'}, {'ally_last_words'}) and type(next(iter(value.values()))) is bool:
        return
    keys = set(value)
    if len(keys & {'player', 'source'}) != 1 or not keys & {'eq', 'gte', 'lte'} or keys - {'player', 'source', 'eq', 'gte', 'lte'}:
        raise ValueError('条件の比較形式が不正です')
    if 'player' in value and value['player'] not in {'health', 'max_pp', 'combo', 'graveyard'}:
        raise ValueError('未対応のプレイヤー条件です')
    if 'source' in value and value['source'] not in {'evolved'}:
        raise ValueError('未対応のカード条件です')
    if any(type(n) is not int for k, n in value.items() if k in {'eq', 'gte', 'lte'}):
        raise ValueError('条件の比較値は整数です')


def validate_filter(query: Json) -> None:
    # AI_NOTE: 選別条件を限定し、未知条件を無視した広い対象への実行を防ぐ。
    if not isinstance(query, dict) or set(query) - {'kind', 'class_name', 'tribe', 'min_cost', 'max_cost', 'last_words', 'exclude_self', 'highest_attack'}:
        raise ValueError('未対応のカード条件です')
    for key in ('last_words', 'exclude_self', 'highest_attack'):
        if key in query and type(query[key]) is not bool:
            raise ValueError('選別条件は真偽値です')
    for key in ('tribe', 'min_cost', 'max_cost'):
        if key in query and (type(query[key]) is not int or query[key] < 0):
            raise ValueError('選別条件は0以上の整数です')


def validate_triggers(rules: list[Json], cards: dict[str, Json]) -> None:
    # AI_NOTE: 発動時点と作用を別々に検査し、画面用ログには依存させない。
    from svdeck.battle import validate_effect
    if not isinstance(rules, list):
        raise ValueError('発動定義は配列です')
    for rule in rules:
        if set(rule) - {'event', 'scope', 'filter', 'condition', 'effects', 'once_per_turn'} or rule.get('event') not in {'enter', 'turn_start', 'turn_end', 'heal'}:
            raise ValueError('未対応の発動時点です')
        if rule.get('scope', 'ally') not in {'ally', 'enemy', 'self', 'other_ally'}:
            raise ValueError('未対応の発動元です')
        validate_condition(rule.get('condition'))
        validate_filter(rule.get('filter', {}))
        for child in rule['effects']:
            validate_effect(child, cards)


def validate_crest(crest: Json, cards: dict[str, Json]) -> None:
    # AI_NOTE: 記録から戻す常在効果もカードと同じ検査を通す。
    if not isinstance(crest, dict) or set(crest) - {'id', 'name', 'keywords', 'triggers', 'last_trigger'}:
        raise ValueError('クレスト定義が不正です')
    if not isinstance(crest.get('id'), str) or not crest['id'].startswith('crest:') or not isinstance(crest.get('name'), str):
        raise ValueError('クレストの識別情報が不正です')
    validate_triggers(crest.get('triggers', []), cards)


def validate_selections(effects: list[Json]) -> dict[str, tuple[str, int]]:
    # AI_NOTE: 非活性な条件の内側も検査し、試験時だけ見えない選択の衝突を防ぐ。
    slots: dict[str, tuple[str, int]] = {}
    for effect in effects:
        children = validate_selections(effect.get('effects', []))
        if effect.get('target', '').startswith('chosen_'):
            children[effect.get('choice', 'target')] = (effect['target'], effect.get('select_count', 1))
        for key, spec in children.items():
            if key in slots and slots[key] != spec:
                raise ValueError('異なる選択対象には別のchoiceが必要です')
            slots[key] = spec
    return slots


def definition(battle: Battle, entity: Json) -> Json:
    # AI_NOTE: 結晶は場でアミュレットとして扱い、元のフォロワー能力を誤発動させない。
    base = battle.cards[entity['card_id']]
    if not entity.get('form'):
        return base
    form: Json = base['forms'][entity['form']]
    return {k: v for k, v in base.items() if k not in (*PHASES, 'keywords', 'modes', 'triggers', 'forms', 'enhance', 'countdown')} | form


def matches(battle: Battle, entity: Json, query: Json, source: Json | None = None) -> bool:
    # AI_NOTE: サーチ・場に出す能力・誘発条件が同じカード条件を参照する。
    card = definition(battle, entity)
    if query.get('exclude_self') and source and entity['id'] == source['id']:
        return False
    tribes: list[int] = list(entity.get('tribes') or card.get('tribes') or [])
    return bool(
        ('kind' not in query or card['kind'] == query['kind'])
        and ('class_name' not in query or card.get('class_name') == query['class_name'])
        and ('tribe' not in query or query['tribe'] in tribes)
        and ('min_cost' not in query or card['cost'] >= query['min_cost'])
        and ('max_cost' not in query or card['cost'] <= query['max_cost'])
        and ('last_words' not in query or bool(card.get('last_words') and not entity.get('lost_last_words')) == query['last_words'])
    )


def condition(battle: Battle, value: Any, owner: int, source: Json | None = None) -> bool:
    # AI_NOTE: 発動条件は効果実行時に判定し、数値をカード名で分岐しない。
    p = battle.state['players'][owner]
    if value is None:
        return True
    if isinstance(value, str):
        return bool({'awakening': p['max_pp'] >= 7, 'combo3': p['combo'] >= 3, 'max_pp10': p['max_pp'] == 10}[value])
    if 'all' in value:
        return all(condition(battle, c, owner, source) for c in value['all'])
    if 'own_turn' in value:
        return bool((battle.state['active_player'] == owner) == value['own_turn'])
    if 'ally_last_words' in value:
        return bool(any(matches(battle, e, {'last_words': True}) for e in p['board']) == value['ally_last_words'])
    actual = p[value['player']] if 'player' in value else (source or {}).get(value['source'], 0)
    return all({'eq': actual == expected, 'lte': actual <= expected, 'gte': actual >= expected}[op]
               for op, expected in value.items() if op in {'eq', 'lte', 'gte'})


def phases(card: Json, phase: str, mode: int | None = None) -> list[Json]:
    # AI_NOTE: モード選択は行動に保存し、再生時に同じ能力を実行する。
    result = list(card.get(phase, []))
    if phase in card.get('modes', {}) and mode is not None:
        result += card['modes'][phase][mode]
    return result


def selections(battle: Battle, effects: list[Json], owner: int, source: Json, playing: bool = False) -> dict[str, Json]:
    # AI_NOTE: 入れ子でも選択の用途を区別し、敵への選択を味方回復へ流用しない。
    result: dict[str, Json] = {}
    for effect in effects:
        active = condition(battle, effect.get('condition'), owner, source)
        if playing and effect.get('condition') == 'combo3':
            active = battle.state['players'][owner]['combo'] + 1 >= 3
        if not active:
            continue
        target = effect.get('target', 'self')
        if target.startswith('chosen_'):
            slot = effect.get('choice', 'target')
            spec = {'target': target, 'count': effect.get('select_count', 1)}
            if slot in result and result[slot] != spec:
                raise ValueError('異なる選択用途には別のchoiceを指定してください')
            result[slot] = spec
        nested = selections(battle, effect.get('effects', []), owner, source, playing)
        for slot, spec in nested.items():
            if slot in result and result[slot] != spec:
                raise ValueError('入れ子の選択用途が衝突しています')
            result[slot] = spec
    return result


def action_choices(battle: Battle, effects: list[Json], owner: int, source: Json, required: bool, playing: bool = False) -> list[Json]:
    # AI_NOTE: 手札2枚などは重複なしの組合せで列挙し、入力と実行で同じ対象規則を使う。
    specs = selections(battle, effects, owner, source, playing)
    if not specs:
        return [{}]
    options: list[list[tuple[str, Any]]] = []
    for slot, spec in specs.items():
        candidates = battle.choices(spec['target'], owner, source)
        if required and len(candidates) < spec['count']:
            return []
        count = min(spec['count'], len(candidates))
        if count == 0:
            if required:
                return []
            options.append([(slot, None)])
        elif spec['count'] == 1:
            options.append([(slot, candidate) for candidate in candidates])
        else:
            options.append([(slot, list(group)) for group in itertools.combinations(candidates, count)])
    result = []
    for selection in itertools.product(*options):
        values = {slot: value for slot, value in selection if value is not None}
        if list(specs) == ['target'] and specs['target']['count'] == 1:
            result.append({'target': values['target']} if values else {})
        else:
            result.append({'choices': values})
    return result


def trigger(battle: Battle, event: str, owner: int, entity: Json | None = None) -> None:
    # AI_NOTE: 発動予約は記録ON/OFFと独立。発動元と対象を固定してから共通の待ち列へ積む。
    if entity and event in {'discard', 'evolved'}:
        effects = definition(battle, entity).get('on_' + event, [])
        if effects:
            battle.pending.append((copy.deepcopy(effects), owner, copy.deepcopy(entity), '捨てられたとき' if event == 'discard' else '進化したとき'))
    for who in (battle.state['active_player'], 1 - battle.state['active_player']):
        player = battle.state['players'][who]
        sources = [(e, definition(battle, e).get('triggers', [])) for e in list(player['board'])]
        sources += [(e, definition(battle, e).get('hand_triggers', [])) for e in list(player['hand'])]
        sources += [(e, e.get('triggers', [])) for e in player.get('crests', [])]
        for source, rules in sources:
            for index, rule in enumerate(rules):
                if rule['event'] != event:
                    continue
                scope = rule.get('scope', 'ally')
                if (scope in {'ally', 'self', 'other_ally'} and owner != who) or (scope == 'enemy' and owner == who):
                    continue
                if scope == 'self' and (not entity or entity.get('id') != source['id']):
                    continue
                if scope == 'other_ally' and entity and entity.get('id') == source['id']:
                    continue
                if rule.get('filter') and (not entity or not matches(battle, entity, rule['filter'], source)):
                    continue
                if not condition(battle, rule.get('condition'), who, source):
                    continue
                if rule.get('once_per_turn'):
                    stamp = f'{battle.state["active_player"]}:{battle.state["players"][battle.state["active_player"]]["turn"]}:{index}'
                    if source.get('last_trigger') == stamp:
                        continue
                    source['last_trigger'] = stamp
                saved = copy.deepcopy(source)
                saved['event_target'] = entity['id'] if entity else None
                battle.pending.append((copy.deepcopy(rule['effects']), who, saved, {'enter':'場に出たとき', 'heal':'リーダーが回復したとき', 'turn_start':'ターン開始時', 'turn_end':'ターン終了時'}[event]))


def summon(battle: Battle, owner: int, entity: Json, modifiers: Json | None = None) -> None:
    # AI_NOTE: 直接召喚・リアニメイト・コピーを共通の登場処理に通す。
    p = battle.state['players'][owner]
    if len(p['board']) >= 5:
        battle.emit('board_full', '盤面上限のため場に出ない')
        return
    for key, value in (modifiers or {}).items():
        if key in {'attack', 'health'}:
            entity[key] += value
            if key == 'health':
                entity['max_health'] += value
        elif key in {'keywords', 'tribes'}:
            entity[key] = list(dict.fromkeys(entity.get(key, []) + value))
        else:
            entity[key] = copy.deepcopy(value)
    entity['entered_turn'] = p['turn']
    p['board'].append(entity)
    battle.reveal(owner, entity)
    battle.emit('summon', f'{entity["name"]}が場に出た', target=entity['id'])
    trigger(battle, 'enter', owner, entity)


def extended_effect(battle: Battle, effect: Json, owner: int, source: Json, chosen: Any) -> bool:
    # AI_NOTE: カード固有名ではなく動作を追加することで、同じ能力を別カードから再利用できる。
    op = effect['op']
    p = battle.state['players'][owner]
    amount = effect.get('amount', 0)
    if op == 'repeat':
        for _ in range(effect['count']):
            battle.resolve(effect['effects'], owner, source, chosen)
    elif op == 'discard':
        for target in battle.targets(effect, owner, source, chosen):
            found = battle.find(target)
            if found and found[0] == owner and found[1] == 'hand':
                entity = found[2]
                p['hand'].remove(entity)
                battle.reveal(owner, entity)
                p['graveyard'] += 1
                battle.emit('discard', f'{entity["name"]}を捨てた', target=target)
                trigger(battle, 'discard', owner, entity)
    elif op in {'pp', 'ep'}:
        p[op] = min(p['max_pp'] if op == 'pp' else 2, p[op]+amount)
        battle.emit(op, f'{op.upper()}を{amount}回復', owner=owner, after=p[op])
    elif op == 'cost':
        found = battle.find(source['id'])
        if found:
            found[2]['cost'] = max(0, found[2]['cost']+amount)
            if found[1] == 'hand':
                battle.update_known_cost(found[0], found[2])
    elif op == 'leader_max':
        p['max_health'] = amount
        p['health'] = min(p['health'], amount)
        battle.emit('leader_max', f'最大体力を{amount}に変更', target=f'leader:{owner}', after=p['health'])
    elif op == 'shield':
        p['damage_shield'] = {'owner': 1-owner, 'turn': battle.state['players'][1-owner]['turn']+1}
        battle.emit('shield', '相手のターン終了までリーダーへのダメージを防ぐ', target=f'leader:{owner}')
    elif op == 'remove_keywords':
        for target in battle.targets(effect, owner, source, chosen):
            found = battle.find(target)
            if found:
                found[2]['keywords'] = [k for k in found[2]['keywords'] if k not in effect['keywords']]
    elif op == 'split_damage':
        remaining = amount
        entities = [e for e in battle.state['players'][1-owner]['board'] if definition(battle, e)['kind'] == 'follower']
        for index, entity in enumerate(entities):
            share = remaining if index == len(entities)-1 else min(remaining, entity['health'])
            battle.damage(entity['id'], share, source)
            remaining -= share
            if not remaining:
                break
    elif op == 'deck_summon':
        seen: set[str] = set()
        for _ in range(effect.get('count', 1)):
            pool = [e for e in p['deck'] if matches(battle, e, effect.get('filter', {})) and (not effect.get('unique') or e['name'] not in seen)]
            if not pool or len(p['board']) >= 5:
                break
            entity = pool[battle.random_index(len(pool))]
            seen.add(entity['name'])
            p['deck'].remove(entity)
            summon(battle, owner, entity)
    elif op == 'reanimate':
        for _ in range(effect.get('count', 1)):
            candidates = [cid for cid in p['destroyed'] if battle.cards[cid]['cost'] <= amount]
            if not candidates or len(p['board']) >= 5:
                break
            maximum = max(battle.cards[cid]['cost'] for cid in candidates)
            candidates = [cid for cid in candidates if battle.cards[cid]['cost'] == maximum]
            summon(battle, owner, battle.fresh(candidates[battle.random_index(len(candidates))]), {'tribes': [6]})
    elif op == 'copy_banish':
        for target in battle.targets(effect, owner, source, chosen):
            found = battle.find(target)
            if found:
                entity = copy.deepcopy(found[2])
                battle.remove(target, 'banish')
                entity['id'] = battle.fresh(entity['card_id'])['id']
                entity['attacks'] = 0
                summon(battle, owner, entity)
    elif op == 'crest':
        who = owner if effect.get('target', 'self') == 'self' else 1-owner
        crests = battle.state['players'][who].setdefault('crests', [])
        crest = copy.deepcopy(effect['crest'])
        if not any(c['id'] == crest['id'] for c in crests):
            crests.append(crest)
            battle.emit('crest', f'{crest["name"]}を付与', owner=who)
    else:
        return False
    return True
