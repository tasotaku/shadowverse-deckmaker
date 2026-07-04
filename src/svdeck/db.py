"""SQLiteスキーマ定義と接続ヘルパー。

テーブルは3層に分かれる:
  - 公式ミラー層 (card / card_set / skill_name / tribe / card_tribe): 再クロールでupsert上書きされる。
  - ユーザレイヤ (card_note / card_tag / card_flag): 再クロールで絶対に触らない・DROPしない。
  - 履歴層 (snapshot / card_change): card_changeはfetch時の新規カード(__new__)と、apply_changeで
    手動適用した能力調整(ナーフ/アッパー)の履歴を溜める。全件fetchでの自動差分検出は行わない。
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
    common_json TEXT
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

CREATE TABLE IF NOT EXISTS snapshot (
    date TEXT PRIMARY KEY,
    fetched_at TEXT,
    card_count INTEGER
);

CREATE TABLE IF NOT EXISTS card_change (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT,
    card_id INTEGER,
    field TEXT,
    old_value TEXT,
    new_value TEXT
);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    # AI_NOTE: DB接続とスキーマ作成を一体化。存在しないテーブルのみCREATE IF NOT EXISTSで作るため、
    # ユーザレイヤ・履歴層のデータは再実行時も消えない。境界（DB接続失敗）は例外を握りつぶさずそのまま伝播させる。
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
