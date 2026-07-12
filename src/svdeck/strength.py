"""戦闘力ベクトル(カード強度の数値化)。design.md §11 のフェーズ1(ベクトル化)を実装する。

カード1枚を**モード分離**した強度へ変換する。モード = 素 / 進化 / 超進化 / エンハンスN。
コストと効果が常にセットで動く版を別ベクトルで持つ(§11.3)。各モードは最低値→最高値の幅と、
最高値を開く発動条件を保持する(§11.2 伸びしろは発動条件付き)。

軸(§11.3): 攻撃力 / 体力 / リーダーダメージ / 回復・軽減 / カード枚数 / PP(実コスト) /
進化権 / 超進化権 / {カウンタ資源}産出。除去は「殺傷力 × 到達」を掛けずリストで持つ(§11.7)。
コストで正規化しない(§11.1)。軸間の重み付け(スカラー化)はフェーズ2で、ここではやらない(§11.4)。

  [card + card_atom(atoms_json)] -> [classify: requiresでモード分類] -> [build_vector: 軸へ集計]
    - I/O境界: cards.db(read-only) / 出力: モード別ベクトルのdataclass
    - 対象外(TODO・§11.8残ギャップ): バフの他対象パース(バフ他)・ダメージの対象不明(ダメージ?)・
      進化/自動進化の値化・位置指定召喚。これらは語彙追加でなく設計判断が要るのでフェーズ2へ。

実行: python -m svdeck.strength <card_id | card_name>
"""

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from sqlite3 import Connection

from svdeck.db import connect

# AI_NOTE: 符号付き産出量として軸化するカウンタ資源(§11.7)。headがこの語で始まればcnt軸へ。
COUNTER_RESOURCES = ("スペルブースト", "土の印", "信仰", "カウンタ", "PP最大", "墓場")
# AI_NOTE: 生存キーワード。数値でなくフラグでベクトルに載せ、価値の重みはフェーズ2(§11.7)。
SURVIVAL_KEYWORDS = frozenset({"守護", "潜伏", "オーラ", "バリア", "威圧"})
# AI_NOTE: 妨害。数が少ないので専用軸を作らず、phase-1では軸へ載せない(その他枠はフェーズ2で§11.7)。
DISRUPTION_KEYWORDS = frozenset({"守護剥奪", "能力剥奪", "行動制限", "手札破棄", "デバフ", "行動制限付与", "体力設定"})

ENHANCE = re.compile(r"エンハンス\((\d+)\)")


@dataclass
class Removal:
    # AI_NOTE: 除去を掛け算で1数字に潰さない(§11.7)。殺傷力と到達を別フィールドで保持する。
    # kill: ダメージN(体力N以下を処理) または "確定"/"確定(戻)"(破壊・消滅・変身・バウンス=サイズ無制限)。
    # reach: 単体=1 / 反復K=K / "全体" / "割振"(盤面体数は掛けない)。kind: "一方的"(スペル除去)。
    # 交戦(突進・必殺で体を差し出す)はphase-1では扱わずキーワードフラグに留める(§11.7)。
    kill: int | str
    reach: int | str
    kind: str


@dataclass
class Effect:
    # AI_NOTE: parse_effectの戻り。kindで判別する軽量ユニオン(mypy strictで扱いやすいよう単一dataclassに集約)。
    # num/numR=軸への加算(numRは置換なので後で最大化)・num2=自己スタッツ・cnt=カウンタ産出・
    # rem=除去・flag=キーワード・sup=他味方への供給・delay=カウントダウン(遅延Nターン)・skip=未解決。
    kind: str
    axis: str = ""
    value: int = 0
    atk: int = 0
    life: int = 0
    count: int = 0
    removal: Removal | None = None
    label: str = ""


@dataclass
class Mode:
    # AI_NOTE: 1プレイ版の強度。cost=実コストPP。floor=無条件で出る分・ceiling=発動条件込みの最大(§11.2)。
    # conds=ceilingを開く発動条件(§4.2の希少度=天井の難度)。unresolvedは826枚監査用の未解決効果ログ。
    label: str
    cost: int
    floor: dict[str, int]
    ceiling: dict[str, int]
    removals: list[Removal]
    flags: set[str]
    supplies: set[str]
    conds: list[str]
    turn_floor: int  # 発動ターン: このモードを出せる最速ターン(§11.9・実コスト＋進化ルール)
    turn_ceiling: int  # 天井が開くターン。ルール確定の条件のみ底上げ・デッキ依存条件は据え置きの下限(§11.9)
    disruptions: set[str] = field(default_factory=set)
    unresolved: list[str] = field(default_factory=list)
    body_count: int = 0  # 横=盤面に出る体数
    max_body: int = 0  # 縦=最大単体の大きさ(攻+体)


def _enemy(target: str) -> bool:
    return "相手" in target or "敵" in target


def _is_self(target: str) -> bool:
    # AI_NOTE: 自己スタッツ判定。「他」を含むと他フォロワー対象なので自己から除外する。
    return ("自身" in target or "これ" in target) and "他" not in target


def _own_other(target: str) -> bool:
    # AI_NOTE: 自陣の他の味方が対象=供給(相方次第で値が決まる・§11.7 他の味方へのバフは供給フラグ)。
    return any(k in target for k in ("自場", "味方", "自分の")) and not _is_self(target)


def _reach(target: str) -> int | str:
    return "全体" if ("すべて" in target or "全体" in target) else 1


def _split_top(text: str) -> list[str]:
    # AI_NOTE: ∧はトップレベル(括弧の外)のみで分割(§前回のfixの回帰対策)。括弧内の∧は付与能力等の引数の一部で、
    # 分割すると括弧が壊れる(例「能力付与(A∧B)」)。深さ0の∧だけで区切り、空片は捨てる。
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in text:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        if ch == "∧" and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _first_int(parts: list[str], default: int = 1) -> int:
    # AI_NOTE: 引数リストから最初の整数を拾う(符号付き可)。無ければdefault。数値未指定の効果向け。
    for part in parts:
        cleaned = part.strip().lstrip("+")
        if cleaned.lstrip("-").isdigit():
            return int(cleaned)
    return default


def load_token_stats(conn: Connection) -> dict[str, tuple[int, int]]:
    # AI_NOTE: 召喚体解決用の全カード名→(攻,体)。同名はトークン版(is_token=1)を優先=実際に場に出る版を採る。
    stats: dict[str, tuple[int, int]] = {}
    for name, atk, life, is_token in conn.execute("SELECT name, atk, life, is_token FROM card WHERE atk IS NOT NULL"):
        if name not in stats or is_token == 1:
            stats[name] = (atk or 0, life or 0)
    return stats


def parse_effect(text: str, tokens: dict[str, tuple[int, int]]) -> Effect:
    # AI_NOTE: 効果文1つを型付き量へ。head=先頭語・args=括弧内の引数。"ではなく"/"置換"は最高値を開く置換で、
    # 足さず後で最大化する(§11.7)。分岐順は具体的なhead一致を先に、汎用のカウンタ資源判定を最後に置く。
    if "勝利のカード" in text:  # 特殊勝利=勝ちライン20点に載せる(§11.9・826枚中マゼルベイン1枚のみ)
        return Effect("num", axis="リーダーダメージ", value=20)
    replace = ("ではなく" in text) or ("置換" in text)
    head_match = re.match(r"\s*([^\(（,]+)", text)
    if not head_match:
        return Effect("skip", label="?")
    head = head_match.group(1).strip()
    paren = re.search(r"[\(（]([^\)）]*)[\)）]", text)
    args = [a.strip() for a in re.split(r"[,、]", paren.group(1))] if paren else []
    target = args[0] if args else ""

    def numbered(axis: str, val: int) -> Effect:
        return Effect("numR", axis=axis, value=val) if replace else Effect("num", axis=axis, value=val)

    if head == "ダメージ":
        # AI_NOTE: 対象に「相手」明記が無いバーンも多い(例「体力最小のリーダーに3」)。リーダー/フォロワーは
        # 「自」が付かなければ相手既定で顔/盤面に振る。「自(分の)」明記のみ自傷として非計上(§11.8 対象パース)。
        n = _first_int(args)
        if "リーダー" in target and "自" not in target:
            return numbered("リーダーダメージ", n)
        if "自" not in target and ("フォロワー" in target or "場" in target or _enemy(target)):
            return Effect("rem", removal=Removal(kill=n, reach=_reach(target), kind="一方的"))
        return Effect("skip", label="ダメージ?")
    if head in ("ダメージ割りふり", "ダメージ割り振り", "ダメージ割振"):
        return Effect("rem", removal=Removal(kill=_first_int(args), reach="割振", kind="一方的"))
    if head == "回復":
        return numbered("回復・軽減", _first_int(args))
    if head == "EP回復":  # 進化権の回復=符号付き産出+N(§11.3・spent_evoの消費-1と相殺しうる)
        return Effect("num", axis="進化権", value=_first_int(args))
    if head in ("ドロー", "サーチ"):
        return Effect("num", axis="カード枚数", value=1)
    if head == "手札生成":
        return Effect("num", axis="カード枚数", value=_first_int(args[1:]) if len(args) > 1 else 1)
    if head == "捨てる":
        return Effect("setup", label="コスト")
    if head == "バフ":
        stat = re.search(r"([+\-]?\d+)\s*/\s*([+\-]?\d+)", text)
        if stat and _is_self(target):
            return Effect("selfstat", atk=int(stat.group(1)), life=int(stat.group(2)))
        if stat and _own_other(target):
            return Effect("sup", label="スタッツ")
        return Effect("skip", label="バフ他")  # TODO: 他対象の値化(§11.8残ギャップ48件)
    if head in ("破壊", "消滅", "変身"):
        if _enemy(target):
            return Effect("rem", removal=Removal(kill="確定", reach=_reach(target), kind="一方的"))
        return Effect("setup", label="コスト")
    if head in ("バウンス", "手札に戻す", "手札を山札に戻す"):  # 手札に戻す系=バウンス扱い(§11.8残ギャップ)
        if _enemy(target):
            return Effect("rem", removal=Removal(kill="確定(戻)", reach=_reach(target), kind="一方的"))
        return Effect("setup", label="コスト")
    if head in ("コスト減", "PP回復"):
        return Effect("num", axis="PP", value=-abs(_first_int(args)))
    if head in ("トークン召喚", "召喚"):  # 全カード名で解決(『』「」除去)・FF不発は素性(スタッツ)のみ数えるので織込済(§11.7)
        name = (args[0] if args else "").strip("『』「」")
        count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
        if name in tokens:
            atk, life = tokens[name]
            return Effect("summon", atk=atk, life=life, count=count)  # 縦/横用に1体分と体数を分けて返す
        return Effect("skip", label=f"召喚?{name[:8]}")  # TODO: 位置指定召喚(§11.8残ギャップ21件)
    if head == "リアニメイト":
        return Effect("flag", label="リアニメイト")  # 蘇生対象は構築次第=固定スタッツを置かずフラグのみ(§11.7)
    if head == "カウントダウン":  # カウントダウン(N)=遅延Nターンフラグ(§11.7 モードでなく時間差)
        return Effect("delay", count=_first_int(args))
    if head.startswith("カウントダウン") or head == "クレスト付与":  # カウントダウン-1/クレスト=発動のお膳立て(setup)
        return Effect("setup", label=head)
    if head in SURVIVAL_KEYWORDS or head in ("疾走", "突進", "必殺", "ドレイン", "追加攻撃権"):
        return Effect("flag", label=head)  # 攻撃予算の使い道を開くフラグ(二重計上しない・§11.7)
    if head in DISRUPTION_KEYWORDS:
        return Effect("disr", label=head)
    if head.endswith("付与"):
        return Effect("sup", label=head[:-2])  # 他の体へキーワードを渡す=供給(相方次第・§11.7)
    if head in ("対象選択", "選択", "モード", "対象選択なし"):
        return Effect("struct", label=head)  # 構造=値でない・軸に載せない(§11.7)
    for resource in COUNTER_RESOURCES:
        if head.startswith(resource):
            return Effect("cnt", axis=resource, count=_first_int(args) if args else 1)
    soil = re.search(r"土の印を\+?(\d+)", head)  # 「自分の場の土の印を+Nする」文章形(§11.8残ギャップ)
    if soil:
        return Effect("cnt", axis="土の印", count=int(soil.group(1)))
    return Effect("skip", label=head)


def cond_turn(cond: str) -> int:
    # AI_NOTE: 発動条件が最高値を開くターン(§11.9・rules.md確定・先攻基準)。進化/超進化/エンハンスはモード側で
    # 扱うのでconds(sit群)には来ない。ここに来るのは覚醒等。ルール未確定・デッキ依存(スペブ/連携/ネクロ)は0=
    # 底上げしない(実ターンはデッキ文脈=スライス2の見積り。ここではルール確定の下限だけ返す)。
    return 7 if cond == "覚醒" else 0  # 覚醒=PP最大7以上(rules.md)


def classify(requires: list[str]) -> str | tuple[str, int]:
    # AI_NOTE: 効果atomをプレイモードへ分類(§11.3 モード分解)。超進化>進化>エンハンス>素の順で判定し、
    # どれでもなく全requiresがFFなら素(base・最低値に含める)、状況依存の残りはsit(最高値を開く条件付き)。
    for r in requires:
        if "超進化時" in r or r == "超進化権":
            return "sevo"
    for r in requires:
        if "進化時" in r or r == "進化権":
            return "evo"
    for r in requires:
        m = ENHANCE.search(r)
        if m:
            return ("enh", int(m.group(1)))
    if all(r == "ファンファーレ" for r in requires):
        return "base"
    return "sit"


def build_vector(
    items: list[tuple[str, list[str]]],
    type_category: str,
    atk: int,
    life: int,
    cost: int,
    spent_evo: str | None,
    tokens: dict[str, tuple[int, int]],
) -> tuple[Counter[str], list[Removal], set[str], set[str], set[str], list[str], int, int]:
    # AI_NOTE: atom群を軸へ集計。フォロワーは素のスタッツを、全カードは実コストPPを土台に置く。置換(numR)は
    # 加算でなくaxisごとの最大値へ畳む(§11.7)。spent_evoは進化/超進化権の消費で符号付き-1(§11.3)。
    vector: Counter[str] = Counter()
    replaced: dict[str, int] = {}
    removals: list[Removal] = []
    flags: set[str] = set()
    supplies: set[str] = set()
    disruptions: set[str] = set()
    unresolved: list[str] = []
    if type_category == "follower":
        vector["攻撃力"] += atk
        vector["体力"] += life
    vector["PP"] += cost
    vector["カード枚数"] -= 1  # AI_NOTE: カードは1枚使えば手札から消える(§11.4 手札-1)。ドロー/生成でこれを相殺。充足軸
    # AI_NOTE: 縦/横(§11.3)。self_body=自分の体の大きさ(縦)・body_count=体数(横)・max_token=召喚体の最大単体
    self_body = atk + life if type_category == "follower" else 0
    body_count = 1 if type_category == "follower" else 0
    max_token = 0
    # AI_NOTE: ∧複合効果(例「フォロワー全体4∧リーダー4」)は各項を独立にパース(67枚で2項目以降が落ちていた)。
    parts = [(p, req) for text, req in items for p in _split_top(text)]
    for text, _requires in parts:
        effect = parse_effect(text, tokens)
        if effect.kind == "num":
            vector[effect.axis] += effect.value
        elif effect.kind == "numR":
            replaced[effect.axis] = max(replaced.get(effect.axis, 0), effect.value)
        elif effect.kind == "selfstat":  # 自分の体を大きくする=縦を伸ばす
            vector["攻撃力"] += effect.atk
            vector["体力"] += effect.life
            self_body += effect.atk + effect.life
        elif effect.kind == "summon":  # 体をN体出す=横を増やす・召喚体の最大単体は縦候補
            vector["攻撃力"] += effect.atk * effect.count
            vector["体力"] += effect.life * effect.count
            body_count += effect.count
            max_token = max(max_token, effect.atk + effect.life)
        elif effect.kind == "cnt":
            vector[f"{effect.axis}産出"] += effect.count
        elif effect.kind == "rem" and effect.removal is not None:
            removals.append(effect.removal)
        elif effect.kind == "flag":
            flags.add(effect.label)
        elif effect.kind == "delay":
            flags.add(f"遅延{effect.count}ターン")
        elif effect.kind == "sup":
            supplies.add(effect.label if effect.label == "スタッツ" else effect.label + "付与")
        elif effect.kind == "disr":
            disruptions.add(effect.label)  # 妨害=その他枠フラグでベクトルに載せる(§11.7・値の重みはフェーズ2)
        elif effect.kind == "skip":
            unresolved.append(effect.label)
        # setup/struct はphase-1では軸に載せない(お膳立て・構造は値でない・§11.7)
    for axis, val in replaced.items():
        vector[axis] = max(vector[axis], val)
    if spent_evo is not None:
        vector[spent_evo] -= 1
    max_body = max(self_body, max_token)  # 縦=自分の体と召喚体の大きい方
    return vector, removals, flags, supplies, disruptions, unresolved, body_count, max_body


def evaluate_card(conn: Connection, card_id: int, tokens: dict[str, tuple[int, int]]) -> tuple[str, list[Mode]]:
    # AI_NOTE: カード1枚をモード別ベクトルへ。atomをrequiresで分類し、モードごとにfloor(素+当該トリガ)と
    # ceiling(floor+状況依存)を組む。ceilingを開く発動条件はsit atomのrequires(FF除く・distinct)を添える(§11.2)。
    row = conn.execute("SELECT name, cost, atk, life, type_category FROM card WHERE card_id = ?", (card_id,)).fetchone()
    if row is None:
        raise ValueError(f"card_id {card_id} は存在しない")
    name, cost, atk, life, type_category = row
    atom_row = conn.execute("SELECT atoms_json FROM card_atom WHERE card_id = ?", (card_id,)).fetchone()
    atoms = json.loads(atom_row[0]).get("atoms", []) if atom_row else []

    groups: defaultdict[str | tuple[str, int], list[tuple[str, list[str]]]] = defaultdict(list)
    for atom in atoms:
        if isinstance(atom, dict):
            requires = atom.get("requires") or []
            groups[classify(requires)].append((atom.get("effect") or "", requires))

    enhance_costs = sorted({key[1] for key in groups if isinstance(key, tuple)})
    modes_spec: list[tuple[str, int, str | tuple[str, int], str | None]] = [("素", cost, "base", None)]
    if groups["evo"]:
        modes_spec.append(("進化", cost, "evo", "進化権"))
    if groups["sevo"]:
        modes_spec.append(("超進化", cost, "sevo", "超進化権"))
    for n in enhance_costs:
        modes_spec.append((f"エンハンス{n}", n, ("enh", n), None))

    situational = groups["sit"]
    conds: list[str] = []
    for _text, req in situational:
        for r in req:
            if r != "ファンファーレ" and r not in conds:
                conds.append(r)

    modes: list[Mode] = []
    for label, mode_cost, trigger, spent_evo in modes_spec:
        floor_items = list(groups["base"]) + ([] if trigger == "base" else groups[trigger])
        ceiling_items = floor_items + situational
        floor_vec, *_ = build_vector(floor_items, type_category, atk, life, mode_cost, spent_evo, tokens)
        ceiling_vec, removals, flags, supplies, disruptions, unresolved, body_count, max_body = build_vector(
            ceiling_items, type_category, atk, life, mode_cost, spent_evo, tokens
        )
        # AI_NOTE: 発動ターン(§11.9)。floor=最速で出せる(プレイ)ターン=コスト、進化/超進化は権利が使えるターンで底上げ。
        # ceiling=天井の"値"が実現するターン=floorとルール確定conds(覚醒等)の最大＋遅延Nターン(カウントダウン等の確定ディレイ)。
        turn_floor = max(mode_cost, 1)  # cost0でも最速はT1(ゲームにT0は無い)
        if spent_evo == "進化権":
            turn_floor = max(turn_floor, 5)  # 進化=先攻T5(rules.md)
        elif spent_evo == "超進化権":
            turn_floor = max(turn_floor, 7)  # 超進化=先攻T7(rules.md)
        delays = [int(m.group(1)) for f in flags if (m := re.match(r"遅延(\d+)ターン", f))]
        turn_ceiling = max([turn_floor] + [cond_turn(c) for c in conds]) + (max(delays) if delays else 0)
        modes.append(
            Mode(label, mode_cost, dict(floor_vec), dict(ceiling_vec), removals, flags, supplies,
                 list(conds), turn_floor, turn_ceiling, disruptions, unresolved, body_count, max_body)
        )
    return name, modes


def _format_vector(floor: dict[str, int], ceiling: dict[str, int]) -> str:
    # AI_NOTE: floor→ceilingの幅を1行に。差があれば "軸:最低→最高"、同値なら "軸:値"。ceilingの軸順を保つ。
    parts = []
    for axis in ceiling:
        lo, hi = floor.get(axis, 0), ceiling[axis]
        if not (lo or hi):
            continue
        parts.append(f"{axis}:{lo}→{hi}" if lo != hi else f"{axis}:{hi}")
    return "  ".join(parts)


def _format_removal(removal: Removal) -> str:
    return f"{{殺傷力:{removal.kill} 到達:{removal.reach} {removal.kind}}}"


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口。card_id(数字)か カード名 でそのカードのモード別ベクトルを見やすく出す。
    args = sys.argv[1:]
    if not args:
        print("usage: python -m svdeck.strength <card_id | card_name>")
        sys.exit(1)
    query = args[0]
    conn = connect()
    try:
        tokens = load_token_stats(conn)
        column = "card_id" if query.isdigit() else "name"
        value: int | str = int(query) if query.isdigit() else query
        row = conn.execute(f"SELECT card_id FROM card WHERE {column} = ?", (value,)).fetchone()
        if row is None:
            print(f"見つからない: {query}")
            sys.exit(1)
        name, modes = evaluate_card(conn, row[0], tokens)
        print(f"■ {name} (card_id={row[0]})")
        for mode in modes:
            turn = f"T{mode.turn_floor}" if mode.turn_ceiling == mode.turn_floor else f"T{mode.turn_floor}→{mode.turn_ceiling}"
            print(f"  [{mode.label} PP{mode.cost} 発動{turn}] {_format_vector(mode.floor, mode.ceiling)}")
            if mode.body_count:
                print(f"      盤面: 体数{mode.body_count}(横) 最大単体{mode.max_body}(縦)")
            if mode.removals:
                print(f"      除去: {[_format_removal(r) for r in mode.removals]}")
            if mode.flags:
                print(f"      フラグ: {sorted(mode.flags)}")
            if mode.supplies:
                print(f"      供給(相方次第): {sorted(mode.supplies)}")
            if mode.disruptions:
                print(f"      妨害: {sorted(mode.disruptions)}")
            if mode.conds:
                print(f"      発動条件(天井を開く): {mode.conds}")
            if mode.unresolved:
                print(f"      未解決: {mode.unresolved}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
