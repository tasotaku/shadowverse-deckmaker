"""【凍結・2026-07-15】戦闘力ベクトルの集計(B3)。card_vschema の効果スキーマ(v5・design.md §11.10)をモード別ベクトルへ畳む。

凍結の理由: ベクトルの価値は「横断スクリーニング・デッキ合算」という使う側で生まれるが、その消費者が
まだ存在しない(ユーザー判断・design.md §11.10末尾)。判定は当面スキーマ(card_vschema)を直接読む。
横断の用途が実際に必要になったら復活を検討する。コードは動く状態のまま残す(mypy strict・テストあり)。

意味の翻訳はLLM(vectorize.pyで保存済み)・ここは算数だけの決定的処理(§11.10 分業の原則)。
旧 strength.py の parse_effect(文字列解析)を置き換え、集計側の設計(モード分け・最低/最高・
発動ターン・除去構造・縦横=§11.2〜11.9)を v5 スキーマ入力で引き継ぐ。

  [card_vschema JSON + card(攻体/コスト)] -> [モード振り分け] -> [種類別に軸へ集計] -> [Mode別ベクトル]
    - モード = 素 / 進化 / 超進化 / エンハンスN / 登場(直接召喚・FF不発でコスト0の別プレイ版)
    - floor=無条件(FF含む)の最低値 / ceiling=条件込みの最高値+条件リスト(§11.2)
    - 変化=最高値にだけ差分上書き(加算しない) / 繰り返しN=×N / X型("X:…")=数値にせず条件へ
    - 非対象(既知limit): お膳立ての枚数N見積り / モード択一の全部盛り解消

実行: python -m svdeck.vector <card_id | card_name> | all
"""

import json
import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from sqlite3 import Connection
from typing import Any

from svdeck.db import connect
from svdeck.strength import cond_turn, load_token_stats

ENHANCE = re.compile(r"エンハンス\(?(\d+)\)?")
DELAY_FLAG = re.compile(r"遅延(\d+)ターン")


@dataclass
class Removal:
    # AI_NOTE: 除去は殺傷力×到達を掛けず・1点に潰さずリストで持つ(§11.7)。strength.Removalとの差分は
    # 幅(kill→kill_max等・変化=覚醒で2→4を1エントリで)と conds(この除去だけを開く条件)を持つこと。
    # kill: ダメージN / "確定"(破壊・消滅・変身) / "確定(戻)"(バウンス) / "X:…"(数える対象)。
    # reach: 命中数(範囲の数×繰り返し) / "全体" / "割振"。kind: スキーマの処理は全て非交戦="一方的"。
    kill: int | str
    reach: int | str
    kind: str
    kill_max: int | str | None = None
    reach_max: int | str | None = None
    conds: list[str] = field(default_factory=list)


@dataclass
class Body:
    # AI_NOTE: 盤面に出る体1種(自身/随伴)の素の姿。合計スタッツ・体数・最大単体はここから導出できるが、
    # 「9/1が1体+1/1が3体」か「3/3が4体」かの分布は合計では復元できないためリストで保持する(2026-07-15ユーザー指摘)。
    name: str
    atk: int
    life: int
    count: int = 1
    conds: list[str] = field(default_factory=list)


@dataclass
class Mode:
    # AI_NOTE: 1プレイ版の強度(strength.Modeと同設計)。floor=無条件の最低値 / ceiling=条件込み最高値。
    # removalsは幅・条件を各エントリが持つので1リスト。notes=その他枠・自傷等の非数値情報(silent禁止の受け皿)。
    label: str
    cost: int
    floor: dict[str, int]
    ceiling: dict[str, int]
    removals: list[Removal]
    flags: set[str]
    supplies: set[str]
    conds: list[str]
    turn_floor: int
    turn_ceiling: int
    disruptions: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    bodies: list[Body] = field(default_factory=list)  # 出る体のリスト(形の保持・合計/縦横の源泉)
    body_count: int = 0  # 横=盤面に出る体数
    max_body: int = 0  # 縦=最大単体の大きさ(攻+体)


@dataclass
class _Acc:
    # AI_NOTE: 1モード分の集計器。floor/ceilingを同時に育て、guaranteed(無条件)の寄与だけfloorにも入れる。
    floor: Counter[str] = field(default_factory=Counter)
    ceiling: Counter[str] = field(default_factory=Counter)
    removals: list[Removal] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    supplies: set[str] = field(default_factory=set)
    disruptions: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    conds: list[str] = field(default_factory=list)
    bodies: list[Body] = field(default_factory=list)
    max_token: int = 0
    self_stat: int = 0

    def add(self, axis: str, value: int, guaranteed: bool) -> None:
        self.ceiling[axis] += value
        if guaranteed:
            self.floor[axis] += value

    def add_conds(self, conds: list[str]) -> None:
        for c in conds:
            if c not in self.conds:
                self.conds.append(c)


def _xnum(value: object, default: int = 0) -> tuple[int, str | None]:
    # AI_NOTE: X型("X:数えるもの")は数値にせず条件へ送る(§11.10)。戻り=(数値, X条件|None)。
    if isinstance(value, bool):
        return default, None
    if isinstance(value, int):
        return value, None
    if isinstance(value, str):
        return 0, value
    return default, None


def _gating(cond: str) -> bool:
    # AI_NOTE: 条件リストには対象制限・持続の注記が混ざる(LLMの癖)。天井を「開く」条件だけをgateとして扱う。
    return not (cond.startswith("対象") or "持続" in cond)


def classify(conds: list[str]) -> tuple[str | tuple[str, int], list[str]]:
    # AI_NOTE: 効果エントリをプレイモードへ(§11.3)。超進化>進化>エンハンス>登場の順で拾い、モードのトリガと
    # FFを除いた残りが「そのモード内で天井を開く条件」。残りが空なら無条件=floor行き。
    for c in conds:
        if "超進化時" in c:
            return "sevo", [r for r in conds if "超進化時" not in r and r != "ファンファーレ"]
    for c in conds:
        if "進化時" in c:
            return "evo", [r for r in conds if "進化時" not in r and r != "ファンファーレ"]
    for c in conds:
        m = ENHANCE.search(c)
        if m:
            return ("enh", int(m.group(1))), [r for r in conds if not ENHANCE.search(r) and r != "ファンファーレ"]
    for c in conds:
        if "直接召喚" in c:
            return "entry", [r for r in conds if "直接召喚" not in r and r != "ファンファーレ"]
    return "base", [r for r in conds if r != "ファンファーレ"]


def _overlay(entry: dict[str, Any], henka: dict[str, Any] | list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    # AI_NOTE: 変化=置き換え(§11.10)。書かないフィールドは基本を引き継ぐ。効果はキー単位でマージ・
    # 他のフィールド(対象/範囲/何枚等)は丸ごと差し替え。段階型(リスト)は順に重ねる=最終段が最大。条件は全段の和。
    merged = dict(entry)
    conds: list[str] = []
    for stage in henka if isinstance(henka, list) else [henka]:
        for key, value in stage.items():
            if key == "条件":
                conds.extend(c for c in value if c not in conds)
            elif key == "効果":
                merged["効果"] = {**merged.get("効果", {}), **value}
            else:
                merged[key] = value
    return merged, conds


def _hits(entry: dict[str, Any]) -> tuple[int | str, list[str]]:
    # AI_NOTE: 範囲×繰り返しを命中数へ。選択N/ランダムN=N×繰り返し・全体="全体"・割り振り="割振"。
    rep, x_rep = _xnum(entry.get("繰り返し", 1), default=1)
    conds = [x_rep] if x_rep else []
    rng = entry.get("範囲")
    if rng is None:
        return max(rep, 1), conds
    kind = str(rng.get("型"))
    if kind.startswith("全体"):
        return "全体", conds
    if kind == "割り振り":
        return "割振", conds
    n, x_n = _xnum(rng.get("数", 1), default=1)
    if x_n:
        conds.append(x_n)
    return max(n, 1) * max(rep, 1), conds


def _damage_amount(entry: dict[str, Any]) -> tuple[int, str | None]:
    # AI_NOTE: 1回あたりのダメージ量。割り振りは総量が本体(効果側のXと同値のことが多い)なので総量を優先。
    rng = entry.get("範囲")
    if rng is not None and rng.get("型") == "割り振り":
        return _xnum(rng.get("総量", entry.get("効果", {}).get("ダメージ", 0)))
    return _xnum(entry.get("効果", {}).get("ダメージ", 0))


def _face_damage(entry: dict[str, Any], targets: list[str]) -> tuple[int, bool, list[str]]:
    # AI_NOTE: リーダーダメージ軸への寄与(§11.9 本体分)。リーダー単独対象=確定(floor可)。フォロワーと
    # 統合された対象(シャクドウ/サンダルフォン型)は全弾顔想定の最高値のみ=ceiling行き。和は取らないので
    # 除去リストとの二重計上にならない(§11.4 軸は独立に持つ)。
    dmg, x_dmg = _damage_amount(entry)
    conds = [x_dmg] if x_dmg else []
    hits, hit_conds = _hits(entry)
    conds.extend(hit_conds)
    only_leader = targets == ["相手リーダー"]
    if isinstance(hits, int):
        total = dmg * hits
    elif hits == "割振":
        total = dmg  # 総量そのもの(全部顔へ振った想定)
    else:  # 全体=リーダーは1回ずつ
        rep, _ = _xnum(entry.get("繰り返し", 1), default=1)
        total = dmg * max(rep, 1)
    if not only_leader:
        conds.append("顔へ全弾想定")
    return total, only_leader, conds


def _removal_of(entry: dict[str, Any]) -> tuple[int | str, int | str] | None:
    # AI_NOTE: 処理エントリ1つ分の除去(殺傷力, 到達)。確定除去>ダメージ>体マイナス(貫通)の順で採る。
    eff = entry.get("効果", {})
    hits, _ = _hits(entry)
    if eff.get("除去") in ("破壊", "消滅", "変身"):
        return "確定", hits
    if eff.get("除去") == "バウンス":
        return "確定(戻)", hits
    dmg, x_dmg = _damage_amount(entry)
    if x_dmg:
        return x_dmg, hits
    if dmg > 0:
        return dmg, hits
    life, x_life = _xnum(eff.get("体", 0))
    if life < 0:
        return -life, hits  # 体−=貫通(バリア無視・rules.md)だがphase-1では殺傷力Nと同列に持つ
    if x_life:
        return x_life, hits
    return None


def _apply_process(acc: _Acc, entry: dict[str, Any], conds: list[str], guaranteed: bool) -> None:
    # AI_NOTE: B処理の本体。基本値でfloor/ceilingを作り、変化があれば最高値側だけ差し替え版で作り直す
    # (加算しない=置換の最大化・§11.10)。変化の条件はそのエントリの天井条件に合流する。
    henka = entry.get("変化")
    if henka is None:
        _apply_process_once(acc, entry, conds, guaranteed, ceiling_only=False)
        return
    changed, henka_conds = _overlay(entry, henka)
    _apply_process_once(acc, entry, conds, guaranteed, ceiling_only=False, floor_only=True)
    _apply_process_once(acc, changed, conds + henka_conds, guaranteed=False, ceiling_only=True,
                        base_for_span=entry)


def _apply_process_once(
    acc: _Acc,
    entry: dict[str, Any],
    conds: list[str],
    guaranteed: bool,
    ceiling_only: bool,
    floor_only: bool = False,
    base_for_span: dict[str, Any] | None = None,
) -> None:
    # AI_NOTE: 対象の自/相手×リーダー/フォロワー/自身で軸を振り分ける(表現は統合・意味の振り分けは下流=§11.10)。
    # floor_only=変化の基本側(ceilingは変化版が担う)。base_for_span=変化版の除去を基本値との幅1エントリに畳む。
    targets: list[str] = entry.get("対象", [])
    eff: dict[str, Any] = entry.get("効果", {})
    rep, _ = _xnum(entry.get("繰り返し", 1), default=1)
    rep = max(rep, 1)
    gate = [c for c in conds if _gating(c)]
    sure = guaranteed and not gate

    def put(axis: str, value: int) -> None:
        if floor_only:
            if sure:
                acc.floor[axis] += value
            return
        if ceiling_only:
            acc.ceiling[axis] += value
            return
        acc.add(axis, value, sure)

    if "相手リーダー" in targets:
        total, only_leader, face_conds = _face_damage(entry, targets)
        if total:
            put("リーダーダメージ", total)
            if not (sure and only_leader):
                acc.add_conds(gate + [c for c in face_conds if not only_leader or c.startswith("X:")])
    heal, x_heal = _xnum(eff.get("回復", 0))
    if ("自リーダー" in targets or "自フォロワー" in targets) and (heal or x_heal):
        put("回復・軽減", heal * rep)
        acc.add_conds(gate + ([x_heal] if x_heal else []))
    if "自身" in targets:
        _apply_to_self(acc, entry, eff, put, gate)
    if "自フォロワー" in targets:
        _supply_to_allies(acc, eff, gate)
    if any(t.startswith("相手") and t != "相手リーダー" for t in targets):
        _apply_to_enemies(acc, entry, eff, gate, ceiling_only, floor_only, sure, base_for_span)
    if "自アミュレット" in targets and eff.get("除去"):
        acc.notes.append(f"自アミュレット{eff['除去']}(コスト/起動)")
        acc.add_conds(gate)


def _apply_to_self(
    acc: _Acc, entry: dict[str, Any], eff: dict[str, Any], put: Callable[[str, int], None], gate: list[str]
) -> None:
    # AI_NOTE: 対象=自身。スタッツは縦を伸ばし、特性はフラグへ、自身バウンス=手札+1(サンダルフォン)、
    # 自傷・自壊はコスト扱いでnotesへ(軸に負で載せない=phase-1はstrength.pyと同じ扱い)。
    atk, x_atk = _xnum(eff.get("攻", 0))
    life, x_life = _xnum(eff.get("体", 0))
    if atk or life:
        put("攻撃力", atk)
        put("体力", life)
        acc.self_stat += atk + life
        acc.add_conds(gate)
    if x_atk or x_life:
        acc.add_conds(gate + [c for c in (x_atk, x_life) if c])
    for kw in eff.get("特性付与", []):
        acc.flags.add(kw)
    if eff.get("除去") == "バウンス":
        put("カード枚数", 1)  # 自身が手札に戻る=手札+1
    elif eff.get("除去"):
        acc.notes.append(f"自身{eff['除去']}(コスト)")
    dmg, _ = _xnum(eff.get("ダメージ", 0))
    if dmg:
        acc.notes.append(f"自傷{dmg}")


def _supply_to_allies(acc: _Acc, eff: dict[str, Any], gate: list[str]) -> None:
    # AI_NOTE: 他の味方への付与=供給フラグ(値は相方次第で固定数字にしない・§11.7)。条件は情報として残す。
    if eff:
        acc.add_conds(gate)
    atk, _ = _xnum(eff.get("攻", 0))
    life, _ = _xnum(eff.get("体", 0))
    if atk or life:
        acc.supplies.add("スタッツ")
    for kw in eff.get("特性付与", []):
        acc.supplies.add(f"{kw}付与")
    if eff.get("除去"):
        acc.notes.append(f"自フォロワー{eff['除去']}(コスト)")
    heal, _ = _xnum(eff.get("回復", 0))
    if heal:
        acc.supplies.add("回復")


def _apply_to_enemies(
    acc: _Acc,
    entry: dict[str, Any],
    eff: dict[str, Any],
    gate: list[str],
    ceiling_only: bool,
    floor_only: bool,
    sure: bool,
    base_for_span: dict[str, Any] | None,
) -> None:
    # AI_NOTE: 相手の体(フォロワー/アミュレット)への処理=除去エントリへ。無条件でない除去はcondsを自身に持つ
    # (§11.2 各増分に条件を添える)。変化版はbase側と1エントリに畳み kill→kill_max の幅にする(2→4)。
    removal = _removal_of(entry)
    if removal is not None:
        kill, reach = removal
        if ceiling_only and base_for_span is not None:
            base = _removal_of(base_for_span)
            if base is not None and acc.removals and acc.removals[-1].kill == base[0]:
                last = acc.removals[-1]
                last.kill_max = kill if kill != last.kill else None
                last.reach_max = reach if reach != last.reach else None
                for c in gate:
                    if c not in last.conds:
                        last.conds.append(c)
                acc.add_conds(gate)
                return
        if not floor_only or sure:
            acc.removals.append(Removal(kill, reach, "一方的", conds=list(gate) if not sure else []))
            acc.add_conds(gate)
    atk, _ = _xnum(eff.get("攻", 0))
    if atk < 0:
        acc.disruptions.add(f"攻{atk}デバフ")
    for kw in eff.get("特性付与", []):
        acc.disruptions.add(f"相手へ{kw}")


def _apply_escort(acc: _Acc, entry: dict[str, Any], gate: list[str], sure: bool,
                  tokens: dict[str, tuple[int, int]]) -> None:
    # AI_NOTE: 随伴=別の体が場に出る。名前解決でスタッツを足す(トークン版優先=strength.load_token_stats)。
    # 出る体のFF・エンハンスは不発なので素のスタッツと特性のみ数える(FF不発の規律・§11.7)。
    name = str(entry.get("何を", "")).strip("『』「」")
    count, x_count = _xnum(entry.get("数", 1), default=1)
    count = max(count, 1)
    if x_count:
        acc.add_conds(gate + [x_count])
    grant = entry.get("付与", {}) or {}
    if name not in tokens:
        acc.flags.add(f"随伴({name})")  # リアニメイトN等の選択条件=構築次第・固定スタッツを置かない(§11.7)
        acc.add_conds(gate)
        return
    atk, life = tokens[name]
    g_atk, _ = _xnum(grant.get("攻", 0))
    g_life, _ = _xnum(grant.get("体", 0))
    atk, life = atk + g_atk, life + g_life
    acc.add("攻撃力", atk * count, sure)
    acc.add("体力", life * count, sure)
    acc.bodies.append(Body(name, atk, life, count, list(gate)))
    acc.max_token = max(acc.max_token, atk + life)
    for kw in grant.get("特性", []):
        acc.flags.add(f"随伴に{kw}")
    acc.add_conds(gate)


def _apply_entry(acc: _Acc, entry: dict[str, Any], residual: list[str],
                 tokens: dict[str, tuple[int, int]]) -> None:
    # AI_NOTE: 種類別ディスパッチ。gate条件が残るエントリはceilingのみ・無条件はfloorにも入る。
    gate = [c for c in residual if _gating(c)]
    sure = not gate
    kind = entry["種類"]
    if kind == "処理":
        _apply_process(acc, entry, residual, guaranteed=True)
    elif kind == "随伴":
        _apply_escort(acc, entry, gate, sure, tokens)
    elif kind == "リソース":
        _apply_resource_gain(acc, entry, gate, sure)
    elif kind in ("手札処理", "デッキ処理"):
        eff = entry.get("効果", {})
        desc = " ".join(f"{k}{v}" for k, v in eff.items())
        acc.supplies.add(f"{kind}({entry.get('対象')}: {desc})")
        acc.add_conds(gate)
    elif kind == "クレスト":
        _apply_crest(acc, entry, gate, tokens)
    elif kind == "資源":
        _apply_resource(acc, entry, sure, gate)
    elif kind == "その他":
        acc.notes.append(str(entry.get("記述", "")))
        acc.add_conds(gate)


def _resource_delta(entry: dict[str, Any]) -> tuple[str, int, list[str]]:
    # AI_NOTE: 引く=実カード(カード枚数)/生成=トークン(トークン生成軸)。トークンは価値が実カードと別物なので
    # 同じ軸に混ぜない(2026-07-15ユーザー決定・案A)。X型は数値にせず条件へ。
    n, x_n = _xnum(entry.get("何枚", 1), default=1)
    axis = "カード枚数" if entry.get("動作") == "引く" else "トークン生成"
    return axis, (max(n, 1) if not x_n else 0), ([x_n] if x_n else [])


def _apply_resource_gain(acc: _Acc, entry: dict[str, Any], gate: list[str], sure: bool) -> None:
    # AI_NOTE: 変化(置き換え)はリソースにも効く(花園の導き「1枚ではなく2枚」)。基本値=floor・
    # 変化を上書きした値=ceilingで、処理(B)と同じ「最高値にだけ差分上書き・加算しない」の規律。
    henka = entry.get("変化")
    axis, n, x_conds = _resource_delta(entry)
    if henka is None:
        acc.add(axis, n, sure)
        acc.add_conds(gate + x_conds)
    else:
        changed, henka_conds = _overlay(entry, henka)
        c_axis, c_n, c_x_conds = _resource_delta(changed)
        if sure:
            acc.floor[axis] += n
        acc.ceiling[c_axis] += c_n
        acc.add_conds(gate + x_conds + henka_conds + c_x_conds)
    made = entry.get("生成対象") or entry.get("変身先")
    if made:
        acc.supplies.add(f"生成:{made}")  # お膳立て(§11.9)の型。枚数Nの見積りは非対象
    drew = entry.get("何を")
    if drew:
        acc.notes.append(f"引くフィルタ:{drew}")  # サーチ対象=構築文脈で効く情報(§11.10)。値化しない


def _apply_crest(acc: _Acc, entry: dict[str, Any], gate: list[str],
                 tokens: dict[str, tuple[int, int]]) -> None:
    # AI_NOTE: クレスト=遅延つきのネスト効果(§11.7 モードでなく時間差)。カウントダウンNは遅延Nターンフラグ、
    # 中身のB処理は遅延条件つきで同モードへ集計。相手へのクレストは妨害枠。
    if entry.get("対象") == "相手":
        acc.disruptions.add("相手へクレスト")
        return
    countdown = entry.get("カウントダウン")
    delay, _ = _xnum(countdown, default=0) if countdown not in (None, "無") else (0, None)
    if delay:
        acc.flags.add(f"遅延{delay}ターン")
    nested: list[dict[str, Any]] = entry.get("効果") or []
    if not nested:
        acc.notes.append("クレスト獲得(内容は別カード参照)")
        acc.add_conds(gate)
        return
    for sub in nested:
        sub_conds = gate + [c for c in sub.get("条件", []) if c != "ファンファーレ"]
        _apply_process(acc, {**sub, "条件": sub_conds}, sub_conds, guaranteed=True)


def _apply_resource(acc: _Acc, entry: dict[str, Any], sure: bool, gate: list[str]) -> None:
    # AI_NOTE: 資源=貯める燃料(§11.10)。PP/進化権/超進化権は消費と相殺できる軸へ直接、他は{種類}産出へ。
    amount, x_amount = _xnum(entry.get("量", 0))
    kind = str(entry.get("資源種類"))
    if x_amount:
        acc.add_conds(gate + [x_amount])
        return
    if kind == "PP":
        acc.add("PP", -amount, sure)  # PP回復=実コストの相殺(負が得)
    elif kind in ("進化権", "超進化権"):
        acc.add(kind, amount, sure)
    else:
        acc.add(f"{kind}産出", amount, sure)
    acc.add_conds(gate)


def _mode_specs(
    groups: dict[str | tuple[str, int], list[tuple[dict[str, Any], list[str]]]], cost: int
) -> list[tuple[str, int, str | tuple[str, int], str | None]]:
    # AI_NOTE: (ラベル, 実コスト, グループキー, 消費する権利)。登場=非手札プレイのコスト0版(§11.10)。
    specs: list[tuple[str, int, str | tuple[str, int], str | None]] = [("素", cost, "base", None)]
    if groups.get("evo"):
        specs.append(("進化", cost, "evo", "進化権"))
    if groups.get("sevo"):
        specs.append(("超進化", cost, "sevo", "超進化権"))
    for n in sorted(key[1] for key in groups if isinstance(key, tuple)):
        specs.append((f"エンハンス{n}", n, ("enh", n), None))
    if groups.get("entry"):
        specs.append(("登場", 0, "entry", None))
    return specs


def evaluate_card(conn: Connection, card_id: int, tokens: dict[str, tuple[int, int]]) -> tuple[str, list[Mode]]:
    # AI_NOTE: カード1枚をモード別ベクトルへ。素スタッツ/コストはDBの確定値・効果はcard_vschemaのv5スキーマ。
    row = conn.execute("SELECT name, cost, atk, life, type_category FROM card WHERE card_id = ?", (card_id,)).fetchone()
    if row is None:
        raise ValueError(f"card_id {card_id} は存在しない")
    name, cost, atk, life, type_category = row
    vrow = conn.execute("SELECT schema_json FROM card_vschema WHERE card_id = ?", (card_id,)).fetchone()
    if vrow is None:
        raise ValueError(f"card_id {card_id} は card_vschema 未抽出")
    schema: dict[str, Any] = json.loads(vrow[0])

    groups: dict[str | tuple[str, int], list[tuple[dict[str, Any], list[str]]]] = {}
    entry_conds: list[str] = []
    for e in schema.get("効果", []):
        if e["種類"] == "登場":
            entry_conds = [c for c in e.get("条件", []) if _gating(c)]
            groups.setdefault("entry", [])
            continue
        key, residual = classify(e.get("条件", []))
        groups.setdefault(key, []).append((e, residual))

    body = schema.get("自身") or {}
    traits: list[str] = body.get("特性", [])
    modes: list[Mode] = []
    for label, mode_cost, key, spent_evo in _mode_specs(groups, cost):
        acc = _Acc()
        if type_category == "follower":
            acc.add("攻撃力", atk, guaranteed=True)
            acc.add("体力", life, guaranteed=True)
            acc.bodies.append(Body("自身", atk, life))
            acc.self_stat = atk + life
        acc.add("PP", mode_cost, guaranteed=True)
        if label != "登場":  # 登場=手札を使わない(デッキから直接出る)ので手札-1を課さない
            acc.add("カード枚数", -1, guaranteed=True)
        if spent_evo is not None:
            acc.add(spent_evo, -1, guaranteed=True)
        acc.flags.update(traits)
        entries = list(groups.get("base", [])) if label != "登場" else []
        if key != "base":
            entries += groups.get(key, [])
        for e, residual in entries:
            _apply_entry(acc, e, residual, tokens)
        conds = entry_conds if label == "登場" else acc.conds
        if any("融合" in c for c in conds):
            # AI_NOTE: 融合=手札のカードを素材として消費する(最低1枚・実枚数は手札次第)。融合条件の効果は
            # 天井側なので素材消費も天井にだけ-1で計上する(2026-07-15ユーザー指摘)。
            acc.ceiling["カード枚数"] -= 1
            acc.notes.append("融合素材:手札-1(最低・実枚数は手札次第)")
        turn_floor = max(mode_cost, 1)
        if spent_evo == "進化権":
            turn_floor = max(turn_floor, 5)  # 進化=先攻T5(rules.md)
        elif spent_evo == "超進化権":
            turn_floor = max(turn_floor, 7)  # 超進化=先攻T7(rules.md)
        delays = [int(m.group(1)) for f in acc.flags if (m := DELAY_FLAG.match(f))]
        turn_ceiling = max([turn_floor] + [cond_turn(c) for c in conds]) + (max(delays) if delays else 0)
        modes.append(
            Mode(label, mode_cost, dict(acc.floor), dict(acc.ceiling), acc.removals, acc.flags,
                 acc.supplies, conds, turn_floor, turn_ceiling, acc.disruptions, acc.notes,
                 acc.bodies, sum(b.count for b in acc.bodies), max(acc.self_stat, acc.max_token))
        )
    return str(name), modes


def _format_vector(floor: dict[str, int], ceiling: dict[str, int]) -> str:
    parts = []
    for axis in ceiling:
        lo, hi = floor.get(axis, 0), ceiling[axis]
        if not (lo or hi):
            continue
        parts.append(f"{axis}:{lo}→{hi}" if lo != hi else f"{axis}:{hi}")
    return "  ".join(parts)


def _format_removal(r: Removal) -> str:
    kill = f"{r.kill}→{r.kill_max}" if r.kill_max is not None else f"{r.kill}"
    reach = f"{r.reach}→{r.reach_max}" if r.reach_max is not None else f"{r.reach}"
    cond = f" ({'・'.join(r.conds)})" if r.conds else ""
    return f"{{殺傷力:{kill} 到達:{reach} {r.kind}{cond}}}"


def _print_card(conn: Connection, card_id: int, tokens: dict[str, tuple[int, int]]) -> None:
    name, modes = evaluate_card(conn, card_id, tokens)
    print(f"■ {name} (card_id={card_id})")
    for m in modes:
        turn = f"T{m.turn_floor}" if m.turn_ceiling == m.turn_floor else f"T{m.turn_floor}→{m.turn_ceiling}"
        print(f"  [{m.label} PP{m.cost} 発動{turn}] {_format_vector(m.floor, m.ceiling)}")
        if m.bodies:
            shapes = ", ".join(
                f"{b.name}{b.atk}/{b.life}" + (f"×{b.count}" if b.count > 1 else "")
                + (f"({'・'.join(b.conds)})" if b.conds else "")
                for b in m.bodies
            )
            print(f"      盤面: 体数{m.body_count}(横) 最大単体{m.max_body}(縦) [{shapes}]")
        if m.removals:
            print(f"      除去: {[_format_removal(r) for r in m.removals]}")
        if m.flags:
            print(f"      フラグ: {sorted(m.flags)}")
        if m.supplies:
            print(f"      供給(相方次第): {sorted(m.supplies)}")
        if m.disruptions:
            print(f"      妨害: {sorted(m.disruptions)}")
        if m.conds:
            print(f"      発動条件(天井を開く): {m.conds}")
        if m.notes:
            print(f"      注記: {m.notes}")


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口。card_id/カード名で1枚、all で card_vschema 保存済み全件を表示。
    args = sys.argv[1:]
    if not args:
        print("usage: python -m svdeck.vector <card_id | card_name> | all")
        sys.exit(1)
    conn = connect()
    try:
        tokens = load_token_stats(conn)
        if args[0] == "all":
            for (cid,) in conn.execute("SELECT card_id FROM card_vschema ORDER BY card_id"):
                _print_card(conn, cid, tokens)
            return
        column = "card_id" if args[0].isdigit() else "name"
        value: int | str = int(args[0]) if args[0].isdigit() else args[0]
        row = conn.execute(f"SELECT card_id FROM card WHERE {column} = ?", (value,)).fetchone()
        if row is None:
            print(f"見つからない: {args[0]}")
            sys.exit(1)
        _print_card(conn, row[0], tokens)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
