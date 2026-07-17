---
source_file: src/svdeck/effects.py
---

# ファイル: effects.py
## 目的
参照先効果（クレスト/結晶/アクセラレート/信仰）を単体カードAPIから収集して specific_effect 表（ミラー層）へ保存する。カード一覧API（fetch.py が使う方）はこのテキストを返さず、単体カードAPI /web/CardList/card だけが specific_effect_card_info として返すため、全カードを1枚ずつ叩く必要がある。fetch.py（一覧で安く取れる分）→ effects.py（単体でしか取れない分）の2段構えは「一覧→詳細クロール」の定石で、開発者レビューで方式ごと承認済み。 <!-- @confirmed 2026-07-17 -->

## 要件・制約
- 増分クロール方式: 効果の有無に関わらず走査済みカードを effect_crawl 表に記録し、次回は「card にあって effect_crawl に無い」カードだけ叩く。全カード総当たりは初回のみで、新弾（約2ヶ月に1回）以降は新カード分だけ。開発者レビューで承認済み。 <!-- @confirmed 2026-07-17 -->
- 対象をテキストで絞る代案は不成立: 結晶/アクセラレートはカード本文（skill_text）にも一覧APIの原文（common_json/style_json）にも痕跡が一切現れないため、事前に持ち主を見分ける材料が無い。消去法で全カード走査＋記録方式。 <!-- @confirmed 2026-07-17 -->
- 公式APIへの負荷対策としてリクエスト間隔 0.35 秒（fetch.py と同じ）。 <!-- @inferred -->
- 50枚ごとに途中確定（commit）する。全826枚×0.35秒≈5分の長丁場のため、途中で落ちても走査済み分は残り、再実行で続きから再開できる。fetch.py の「最後に1回で確定」と方針が逆なのは作業の性質の差（1枚ずつ独立した積み上げ vs 一括の取り直し）で、ファイルを分けたまま保つ理由でもある。 <!-- @confirmed 2026-07-17 -->
- fetch.py の run から接続を受け取り、新弾取り込み直後の増分クロールとして自動で連鎖実行される（単独実行も可）。運用上は fetch 1コマンドで card→specific_effect まで揃う。 <!-- @confirmed 2026-07-17 -->
- 既知の穴: 一度走査したカードは二度と叩かないため、参照先効果のエラッタ（公式の文面修正）を取り込めない。fetch.py の --refresh 実装時に effect_crawl の記録も消して再走査する形で揃える想定。 <!-- @confirmed 2026-07-17 -->
- HTTP境界の例外は握りつぶさず伝播。 <!-- @inferred -->

## 関数: fetch_card
### 目的
カードIDを1つ指定して単体カードAPIを叩く通信境界。specific_effect_card_info を含む data を返す。失敗は伝播。
### 構成
1. 取得と復号 → anchor: "def fetch_card("

## 関数: save_effects
### 目的
1枚分の応答から参照先効果を取り出して specific_effect へ保存し、件数を返す。効果種別の表示名はAPI同梱の辞書（specific_effect_type_names）から引く。
### 要件・制約
- INSERT OR REPLACE（同じ効果IDの行があれば入れ直す）なので再実行しても二重登録されない。 <!-- @inferred -->
### 構成
1. 効果の保存 → anchor: "def save_effects("

## 関数: run
### 目的
エントリポイント。未クロールのカードだけを対象に単体APIを周回し、効果を保存・走査記録を付ける。
### 構成
1. 未クロール対象の抽出 → anchor: "SELECT card_id FROM card WHERE card_id NOT IN (SELECT card_id FROM effect_crawl)"
2. 周回と走査記録 → anchor: "INSERT OR REPLACE INTO effect_crawl"
3. 途中確定（50枚ごと） → anchor: "if i % 50 == 0:"
4. 完了報告 → anchor: "SELECT COUNT(*) FROM specific_effect"
