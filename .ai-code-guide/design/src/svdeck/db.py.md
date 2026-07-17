---
source_file: src/svdeck/db.py
---

# ファイル: db.py
## 目的
SQLiteのスキーマ定義と接続ヘルパー。テーブルを4層（公式ミラー層／ユーザレイヤ／派生層／外部メタ層）に分け、「作り直してよいデータ」と「絶対に消さないデータ」の境界をスキーマの層で表現する。 <!-- @inferred -->

## 関数: connect
### 目的
DB接続とスキーマ作成を一体化する。呼ぶだけで足りないテーブルが作られ、既存データは消えない。
### 要件・制約
- ユーザレイヤ（card_note / card_tag / card_flag / anchor_require）は再クロール・再実行で絶対に消えない。全テーブルを CREATE IF NOT EXISTS のみで作ることで担保 <!-- @inferred -->
- anchor_require は不成立確定でも DELETE せず status='dead' で残す（判定根拠を失わないため）。recheck の「前はdead→今は供給あり」検出の前提 <!-- @inferred -->
- DB_PATH はデフォルト引数でなく呼び出し時に解決する（def時束縛だとテストの monkeypatch が効かない） <!-- @inferred -->
- 例外: DB接続失敗は握りつぶさず伝播（外部I/O境界） <!-- @inferred -->
### 方針
スキーマは1つの文字列 `_SCHEMA` に集約し executescript で流す。ただし card_vschema だけは vectorize.py 側で CREATE している（スキーマ定義が2箇所に分かれている点は意図未確認）。 <!-- @inferred -->
### 構成
1. DBパス定義 → anchor: "DB_PATH = Path(__file__)"
2. スキーマ本体（4層のテーブル群） → anchor: "CREATE TABLE IF NOT EXISTS card ("
3. 接続＋スキーマ適用 → anchor: "def connect("
