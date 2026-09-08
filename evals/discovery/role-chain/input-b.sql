BEGIN TRANSACTION;
CREATE TABLE ability_keyword (
    title TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    fetched_at TEXT
);
CREATE TABLE anchor_require (
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
CREATE TABLE atom_tag (
    card_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('supply', 'require')),
    tag TEXT NOT NULL,
    PRIMARY KEY (card_id, kind, tag)
);
INSERT INTO "atom_tag" VALUES(94070001,'supply','ダメージ(相手リーダー)');
INSERT INTO "atom_tag" VALUES(94070001,'require','存在(手札高コストフォロワー)');
INSERT INTO "atom_tag" VALUES(94070002,'supply','トークン召喚(青磁の番兵)');
INSERT INTO "atom_tag" VALUES(94070003,'supply','手札戻し(味方フォロワー)');
INSERT INTO "atom_tag" VALUES(94070004,'supply','コスト減少(手札スペル)');
INSERT INTO "atom_tag" VALUES(94070005,'supply','守護保持');
INSERT INTO "atom_tag" VALUES(94070006,'supply','ダメージ(相手リーダー)');
INSERT INTO "atom_tag" VALUES(94070007,'supply','回復(自分リーダー)');
INSERT INTO "atom_tag" VALUES(94070008,'supply','守護保持');
INSERT INTO "atom_tag" VALUES(94070009,'supply','回復(自分リーダー)');
CREATE TABLE card (
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
INSERT INTO "card" VALUES(94070001,'金環の対句',NULL,'相手のリーダーに4ダメージ。自分の手札に元のコストが12以上のフォロワーがあるなら、4ダメージではなく13ダメージ。',NULL,4,0,0,3,'ウィッチ',2,'スペル',1,'ブロンズレア',94070,0,3,1,94070001,94070001,NULL,NULL,NULL,NULL);
INSERT INTO "card" VALUES(94070002,'静寂の守衛庫',NULL,'「青磁の番兵」1枚を自分の場に出す。',NULL,4,0,0,3,'ウィッチ',2,'スペル',1,'ブロンズレア',94070,0,3,1,94070002,94070002,NULL,NULL,NULL,NULL);
INSERT INTO "card" VALUES(94070003,'折返しの紙梯子',NULL,'自分のフォロワー1枚を手札に戻す。',NULL,2,0,0,3,'ウィッチ',2,'スペル',1,'ブロンズレア',94070,0,3,1,94070003,94070003,NULL,NULL,NULL,NULL);
INSERT INTO "card" VALUES(94070004,'余白のしるし',NULL,'自分の手札のスペル1枚を選ぶ。そのコストを-2する（このターン中）。',NULL,1,0,0,3,'ウィッチ',2,'スペル',1,'ブロンズレア',94070,0,3,1,94070004,94070004,NULL,NULL,NULL,NULL);
INSERT INTO "card" VALUES(94070005,'青磁の番兵',NULL,'【守護】',NULL,9,1,4,3,'ウィッチ',1,'フォロワー',1,'ブロンズレア',94070,1,0,1,94070005,94070005,'{"atk": 3, "life": 6, "skill_text": "【守護】"}',NULL,NULL,NULL);
INSERT INTO "card" VALUES(94070006,'火花の採寸',NULL,'相手のリーダーに4ダメージ。',NULL,4,0,0,3,'ウィッチ',2,'スペル',1,'ブロンズレア',94070,0,3,1,94070006,94070006,NULL,NULL,NULL,NULL);
INSERT INTO "card" VALUES(94070007,'硝子の休符',NULL,'自分のリーダーを3回復。',NULL,2,0,0,3,'ウィッチ',2,'スペル',1,'ブロンズレア',94070,0,3,1,94070007,94070007,NULL,NULL,NULL,NULL);
INSERT INTO "card" VALUES(94070008,'乾いた番帳',NULL,'【守護】',NULL,2,2,2,3,'ウィッチ',1,'フォロワー',1,'ブロンズレア',94070,0,3,1,94070008,94070008,'{"atk": 4, "life": 4, "skill_text": "【守護】"}',NULL,NULL,NULL);
INSERT INTO "card" VALUES(94070009,'凪の観測者',NULL,'自分のターン終了時、自分のリーダーを1回復。',NULL,3,3,4,3,'ウィッチ',1,'フォロワー',1,'ブロンズレア',94070,0,3,1,94070009,94070009,'{"atk": 5, "life": 6, "skill_text": "自分のターン終了時、自分のリーダーを1回復。"}',NULL,NULL,NULL);
CREATE TABLE card_atom (
    card_id INTEGER PRIMARY KEY,
    atoms_json TEXT NOT NULL,
    model TEXT,
    extracted_at TEXT
);
CREATE TABLE card_flag (
    card_id INTEGER PRIMARY KEY,
    favorite INTEGER DEFAULT 0
);
CREATE TABLE card_note (
    card_id INTEGER PRIMARY KEY,
    note TEXT,
    updated_at TEXT
);
INSERT INTO "card_note" VALUES(94070001,'架空カード。公式カードとして扱わない。 条件は元のコストを参照する。通常の4ダメージと条件成立時13ダメージは加算しない。','2026-09-08T00:00:00+09:00');
INSERT INTO "card_note" VALUES(94070002,'架空カード。公式カードとして扱わない。 この効果の生成先は場。手札へ直接加える効果ではない。','2026-09-08T00:00:00+09:00');
INSERT INTO "card_note" VALUES(94070003,'架空カード。公式カードとして扱わない。 この効果自体にPP回復はない。','2026-09-08T00:00:00+09:00');
INSERT INTO "card_note" VALUES(94070004,'架空カード。公式カードとして扱わない。 軽減はこのターン限り。支払うコストは0未満にならない。','2026-09-08T00:00:00+09:00');
INSERT INTO "card_note" VALUES(94070005,'架空カード。公式カードとして扱わない。 検査用の生成専用カード。直接採用不可。通常のフォロワーとして扱う。','2026-09-08T00:00:00+09:00');
INSERT INTO "card_note" VALUES(94070006,'架空カード。公式カードとして扱わない。 本文以外の能力はない。','2026-09-08T00:00:00+09:00');
INSERT INTO "card_note" VALUES(94070007,'架空カード。公式カードとして扱わない。 本文以外の能力はない。','2026-09-08T00:00:00+09:00');
INSERT INTO "card_note" VALUES(94070008,'架空カード。公式カードとして扱わない。 本文以外の能力はない。','2026-09-08T00:00:00+09:00');
INSERT INTO "card_note" VALUES(94070009,'架空カード。公式カードとして扱わない。 本文以外の能力はない。','2026-09-08T00:00:00+09:00');
CREATE TABLE card_set (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
INSERT INTO "card_set" VALUES(94070,'仮想因果検査・固定カード集合');
CREATE TABLE card_tag (
    card_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (card_id, tag)
);
CREATE TABLE card_tribe (
    card_id INTEGER NOT NULL,
    tribe_id INTEGER NOT NULL,
    PRIMARY KEY (card_id, tribe_id)
);
CREATE TABLE meta_deck (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT,
    url TEXT UNIQUE,
    name TEXT,
    tier TEXT,
    format TEXT,
    updated_on TEXT,
    fetched_at TEXT
);
CREATE TABLE meta_deck_card (
    deck_id INTEGER,
    card_name TEXT,
    count INTEGER,
    card_id INTEGER
);
CREATE TABLE skill_name (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE tribe (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE INDEX idx_atom_tag_tag ON atom_tag (kind, tag);
CREATE INDEX idx_anchor_require_card ON anchor_require (card_id);
DELETE FROM "sqlite_sequence";
COMMIT;
