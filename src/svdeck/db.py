"""SQLiteスキーマ定義と接続ヘルパー。

テーブルは4層に分かれる:
  - 公式ミラー層 (card / card_set / skill_name / tribe / card_tribe / ability_keyword): 公式データのコピー。
    cardは通常取得では新規だけINSERTし、公式の能力変更時だけ明示的な再確認でUPDATEする。
    辞書(card_set/skill_name/tribe/ability_keyword)は取得のたび作り直す。
  - ユーザレイヤ (card_note / card_tag / card_flag / anchor_require): 再クロールで絶対に触らない・DROPしない。
    anchor_requireはアンカーの要求コンパイル結果の永続化(design.md §8-7)。行単位でupsertし、
    不成立確定時もDELETEせずstatus='dead'で残す(判定根拠を失わないため)。
  - 派生層 (card_atom / atom_tag): LLM抽出で作る供給/要求アトム。再抽出でいつでも作り直してよい。
  - 外部メタ層 (meta_deck / meta_deck_card): 攻略サイトのTier表・デッキレシピのコピー。鮮度が命なので
    再クロールのたびDELETE→全INSERTで作り直す。
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cards.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS card (
    card_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_ruby TEXT,
    skill_text TEXT,
    flavour_text TEXT,
    cost INTEGER,
    atk INTEGER,
    life INTEGER,
    class INTEGER,
    class_name TEXT,
    type INTEGER,
    type_category TEXT,
    rarity INTEGER,
    rarity_name TEXT,
    card_set_id INTEGER,
    is_token INTEGER,
    deck_enabled_num INTEGER,
    is_include_rotation INTEGER,
    base_card_id INTEGER,
    original_card_id INTEGER,
    evo_json TEXT,
    style_json TEXT,
    common_json TEXT,
    ref_effect_text TEXT
);

CREATE TABLE IF NOT EXISTS card_set (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_name (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tribe (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS card_tribe (
    card_id INTEGER NOT NULL,
    tribe_id INTEGER NOT NULL,
    PRIMARY KEY (card_id, tribe_id)
);

CREATE TABLE IF NOT EXISTS card_note (
    card_id INTEGER PRIMARY KEY,
    note TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS card_tag (
    card_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (card_id, tag)
);

CREATE TABLE IF NOT EXISTS card_flag (
    card_id INTEGER PRIMARY KEY,
    favorite INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS card_atom (
    card_id INTEGER PRIMARY KEY,
    atoms_json TEXT NOT NULL,
    model TEXT,
    extracted_at TEXT
);

CREATE TABLE IF NOT EXISTS atom_tag (
    card_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('supply', 'require')),
    tag TEXT NOT NULL,
    PRIMARY KEY (card_id, kind, tag)
);

CREATE INDEX IF NOT EXISTS idx_atom_tag_tag ON atom_tag (kind, tag);

CREATE TABLE IF NOT EXISTS meta_deck (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT,
    url TEXT UNIQUE,
    name TEXT,
    tier TEXT,
    format TEXT,
    updated_on TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS meta_deck_card (
    deck_id INTEGER,
    card_name TEXT,
    count INTEGER,
    card_id INTEGER
);

CREATE TABLE IF NOT EXISTS ability_keyword (
    title TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS anchor_require (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    req_type TEXT NOT NULL CHECK (req_type IN ('event', 'accumulate', 'presence', 'construction')),
    requirement TEXT NOT NULL,
    req_tag TEXT,
    deadline_turn INTEGER,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    note TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_anchor_require_card ON anchor_require (card_id);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    # AI_NOTE: DB接続とスキーマ作成を一体化。存在しないテーブルのみCREATE IF NOT EXISTSで作るため、
    # ユーザレイヤのデータは再実行時も消えない。境界（DB接続失敗）は例外を握りつぶさずそのまま伝播させる。
    # AI_NOTE: DB_PATHは呼び出し時に解決する(デフォルト引数のdef時束縛だとテストのmonkeypatchが効かない)。
    db_path = DB_PATH if db_path is None else db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    _migrate_ref_effect(conn)
    conn.commit()
    return conn


def _migrate_ref_effect(conn: sqlite3.Connection) -> None:
    # AI_NOTE: 2026-07-17のスキーマ統合(specific_effect/effect_crawl廃止→card.ref_effect_text列)の
    # 移行。旧スキーマのDBだけが対象で、移行済み・新規DBでは何もしない冪等処理。全DBコピーが
    # 新スキーマに揃ったら丸ごと削除してよい。走査記録(effect_crawl)は移さない:
    # 取得済み判定は「card行の有無」に変わったため(既存DBは全カード走査済みが前提)。
    cols = {row[1] for row in conn.execute("PRAGMA table_info(card)")}
    if "ref_effect_text" not in cols:
        conn.execute("ALTER TABLE card ADD COLUMN ref_effect_text TEXT")
    if "effect_crawled_at" in cols:
        # AI_NOTE: 統合の途中形(同日中の旧設計)で足した列。作り直し前に消す。
        conn.execute("ALTER TABLE card DROP COLUMN effect_crawled_at")
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('specific_effect', 'effect_crawl')"
    )}
    if "specific_effect" in tables:
        # AI_NOTE: 見出し形式「種別名(コスト): 本文」はfetch.pyの保存形式と揃える。
        # コスト0(クレスト/信仰)は数値に意味が無いので「種別名: 本文」にする。
        conn.execute(
            "UPDATE card SET ref_effect_text = ("
            "  SELECT group_concat(effect_type_name"
            "    || CASE WHEN cost > 0 THEN '(' || cost || ')' ELSE '' END"
            "    || ': ' || skill_text, char(10))"
            "  FROM specific_effect WHERE specific_effect.card_id = card.card_id"
            ") WHERE card_id IN (SELECT card_id FROM specific_effect)"
        )
        conn.execute("DROP TABLE specific_effect")
    if "effect_crawl" in tables:
        conn.execute("DROP TABLE effect_crawl")
