"""戦闘力ベクトル化の効果スキーマ(v5・design.md §11.10)の入出力＋検証CLI。

抽出はLLMが docs/vector-extraction-prompt.md に従って行い、このモジュールは入力JSONの書き出し(dump)・
抽出結果の検証(validate)・取り込み(load)・確認(show)を担う。atoms.py(マッチング用アトム)と同じ
dump/load構造に倣うが、こちらは**閉じたスキーマをコードで検証**する(LLM出力のドリフトを弾く=silent禁止の実装)。

実行:
  python -m svdeck.vectorize dump [card_id ...]      # 抽出のLLM入力JSON(省略時は全カード)
  python -m svdeck.vectorize load extracted.json     # 検証して card_vschema へ取り込み
  python -m svdeck.vectorize show <card_id>          # 取り込み済みスキーマを表示
"""

import json
import sys
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from svdeck.db import connect

DUMP_COLUMNS = "card_id, name, class_name, type_category, cost, atk, life, skill_text"

# AI_NOTE: v5スキーマの閉じた語彙(design.md §11.10)。validateはこの集合で未知値を弾く=LLMのドリフト検出。
KIND = {"登場", "随伴", "処理", "リソース", "手札処理", "デッキ処理", "クレスト", "資源", "その他"}
TARGET = {"自身", "自フォロワー", "相手フォロワー", "自アミュレット", "相手アミュレット", "自リーダー", "相手リーダー"}
RANGE_TYPE = {"選択", "ランダム", "全体", "全体(自身除く)", "割り振り"}
REMOVAL = {"破壊", "消滅", "変身", "バウンス"}
GEN_TYPE = {"特定", "コピー", "参照", "変身"}
RES_ACTION = {"引く", "生成"}
RESOURCE = {"PP", "進化権", "超進化権", "スペルブースト", "土の印", "信仰", "墓場", "カウント"}
EFFECT_KEYS = {"攻", "体", "特性付与", "ダメージ", "回復", "除去", "変身先"}


def dump(card_ids: list[int]) -> str:
    # AI_NOTE: 抽出のLLM入力となるカード情報をJSON文字列で返す(atoms.dumpと同形式)。card_ids省略時は全カード。
    conn = connect()
    try:
        if card_ids:
            marks = ",".join("?" * len(card_ids))
            cursor = conn.execute(f"SELECT {DUMP_COLUMNS} FROM card WHERE card_id IN ({marks})", card_ids)
        else:
            cursor = conn.execute(f"SELECT {DUMP_COLUMNS} FROM card")
        columns = [d[0] for d in cursor.description]
        cards = [dict(zip(columns, row)) for row in cursor]
    finally:
        conn.close()
    return json.dumps(cards, ensure_ascii=False, indent=1)


def validate(card: dict[str, Any]) -> list[str]:
    # AI_NOTE: v5スキーマ準拠を検査しエラー文のリストを返す(空=合格)。閉じた語彙・必須フィールド・種類別の形を見る。
    # 保存は弾かず全部入れる(silent禁止=欠落させない)が、ここで違反を明示的に炙り出すのが目的。
    errs: list[str] = []
    if not isinstance(card.get("card_id"), int):
        errs.append("card_id が整数でない")
    body = card.get("自身")
    if body is not None:
        if not isinstance(body, dict):
            errs.append("自身 が辞書でもnullでもない")
        else:
            # AI_NOTE: フォロワー=攻体+特性 / アミュレット=特性のみ(攻体なし・カウントダウンNも特性)。スペルはnull。
            has_atk = "攻" in body or "体" in body
            if has_atk and (not isinstance(body.get("攻"), int) or not isinstance(body.get("体"), int)):
                errs.append("自身.攻/体 が整数でない")
            if not isinstance(body.get("特性"), list):
                errs.append("自身.特性 がリストでない")
    effects = card.get("効果")
    if not isinstance(effects, list):
        errs.append("効果 がリストでない")
        return errs
    for i, e in enumerate(effects):
        p = f"効果[{i}]"
        if not isinstance(e, dict):
            errs.append(f"{p} が辞書でない")
            continue
        kind = e.get("種類")
        if kind not in KIND:
            errs.append(f"{p}.種類 '{kind}' は未知")
            continue
        if not isinstance(e.get("条件"), list):
            errs.append(f"{p}.条件 がリストでない")
        errs.extend(_validate_effect(p, kind, e))
    return errs


def _validate_effect(p: str, kind: str, e: dict[str, Any]) -> list[str]:
    # AI_NOTE: 種類ごとの必須フィールドと語彙を検査。分岐は種類で機械的に。
    errs: list[str] = []
    if kind == "登場":
        # AI_NOTE: この体自身の別の出方(直接召喚等・非手札プレイ=FF不発)。経路は必須・自由記述可(直接召喚が主)。
        if not isinstance(e.get("経路"), str):
            errs.append(f"{p}.経路 が文字列でない")
        return errs
    if kind == "処理":
        tgt = e.get("対象")
        if not isinstance(tgt, list) or not tgt or any(t not in TARGET for t in tgt):
            errs.append(f"{p}.対象 が不正: {tgt}")
        rng = e.get("範囲")
        if rng is not None and (not isinstance(rng, dict) or rng.get("型") not in RANGE_TYPE):
            errs.append(f"{p}.範囲.型 が不正: {rng}")
        eff = e.get("効果")
        if not isinstance(eff, dict):
            errs.append(f"{p}.効果 が辞書でない")
        else:
            for k in eff:
                if k not in EFFECT_KEYS:
                    errs.append(f"{p}.効果 に未知キー '{k}'")
            if eff.get("除去") is not None and eff["除去"] not in REMOVAL:
                errs.append(f"{p}.効果.除去 が不正: {eff.get('除去')}")
        # AI_NOTE: 変化=置き換え(§11.10)。条件必須＋上書きは対象/範囲/効果のみ。dict単体かリスト(段階型)を許す。
        henka = e.get("変化")
        if henka is not None:
            for j, v in enumerate(henka if isinstance(henka, list) else [henka]):
                q = f"{p}.変化[{j}]"
                if not isinstance(v, dict) or not isinstance(v.get("条件"), list):
                    errs.append(f"{q} が辞書でないか条件がリストでない")
                    continue
                for k in v:
                    if k not in ("条件", "対象", "範囲", "効果"):
                        errs.append(f"{q} に未知キー '{k}'")
    elif kind == "随伴":
        if not isinstance(e.get("何を"), str):
            errs.append(f"{p}.何を が文字列でない")
    elif kind == "リソース":
        if e.get("動作") not in RES_ACTION:
            errs.append(f"{p}.動作 が不正: {e.get('動作')}")
        if e.get("動作") == "生成" and e.get("生成種別") not in GEN_TYPE:
            errs.append(f"{p}.生成種別 が不正: {e.get('生成種別')}")
        # AI_NOTE: 変化(置き換え)はリソースにも許す(「1枚ではなく2枚」型・2026-07-15決定)。条件必須＋
        # 上書きできるのはリソース自身のフィールドのみ。
        henka = e.get("変化")
        if henka is not None:
            for j, v in enumerate(henka if isinstance(henka, list) else [henka]):
                q = f"{p}.変化[{j}]"
                if not isinstance(v, dict) or not isinstance(v.get("条件"), list):
                    errs.append(f"{q} が辞書でないか条件がリストでない")
                    continue
                for k in v:
                    if k not in ("条件", "動作", "何枚", "何を", "生成種別", "生成対象", "元"):
                        errs.append(f"{q} に未知キー '{k}'")
    elif kind in ("手札処理", "デッキ処理"):
        if not isinstance(e.get("対象"), str):
            errs.append(f"{p}.対象 が文字列でない")
        if not isinstance(e.get("効果"), dict):
            errs.append(f"{p}.効果 が辞書でない")
    elif kind == "クレスト":
        if e.get("対象") not in ("自", "相手"):
            errs.append(f"{p}.対象 が自/相手でない: {e.get('対象')}")
        if not isinstance(e.get("効果"), list):
            errs.append(f"{p}.効果 がリストでない")
    elif kind == "資源":
        if e.get("資源種類") not in RESOURCE:
            errs.append(f"{p}.資源種類 が不正: {e.get('資源種類')}")
        if not isinstance(e.get("量"), (int, float)):
            errs.append(f"{p}.量 が数値でない")
    elif kind == "その他":
        if not isinstance(e.get("記述"), str):
            errs.append(f"{p}.記述 が文字列でない")
    return errs


def _ensure_table(conn: Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS card_vschema ("
        "card_id INTEGER PRIMARY KEY, schema_json TEXT NOT NULL, model TEXT, extracted_at TEXT)"
    )


def load(path: Path) -> tuple[int, int]:
    # AI_NOTE: 抽出結果JSON(配列)を検証して card_vschema へ取り込む。(合格数, 違反あり数)を返す。違反は弾かず
    # 保存しつつ標準出力へ列挙する(欠落させない=silent禁止。人が違反を見て指示書orカードを直す)。
    cards: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    conn = connect()
    try:
        _ensure_table(conn)
        known = {row[0] for row in conn.execute("SELECT card_id FROM card")}
        ok = 0
        flawed = 0
        for card in cards:
            card_id = int(card["card_id"])
            if card_id not in known:
                raise ValueError(f"card_id {card_id} はcardテーブルに存在しない")
            errs = validate(card)
            if errs:
                flawed += 1
                print(f"  ⚠ {card_id}: 検証エラー{len(errs)}件")
                for m in errs:
                    print(f"      - {m}")
            else:
                ok += 1
            conn.execute("DELETE FROM card_vschema WHERE card_id = ?", (card_id,))
            conn.execute(
                "INSERT INTO card_vschema (card_id, schema_json, model, extracted_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (card_id, json.dumps(card, ensure_ascii=False), card.get("model", "unknown")),
            )
        conn.commit()
        return ok, flawed
    finally:
        conn.close()


def show(card_id: int) -> str:
    # AI_NOTE: 取り込み済みスキーマを整形表示。無ければメッセージ。人手の確認用。
    conn = connect()
    try:
        row = conn.execute("SELECT schema_json FROM card_vschema WHERE card_id = ?", (card_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return f"未取り込み: {card_id}"
    return json.dumps(json.loads(row[0]), ensure_ascii=False, indent=2)


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口なので引数不正はusage表示で終了する。
    args = sys.argv[1:]
    if args and args[0] == "dump":
        print(dump([int(a) for a in args[1:]]))
        return
    if len(args) == 2 and args[0] == "load":
        ok, flawed = load(Path(args[1]))
        print(f"[vectorize] 取り込み: {ok + flawed}枚 (合格{ok} / 違反あり{flawed})")
        return
    if len(args) == 2 and args[0] == "show":
        print(show(int(args[1])))
        return
    print("usage: python -m svdeck.vectorize dump [card_id ...] | load <json> | show <card_id>")
    sys.exit(1)


if __name__ == "__main__":
    main()
