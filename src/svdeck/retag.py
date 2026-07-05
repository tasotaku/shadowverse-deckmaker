"""キーワード系供給タグの「付与」/「保持」再分類。

背景(2026-07-06ユーザー発見): 抽出時に「キーワードを自分が持っている(保持)」と「他者に与える(付与)」が
混同され、`X付与`タグの多くが実際はただの保持だった(例: 【突進】ブラケットのみの自己完結カード)。
マッチングで「付与供給」を探すと保持カードが大量の偽陽性になる。本モジュールは既存の`X付与`タグ
(kind='supply')を skill_text(+specific_effectの同一card_id分を連結)の文型から再判定し、
他者付与でないものを`X保持`にUPDATEする(1機構1タグの原則は維持=付与/保持のどちらか一方のみ持つ)。

判定対象キーワード: 突進・守護・疾走・潜伏・必殺・ドレイン・威圧・オーラ・バリア。

実行: python -m svdeck.retag
"""

import re
import sqlite3
from pathlib import Path
from typing import NamedTuple

from svdeck.db import connect

TARGET_KEYWORDS = ["突進", "守護", "疾走", "潜伏", "必殺", "ドレイン", "威圧", "オーラ", "バリア"]

REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "retag_report.txt"

# AI_NOTE: マークアップ(<color=Keyword>~</color>等のタグ)を除去してから文単位で判定する。
_MARKUP_PATTERN = re.compile(r"<[^>]+>")

# AI_NOTE: 自己付与(保持)文型。「これは/これが」「自分のリーダーは」が「~を持つ」の主語になる文。
# 「これは+2/+2して【守護】を持つ」のように間に修飾(スタッツ変化等)が挟まる場合も対象にするため、
# 文中どこにあっても主語がこれ/自分のリーダーなら自己付与とみなす(文末が「を持つ」で終わる前提)。
_SELF_GRANT = re.compile(r"(これ(は|が)|自分のリーダーは)[^。「」]*を持つ$")

# AI_NOTE: 他者付与文型。「それ/それら/それとこれ/選んだ~/~すべて/~N枚/フォロワー(は|に)…を持つ」。
# 「フォロワーから」(選択元を表す用法)は対象記述でなく効果対象ではないため除外する。
_OTHER_GRANT = re.compile(
    r"(それら|それとこれ|それ|選んだ[^。]{0,20}|[^。]{0,20}すべて|[^。、]{0,10}[0-9０-９]+枚|フォロワー(?!から))"
    r"(は|に)[^。]{0,40}を持つ$"
)

# AI_NOTE:「~を持たせる」型(能動的な付与の別表現)。
_GIVE_GRANT = re.compile(r"を持たせる")

# AI_NOTE: 名詞修飾で「Xを持つフォロワー/カード」を対象選定条件として参照しているだけの文(能力トリガの
# 主節でなく他カードの状態を言及)は判定対象から除外する。例:「【守護】を持つ、進化前のフォロワー」。
_NOUN_REF = re.compile(r"を持つ[、」]?(フォロワー|カード)")

# AI_NOTE: 境界例(付与文型はあるが対象が自分が今出した別トークンだけ)。直前の文に「~を自分の場に出す」が
# あり、当該文が「それ(ら)は/に」で始まる場合、対象は生成したトークン自身であり「他者への供給」と
# 断定しにくい(トークンの性能そのものとも解釈できる)。親レビュー対象として境界保留にする。
_SUMMON_PREFIX = re.compile(r"自分の場に出す$")
# AI_NOTE: 「【超進化時】それは~を持つ」のようにトリガ表記(【X】/（N）)が文頭に付く場合も
# 代名詞開始とみなす(トリガは召喚と別タイミングでも「それ」は直前召喚物を指すため)。
_PRONOUN_START = re.compile(r"^(【[^】]+】|（\d+）)*(それ(ら)?|これ)(は|に)")


class TagVerdict(NamedTuple):
    card_id: int
    card_name: str
    keyword: str
    old_tag: str
    new_kind: str  # "grant"(付与維持) / "keep"(保持へ変更) / "boundary"(境界保留)
    evidence: str  # 判定根拠になった文


def _strip_markup(text: str) -> str:
    return _MARKUP_PATTERN.sub("", text)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。\n]", text) if s.strip()]


def _load_full_text(conn: sqlite3.Connection, card_id: int, skill_text: str | None) -> str:
    # AI_NOTE: specific_effect(進化後能力等の派生カード)は同一card_id分を連結してから判定する
    # (仕様: specific_effectの参照効果も同一card_id分は連結して判定)。
    text = skill_text or ""
    rows = conn.execute("SELECT skill_text FROM specific_effect WHERE card_id = ?", (card_id,)).fetchall()
    for (se_text,) in rows:
        if se_text:
            text += "\n" + se_text
    return text


def classify_keyword(card_id: int, card_name: str, keyword: str, full_text: str) -> TagVerdict:
    # AI_NOTE: 判定は文単位。同じキーワードについて複数文が「持つ」を含みうるため、1文でも他者付与が
    # 見つかれば付与維持、境界パターンが見つかれば境界保留(付与より優先度低いが保持よりは優先)、
    # どれも無ければ保持へ変更する。優先順位: grant > boundary > keep。
    old_tag = f"{keyword}付与"
    text = _strip_markup(full_text)
    sentences = _split_sentences(text)
    verdicts: list[tuple[str, str]] = []
    for i, sentence in enumerate(sentences):
        if keyword not in sentence:
            continue
        if _NOUN_REF.search(sentence):
            continue
        if "を持つ" not in sentence and "を持たせる" not in sentence:
            continue
        prev = sentences[i - 1] if i > 0 else ""
        if _GIVE_GRANT.search(sentence):
            verdicts.append(("grant", sentence))
        elif _SELF_GRANT.search(sentence):
            verdicts.append(("self", sentence))
        elif _SUMMON_PREFIX.search(prev) and _PRONOUN_START.match(sentence):
            verdicts.append(("boundary", f"{prev}。{sentence}"))
        elif _OTHER_GRANT.search(sentence):
            verdicts.append(("grant", sentence))
        else:
            verdicts.append(("boundary", sentence))  # 未知文型は安全側(境界保留)に倒す

    kinds = [k for k, _ in verdicts]
    if "grant" in kinds:
        evidence = next(s for k, s in verdicts if k == "grant")
        return TagVerdict(card_id, card_name, keyword, old_tag, "grant", evidence)
    if "boundary" in kinds:
        evidence = next(s for k, s in verdicts if k == "boundary")
        return TagVerdict(card_id, card_name, keyword, old_tag, "boundary", evidence)
    evidence = verdicts[0][1] if verdicts else "(【" + keyword + "】ブラケットのみ)"
    return TagVerdict(card_id, card_name, keyword, old_tag, "keep", evidence)


def run_retag(conn: sqlite3.Connection) -> list[TagVerdict]:
    tags = [f"{kw}付与" for kw in TARGET_KEYWORDS]
    marks = ",".join("?" * len(tags))
    rows = conn.execute(
        f"""
        SELECT at.card_id, c.name, c.skill_text, at.tag
        FROM atom_tag at JOIN card c ON c.card_id = at.card_id
        WHERE at.kind = 'supply' AND at.tag IN ({marks})
        ORDER BY at.tag, at.card_id
        """,
        tags,
    ).fetchall()

    verdicts = []
    for card_id, card_name, skill_text, tag in rows:
        keyword = tag[: -len("付与")]
        full_text = _load_full_text(conn, card_id, skill_text)
        verdicts.append(classify_keyword(card_id, card_name, keyword, full_text))

    for verdict in verdicts:
        if verdict.new_kind == "keep":
            new_tag = f"{verdict.keyword}保持"
            conn.execute(
                "UPDATE atom_tag SET tag = ? WHERE card_id = ? AND kind = 'supply' AND tag = ?",
                (new_tag, verdict.card_id, verdict.old_tag),
            )
    conn.commit()
    return verdicts


def format_report(verdicts: list[TagVerdict]) -> str:
    lines: list[str] = []
    lines.append("=== retag: キーワード付与/保持タグの再分類 ===")

    by_keyword: dict[str, list[TagVerdict]] = {}
    for v in verdicts:
        by_keyword.setdefault(v.keyword, []).append(v)

    lines.append("タグ別件数(付与残存 / 保持へ変更 / 境界保留):")
    for keyword in TARGET_KEYWORDS:
        vs = by_keyword.get(keyword, [])
        grant_n = sum(1 for v in vs if v.new_kind == "grant")
        keep_n = sum(1 for v in vs if v.new_kind == "keep")
        boundary_n = sum(1 for v in vs if v.new_kind == "boundary")
        lines.append(f"  {keyword}: 付与{grant_n} / 保持へ変更{keep_n} / 境界保留{boundary_n} (総{len(vs)})")
    lines.append("")

    total_grant = sum(1 for v in verdicts if v.new_kind == "grant")
    total_keep = sum(1 for v in verdicts if v.new_kind == "keep")
    total_boundary = sum(1 for v in verdicts if v.new_kind == "boundary")
    lines.append(f"総計: 付与残存{total_grant} / 保持へ変更{total_keep} / 境界保留{total_boundary} / 全{len(verdicts)}件")
    lines.append("")

    lines.append("=== 境界保留一覧(親レビュー対象・タグ未変更) ===")
    for v in verdicts:
        if v.new_kind == "boundary":
            lines.append(f"- {v.card_id} {v.card_name} [{v.keyword}] 根拠: {v.evidence}")
    lines.append("")

    lines.append(f"=== 付与残存カード一覧(全{TARGET_KEYWORDS}件をkeyword別に列挙) ===")
    for keyword in TARGET_KEYWORDS:
        vs = [v for v in by_keyword.get(keyword, []) if v.new_kind == "grant"]
        if not vs:
            continue
        lines.append(f"--- {keyword}付与 残存 {len(vs)}件 ---")
        for v in vs:
            lines.append(f"- {v.card_id} {v.card_name} 根拠: {v.evidence}")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    conn = connect()
    try:
        verdicts = run_retag(conn)
    finally:
        conn.close()
    report = format_report(verdicts)
    print(report)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
