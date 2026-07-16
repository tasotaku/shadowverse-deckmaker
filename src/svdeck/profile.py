"""デッキプロファイル第1弾(design.md §6.5.1)。環境デッキ40枚をリーダーダメージ・回復・リソース力の3軸へ集計。

card_vschema を直読し、随伴・手札加算トークンは名前解決してトークン自身のキーワード・コストまで数える
(バット=1/1ドレインの漏れを塞ぐ)。進化時・超進化時のエントリは機械値に入れない(進化権は機械では
考えない・人が後から足す)。条件付きの回復・打点は数値にせず素材リストとして列挙し、デッキ単位の
見積もりは人/LLMの仕事に残す。変化(置き換え)はv1未対応で件数だけ報告する(silent禁止)。

  [meta_deck_card] -> [カード毎の3軸寄与(スキーマ直読+トークン解決)] -> [デッキ集計(リソース力A=不動点)] -> [レポート]

リソース力A = (コスト総和 + 手札加算トークンのコスト総和) / (40 - ドロー総数)。
= 手札1枚の正味消費あたり使えるコスト量(§6.5.1・合計は二重計上になるため使わない)。

実行: PYTHONPATH=src python -m svdeck.profile <deck_id ...> | decks
"""

import json
import sys
from dataclasses import dataclass, field
from sqlite3 import Connection
from typing import Any

from svdeck.db import connect
from svdeck.vector import ENHANCE, _gating, _xnum

# AI_NOTE: 素で使う想定のない融合用等のトークン(§6.5.1)。ユーザーの○×で育てる除外リスト。
EXCLUDED_TOKENS: set[str] = set()


@dataclass
class TokenInfo:
    card_id: int
    cost: int
    atk: int
    traits: list[str]


@dataclass
class CardShare:
    # AI_NOTE: カード1種のデッキへの寄与(コピー数を掛ける前)。material=条件付きで数値にできない素材の説明文。
    leader_floor: int = 0
    leader_ceiling: int = 0
    heal_floor: int = 0
    heal_ceiling: int = 0
    draw_floor: int = 0
    draw_ceiling: int = 0
    token_cost_floor: int = 0
    token_cost_ceiling: int = 0
    hand_tokens: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    skipped_evo: int = 0
    skipped_henka: int = 0
    # AI_NOTE: 手札に加わったトークンは後でプレイされ効果が出る(バットのドレイン・0コススペルのバーン等)。
    # (トークン名, 枚数, 生成が無条件か)を積み、card_shareが再帰解決してマージする(§6.5.1 トークン漏れ防止)。
    pending_tokens: list[tuple[str, int, bool]] = field(default_factory=list)


def load_tokens(conn: Connection) -> dict[str, TokenInfo]:
    # AI_NOTE: トークン名→(コスト/攻/特性)。同名はトークン版(is_token=1)優先=strength.load_token_statsと同じ規律。
    # 特性はvschemaの自身.特性から引く(ドレイン・疾走の内蔵キーワードを漏らさない=§6.5.1の共通前提)。
    tokens: dict[str, TokenInfo] = {}
    rows = conn.execute(
        "SELECT c.name, c.card_id, c.cost, c.atk, c.is_token, v.schema_json "
        "FROM card c LEFT JOIN card_vschema v USING(card_id)"
    )
    for name, card_id, cost, atk, is_token, schema_json in rows:
        if name in tokens and is_token != 1:
            continue
        traits: list[str] = []
        if schema_json:
            body = json.loads(schema_json).get("自身") or {}
            traits = [t for t in body.get("特性") or [] if isinstance(t, str)]
        tokens[name] = TokenInfo(card_id, cost or 0, atk or 0, traits)
    return tokens


def _mode(conds: list[str]) -> tuple[str, list[str]]:
    # AI_NOTE: エントリの効きどころ。evo=進化系(機械値に入れない)/entry=直接召喚(FF不発の別経路・数えない)/
    # base=素プレイ。gateはファンファーレを除いた「天井を開く条件」(vector.classifyの簡約版。エンハンスも
    # 同一カードの別プレイなので天井条件として残す)。
    if any(("進化時" in c or "超進化時" in c) for c in conds):
        return "evo", []
    if any("直接召喚" in c for c in conds):
        return "entry", []
    gate = [c for c in conds if c != "ファンファーレ" and _gating(c)]
    return "base", gate


def _rep(entry: dict[str, Any]) -> int:
    rep, _ = _xnum(entry.get("繰り返し", 1), default=1)
    return max(rep, 1)


def _leader_and_heal(share: CardShare, entry: dict[str, Any], gate: list[str], name: str) -> None:
    # AI_NOTE: 処理エントリからバーン(相手リーダー)と回復(自リーダー)を拾う。X型は素材へ。
    # 自フォロワー回復は盤面維持でリーダー体力でないため軸に載せず素材にも出さない(§6.5.1は回復=リーダー)。
    targets = entry.get("対象") or []
    eff = entry.get("効果") or {}
    if "相手リーダー" in targets:
        dmg, x_dmg = _xnum(eff.get("ダメージ", 0))
        if x_dmg:
            share.materials.append(f"バーンX型: {name} ({x_dmg})")
        elif dmg:
            total = dmg * _rep(entry)
            share.leader_ceiling += total
            if not gate:
                share.leader_floor += total
            else:
                share.materials.append(f"条件付きバーン: {name} {total}点 ({'・'.join(gate)})")
    if "自リーダー" in targets:
        heal, x_heal = _xnum(eff.get("回復", 0))
        if x_heal:
            share.materials.append(f"回復X型: {name} ({x_heal})")
        elif heal:
            total = heal * _rep(entry)
            share.heal_ceiling += total
            if not gate:
                share.heal_floor += total
            else:
                share.materials.append(f"条件付き回復: {name} {total}点 ({'・'.join(gate)})")
    grants = eff.get("特性付与") or []
    for kw in ("疾走", "ドレイン"):
        if any(kw in str(g) for g in grants):
            share.materials.append(f"{kw}付与: {name} ({'・'.join(gate) or '無条件'})")


def _storm_bodies(share: CardShare, entry: dict[str, Any], gate: list[str],
                  name: str, tokens: dict[str, TokenInfo]) -> None:
    # AI_NOTE: 随伴=場に出る体。トークン自身の内蔵キーワードを解決し、疾走=打点(素の攻撃力)・
    # ドレイン=条件付き回復素材にする。FF不発の規律は維持(出た体のFFは見ない・特性だけ見る)。
    token_name = str(entry.get("何を", "")).strip("『』「」")
    info = tokens.get(token_name)
    if info is None:
        return
    count, x_count = _xnum(entry.get("数", 1), default=1)
    count = max(count, 1)
    grant = entry.get("付与") or {}
    traits = info.traits + [t for t in grant.get("特性") or [] if isinstance(t, str)]
    if any("疾走" in t for t in traits) and info.atk:
        total = info.atk * count
        share.leader_ceiling += total
        if not gate and not x_count:
            share.leader_floor += total
        else:
            share.materials.append(f"条件付き疾走: {name}→{token_name} {total}点 ({'・'.join(gate) or x_count})")
    if any("ドレイン" in t for t in traits):
        share.materials.append(
            f"ドレイン体: {name}→{token_name}×{count} 攻{info.atk} ({'・'.join(gate) or '無条件'})"
        )


def _resource(share: CardShare, entry: dict[str, Any], gate: list[str],
              name: str, tokens: dict[str, TokenInfo]) -> None:
    # AI_NOTE: リソース力の材料(§6.5.1)。引く=ドロー枚数 / 生成(特定)=手札加算トークンの額面コスト。
    # コピー/参照/変身は額面が決まらないため素材へ(=個別の変数)。除外リストのトークンは0扱い。
    count, x_count = _xnum(entry.get("何枚", 1), default=1)
    if x_count:
        share.materials.append(f"リソースX型: {name} ({x_count})")
        return
    if entry.get("動作") == "引く":
        share.draw_ceiling += count
        if not gate:
            share.draw_floor += count
        return
    kind = entry.get("生成種別")
    if kind != "特定":
        share.materials.append(f"生成({kind}): {name} ×{count}")
        return
    token_name = str(entry.get("生成対象", "")).strip("『』「」")
    share.hand_tokens.append(token_name)
    if token_name in EXCLUDED_TOKENS:
        return
    info = tokens.get(token_name)
    if info is None:
        share.materials.append(f"生成先が未解決: {name}→{token_name}")
        return
    share.token_cost_ceiling += info.cost * count
    if not gate:
        share.token_cost_floor += info.cost * count
    share.pending_tokens.append((token_name, count, not gate))


def _merge_token(share: CardShare, token_share: "CardShare", token_name: str, count: int, floor_ok: bool) -> None:
    # AI_NOTE: 手札加算トークンのプレイ時効果を親カードへ合算。生成が条件付きなら最低値には入れない
    # (floor_ok=False)。トークンのコスト計上は_resource側で済んでいるので数値軸と素材だけ足す。
    for axis in ("leader", "heal", "draw"):
        setattr(share, f"{axis}_ceiling",
                getattr(share, f"{axis}_ceiling") + getattr(token_share, f"{axis}_ceiling") * count)
        if floor_ok:
            setattr(share, f"{axis}_floor",
                    getattr(share, f"{axis}_floor") + getattr(token_share, f"{axis}_floor") * count)
    share.materials += [f"{m} (手札加算: {token_name}×{count})" for m in token_share.materials]
    share.skipped_evo += token_share.skipped_evo * count
    share.skipped_henka += token_share.skipped_henka * count


def card_share(conn: Connection, card_id: int, tokens: dict[str, TokenInfo], depth: int = 0) -> CardShare | None:
    # AI_NOTE: カード1種の3軸寄与。自身の疾走・ドレインもトークンと同じ規律で数える(打点は素の攻撃力)。
    # depth=手札加算トークンの再帰段数。2で打ち切り(トークンがトークンを生む連鎖の暴走防止)。
    row = conn.execute(
        "SELECT c.name, c.atk, v.schema_json FROM card c "
        "LEFT JOIN card_vschema v USING(card_id) WHERE c.card_id = ?", (card_id,)
    ).fetchone()
    if row is None or row[2] is None:
        return None
    name, atk, schema_json = row
    schema = json.loads(schema_json)
    share = CardShare()
    traits = [t for t in (schema.get("自身") or {}).get("特性") or [] if isinstance(t, str)]
    if any("疾走" in t for t in traits) and atk:
        share.leader_floor += atk
        share.leader_ceiling += atk
    if any("ドレイン" in t for t in traits):
        share.materials.append(f"ドレイン体: {name} 攻{atk or 0} (無条件)")
    for entry in schema.get("効果") or []:
        conds = [str(c) for c in entry.get("条件") or []]
        mode, gate = _mode(conds)
        if mode != "base":
            share.skipped_evo += mode == "evo"
            continue
        if entry.get("変化") is not None:
            share.skipped_henka += 1
        kind = entry.get("種類")
        if kind == "処理":
            _leader_and_heal(share, entry, gate, name)
        elif kind == "随伴":
            _storm_bodies(share, entry, gate, name, tokens)
        elif kind == "リソース":
            _resource(share, entry, gate, name, tokens)
    if depth < 2:
        for token_name, count, floor_ok in share.pending_tokens:
            info = tokens.get(token_name)
            token_share = card_share(conn, info.card_id, tokens, depth + 1) if info else None
            if token_share is not None:
                _merge_token(share, token_share, token_name, count, floor_ok)
    return share


def profile(conn: Connection, deck_id: int, tokens: dict[str, TokenInfo]) -> str:
    # AI_NOTE: デッキ集計本体。コピー数を掛けて合算し、リソース力Aを不動点式で出す。
    deck = conn.execute("SELECT name, tier, format FROM meta_deck WHERE id = ?", (deck_id,)).fetchone()
    if deck is None:
        return f"deck_id {deck_id} は meta_deck に存在しません。\n"
    rows = conn.execute(
        "SELECT mdc.card_id, mdc.card_name, mdc.count, c.cost FROM meta_deck_card mdc "
        "JOIN card c USING(card_id) WHERE mdc.deck_id = ? AND mdc.card_id IS NOT NULL", (deck_id,)
    ).fetchall()
    total = CardShare()
    cost_sum = 0
    cards = 0
    materials: list[str] = []
    missing: list[str] = []
    for card_id, card_name, count, cost in rows:
        cards += count
        cost_sum += (cost or 0) * count
        share = card_share(conn, card_id, tokens)
        if share is None:
            missing.append(card_name)
            continue
        for axis in ("leader_floor", "leader_ceiling", "heal_floor", "heal_ceiling",
                     "draw_floor", "draw_ceiling", "token_cost_floor", "token_cost_ceiling"):
            setattr(total, axis, getattr(total, axis) + getattr(share, axis) * count)
        total.skipped_evo += share.skipped_evo * count
        total.skipped_henka += share.skipped_henka * count
        total.hand_tokens += share.hand_tokens * count
        materials += [f"{m} ×{count}" for m in share.materials]

    lines = [f"=== [{deck[2]}/T{deck[1]}] {deck[0]} ({cards}枚) ==="]
    lines.append(f"  リーダーダメージ: {total.leader_floor} → {total.leader_ceiling} (疾走素点+バーン・進化権抜き)")
    lines.append(f"  回復(リーダー):   {total.heal_floor} → {total.heal_ceiling} (無条件のみ機械値)")
    for label, floor_d, floor_t, ceil_d, ceil_t in [
        ("最低", total.draw_floor, total.token_cost_floor, total.draw_ceiling, total.token_cost_ceiling)
    ]:
        a_floor = (cost_sum + floor_t) / (cards - floor_d) if cards > floor_d else float("inf")
        a_ceil = (cost_sum + ceil_t) / (cards - ceil_d) if cards > ceil_d else float("inf")
        lines.append(
            f"  リソース力A:     {a_floor:.2f} → {a_ceil:.2f} "
            f"(コスト計{cost_sum}・ドロー{floor_d}→{ceil_d}・手札加算トークンコスト{floor_t}→{ceil_t})"
        )
    if materials:
        lines.append("  --- 素材リスト(条件付き・人/LLMが見積もる) ---")
        lines += [f"    - {m}" for m in sorted(set(materials))]
    if total.hand_tokens:
        uniq = sorted(set(total.hand_tokens))
        lines.append(f"  手札加算トークン(○×レビュー用): {', '.join(uniq)}")
    if total.skipped_evo or total.skipped_henka:
        lines.append(f"  (非対象: 進化系エントリ{total.skipped_evo}件・変化未対応{total.skipped_henka}件)")
    if missing:
        lines.append(f"  ⚠ スキーマなし: {missing}")
    return "\n".join(lines) + "\n"


def list_decks(conn: Connection) -> str:
    rows = conn.execute("SELECT id, tier, name, format FROM meta_deck ORDER BY tier, id").fetchall()
    return "\n".join(f"{r[0]:3d} T{r[1]} {r[2]} ({r[3]})" for r in rows) + "\n"


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口。decks=一覧 / deck_id列挙=各デッキのプロファイル。
    args = sys.argv[1:]
    conn = connect()
    try:
        if args == ["decks"]:
            print(list_decks(conn))
            return
        if not args or not all(a.isdigit() for a in args):
            print("usage: python -m svdeck.profile <deck_id ...> | decks")
            sys.exit(1)
        tokens = load_tokens(conn)
        for deck_id in args:
            print(profile(conn, int(deck_id), tokens))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
