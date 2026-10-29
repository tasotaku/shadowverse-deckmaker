"""2026-09-14の公開40枚構築で使うカードの実行定義。

ランプドラゴンとラストワードナイトメア、および生成先を収録する。
出典・構築枚数・本文の変更検出はカタログ側で管理する。
"""
from __future__ import annotations

from typing import Any

Json = dict[str, Any]


def _effect(op: str, target: str = 'self', **values: Any) -> Json:
    # AI_NOTE: このモジュールはカードの作用を宣言し、状態の変更は共通処理に任せる。
    return {'op': op, 'target': target, **values}


def definitions() -> dict[str, Json]:
    # AI_NOTE: 呼び出しごとに独立した定義を返し、対戦中の変更を次の対戦へ漏らさない。
    e = _effect
    d: dict[str, Json] = {}

    # ランプドラゴン: https://game8.jp/shadowverse-beyond/698541
    d['10403120'] = {  # 空の命運を握る少女・ルリア
        'keywords': ['バリア'], 'enhance': 8,
        'enhance_effects': [e('draw', count=1, filter={'kind': 'follower', 'min_cost': 7}), e('pp', amount=7)],
    }
    d['10644120'] = {  # 旧き天刀・ヴォーラライ
        'keywords': ['必殺'],
        'on_discard': [e('summon', card_id='10644120', count=1)],
        'evolve': [e('generate', card_id='90044330', count=1)],
        'super_evolve': [e('generate', card_id='90044330', count=3)],
    }
    d['10741110'] = {  # 喧伝の龍人
        'keywords': ['突進'], 'enhance': 4,
        'enhance_effects': [e('summon', card_id='10741110', count=2)],
    }
    kimika = [e('discard', 'chosen_hand', choice='hand'), e('draw', count=1), e('heal', 'own_leader', amount=1)]
    d['10842120'] = {'fanfare': kimika, 'evolve': [dict(x) for x in kimika]}  # 笑顔の調理・キミカ
    d['10543310'] = {  # 怠惰なる波揺花: 同じ対象が2回選ばれる可能性がある。
        'effects': [e('repeat', count=2, effects=[e('damage', 'random_enemy', amount=2)]),
                    e('damage', 'enemy_leader', amount=2, condition='awakening')],
    }
    d['10042310'] = {'effects': [e('ramp', amount=1), e('draw', count=1, condition='max_pp10')]}
    d['10742310'] = {'effects': [e('heal', 'own_leader', amount=3), e('draw', count=1, condition='awakening')]}
    d['10542310'] = {'effects': [e('damage', 'all', amount='board_count')]}  # プロミネンスロア
    d['10503310'] = {  # 《世界》の提示
        'effects': [e('draw', count=2), e('destroy', 'random_enemy', filter={'highest_attack': True})],
        'enhance': 10, 'enhance_effects': [e('damage', 'all_enemy_characters', amount=4)],
    }
    d['10444120'] = {  # 世界の味方・ゾーイ
        'fanfare': [e('ramp', amount=1)], 'enhance': 10,
        'enhance_effects': [e('grant', keywords=['疾走']), e('leader_max', amount=1), e('shield')],
    }
    d['10644110'] = {  # 断頭の斬姫・サガツマツ
        'keywords': ['疾走', '必殺', 'オーラ'],
        'fanfare': [e('discard', 'chosen_hand', choice='hand'), e('generate', card_id='10642310', count=2)],
    }
    nomagdala = [[e('draw', count=1), e('heal', 'own_leader', amount=3)], [e('buff', 'all_enemy', attack=0, health=-4)]]
    d['10944120'] = {  # 禁牙の変貌・ノマグダラ
        'keywords': ['守護'], 'modes': {'fanfare': nomagdala, 'evolve': [[dict(x) for x in mode] for mode in nomagdala]},
    }
    d['10844120'] = {  # 金銀絢爛・リュミオール＆アルジャンテ
        'fanfare': [e('discard', 'chosen_hand', choice='hand', select_count=2), e('damage', 'all_enemy_characters', amount=4)],
        'super_evolve': [e('draw', count=3)],
        'forms': {'accelerate': {'kind': 'spell', 'cost': 3, 'keywords': [], 'effects': [e('ramp', amount=1)]}},
    }
    d['10744110'] = {  # 焦灰のアナテマ・バーンドナイト: クレストを相手に持たせる。
        'fanfare': [e('damage', 'all_enemy', amount=9)],
        'super_evolve': [e('crest', 'enemy_leader', crest={
            'id': 'crest:10744112', 'name': 'クレスト：焦灰のアナテマ・バーンドナイト', 'keywords': [],
            'triggers': [
                {'event': 'turn_start', 'scope': 'ally', 'effects': [e('damage', 'own_leader', amount=2)]},
                {'event': 'heal', 'scope': 'ally', 'condition': {'own_turn': True}, 'once_per_turn': True,
                 'effects': [e('damage', 'own_leader', amount=1)]},
            ],
        })],
    }
    d['10544110'] = {  # 律する《正義》・イランツァ: 2枚は重複なしの対象。
        'keywords': ['守護'],
        'evolve': [e('remove_keywords', keywords=['守護']), e('grant', keywords=['威圧'])],
        'end_turn': [
            e('if', condition={'source': 'evolved', 'eq': 0}, effects=[e('damage', 'random_enemy', amount=8, count=2), e('heal', 'own_leader', amount=8)]),
            e('damage', 'enemy_leader', amount=8, condition={'source': 'evolved', 'gte': 1}),
        ],
    }
    d['90044330'] = {  # 天刀の深淵: 使用と捨てた場合の両方で働く。
        'effects': [e('damage', 'enemy_leader', amount=1), e('heal', 'own_leader', amount=1)],
        'on_discard': [e('damage', 'enemy_leader', amount=1), e('heal', 'own_leader', amount=1)],
    }
    d['10642310'] = {  # 赤色流し: 手札と敵場の両対象が必須。
        'effects': [e('discard', 'chosen_hand', choice='hand'), e('destroy', 'chosen_enemy', choice='enemy')],
    }

    # ラストワードナイトメア: https://game8.jp/shadowverse-beyond/811839
    d['10052110'] = {'last_words': [e('generate', card_id='90051120', count=1)]}
    d['10851120'] = {  # キュートな悪魔・リリム
        'attack_effects': [e('damage', 'all_leaders', amount=1)],
        'last_words': [e('generate', card_id='90051120', count=1)],
    }
    d['10751120'] = {  # デーモンドラム・ラズ
        'last_words': [e('summon', card_id='90051110', count=1)],
        'evolve': [e('damage', 'chosen_enemy', amount=3)],
    }
    d['10951120'] = {  # 幽冥の中尉: 召喚先だけが能力を失う。
        'last_words': [e('summon', card_id='10951120', count=1, modifiers={'attack': 1, 'keywords': ['突進'], 'lost_last_words': True})],
    }
    d['10452130'] = {  # 元素の共鳴・バアル
        'modes': {'fanfare': [
            [e('buff', 'random_ally', attack=1, health=1, filter={'exclude_self': True}), e('buff', attack=1, health=1)],
            [e('damage', 'random_enemy', amount=3)],
        ]},
    }
    d['10552110'] = {  # トラブルネクロマンサー: ゴースト、スケルトンの記載順。
        'fanfare': [e('summon', card_id='90051130', count=1), e('summon', card_id='90051110', count=1)],
        'evolve': [e('summon', card_id='90051140', count=1)],
    }
    d['10753310'] = {  # 夜の唱のライブ: ランダム射撃ではなく古い順への割当。
        'effects': [e('split_damage', 'all_enemy', amount=6), e('necro', amount=6, effects=[e('damage', 'enemy_leader', amount=2)])],
    }
    d['10654120'] = {  # 旧き天眼・ビバティー: EPを使わない進化でも誘発する。
        'fanfare': [e('necro', amount=4, effects=[e('evolve')])],
        'on_evolved': [e('generate', card_id='90054330', count=1)],
    }
    tightrope = [e('damage', 'chosen_enemy', amount=3), e('summon', card_id='90051110', count=1)]
    d['10752110'] = {'fanfare': tightrope, 'evolve': [dict(x) for x in tightrope]}
    d['10754110'] = {  # 傍死のアナテマ・徒姫
        'fanfare': [e('deck_summon', count=2, unique=True, filter={'kind': 'follower', 'class_name': 'ナイトメア', 'max_cost': 2})],
        'triggers': [{'event': 'enter', 'scope': 'other_ally', 'filter': {'kind': 'follower', 'class_name': 'ナイトメア'},
                      'effects': [e('grant', 'event', keywords=['突進'])]}],
        'super_evolve': [e('buff', 'all_other_ally', attack=2, health=2, filter={'class_name': 'ナイトメア'})],
    }
    d['10952110'] = {  # 淵底の大佐: 結晶のラストワードと本体のラストワードは別。
        'keywords': ['守護'],
        'last_words': [e('destroy', 'random_enemy'), e('heal', 'own_leader', amount=2)],
        'forms': {'crystallize': {'kind': 'amulet', 'cost': 2, 'attack': 0, 'health': 0, 'keywords': [], 'countdown': 4,
                                  'last_words': [e('summon', card_id='10952110', count=1)]}},
    }
    d['10954110'] = {  # イステンデッドVSマルチルゲート
        'fanfare': [e('reanimate', amount=2, count=3), e('damage', 'all_enemy', amount=2)],
        'super_evolve': [e('crest', crest={
            'id': 'crest:10954112', 'name': 'クレスト：イステンデッドVSマルチルゲート', 'keywords': [],
            'triggers': [{'event': 'turn_end', 'scope': 'ally', 'condition': {'ally_last_words': True},
                          'effects': [e('destroy', 'random_ally', filter={'last_words': True}), e('destroy', 'random_enemy')]}],
        })],
    }
    d['10652310'] = {'effects': [e('copy_banish', 'chosen_enemy')]}  # 『最強』の魅惑
    d['10854110'] = {  # 出発の憧憬・イツルギ＆タケツミ
        'modes': {
            'fanfare': [[e('damage', 'enemy_leader', amount=4), e('heal', 'own_leader', amount=4)],
                        [e('damage', 'all_enemy', amount=5), e('ep', amount=1)]],
            'evolve': [[e('draw', count=2)], [e('pp', amount=2)]],
        },
    }
    d['10954120'] = {  # ガロダートVSゼット
        'hand_triggers': [{'event': 'turn_end', 'scope': 'ally', 'condition': {'player': 'health', 'lte': 12},
                           'effects': [e('cost', amount=-1)]}],
        'modes': {'fanfare': [[e('grant', keywords=['疾走']), e('damage', 'own_leader', amount=2)],
                              [e('grant', keywords=['守護']), e('damage', 'all_enemy', amount=8)]]},
    }
    d['10754120'] = {  # デッドプレゼンター・マクミラン
        'fanfare': [e('necro', amount=10, effects=[e('summon', card_id='90051140', count=3)])],
        'triggers': [{'event': 'enter', 'scope': 'ally', 'filter': {'kind': 'follower', 'tribe': 6},
                      'condition': {'own_turn': True},
                      'effects': [e('buff', 'event', attack=1, health=0, keywords=['突進', '守護']), e('damage', 'enemy_leader', amount=1)]}],
    }
    d['90051120'] = {'keywords': ['ドレイン']}
    d['90051110'] = {'keywords': []}
    d['90051130'] = {'keywords': ['疾走'], 'leave_banish': True, 'end_turn': [e('banish')]}
    d['90051140'] = {'last_words': [e('summon', card_id='90051140', count=1, modifiers={'lost_last_words': True})]}
    d['90054330'] = {'effects': [e('draw', count=2)]}
    return d
