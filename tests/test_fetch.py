"""公式カード取得の差分更新テスト。"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from svdeck.db import connect  # noqa: E402
from svdeck.fetch import _effect_changed, find_changed_card_ids, insert_card, update_card  # noqa: E402


CARD_ID = 10632310


def _api_data(skill_text: str, tribes: list[int] | None = None) -> dict[str, Any]:
    common = {
        "name": "正常の侵食",
        "name_ruby": "ノーマル・エロージョン",
        "skill_text": skill_text,
        "flavour_text": "",
        "cost": 1,
        "atk": 0,
        "life": 0,
        "class": 3,
        "type": 4,
        "rarity": 2,
        "card_set_id": 10006,
        "is_token": False,
        "deck_enabled_num": 3,
        "is_include_rotation": True,
        "base_card_id": 0,
        "original_card_id": 0,
        "tribes": tribes or [],
    }
    return {
        "card_details": {str(CARD_ID): {"common": common, "evo": [], "style_card_list": []}},
        "specific_effect_card_info": {},
        "specific_effect_type_names": {},
    }


def test_refresh_updates_mirror_and_preserves_user_layer(tmp_path: Path) -> None:
    conn = connect(tmp_path / "cards.db")
    old_text = "自分のデッキからウィッチ・フォロワー2枚を引く。"
    new_text = "自分のデッキから2枚を引く。"
    try:
        insert_card(conn, CARD_ID, _api_data(old_text, [7]))
        conn.execute("INSERT INTO card_note(card_id, note) VALUES (?, ?)", (CARD_ID, "利用者メモ"))
        conn.execute("INSERT INTO card_tag(card_id, tag) VALUES (?, ?)", (CARD_ID, "確認済み"))
        diffs, stale = update_card(conn, CARD_ID, _api_data(new_text, [8]))

        assert diffs["skill_text"] == (old_text, new_text)
        assert stale is True
        assert conn.execute("SELECT skill_text FROM card WHERE card_id = ?", (CARD_ID,)).fetchone()[0] == new_text
        assert conn.execute("SELECT tribe_id FROM card_tribe WHERE card_id = ?", (CARD_ID,)).fetchall() == [(8,)]
        assert conn.execute("SELECT note FROM card_note WHERE card_id = ?", (CARD_ID,)).fetchone()[0] == "利用者メモ"
        assert conn.execute("SELECT tag FROM card_tag WHERE card_id = ?", (CARD_ID,)).fetchone()[0] == "確認済み"
    finally:
        conn.close()


def test_find_changed_card_ids_ignores_new_and_unchanged_cards(tmp_path: Path) -> None:
    conn = connect(tmp_path / "cards.db")
    old_text = "旧能力"
    try:
        insert_card(conn, CARD_ID, _api_data(old_text))
        unchanged = _api_data(old_text)
        assert find_changed_card_ids(conn, unchanged) == []

        changed = _api_data("新能力")
        assert find_changed_card_ids(conn, changed) == [CARD_ID]

        changed["card_details"]["99999999"] = changed["card_details"].pop(str(CARD_ID))
        assert find_changed_card_ids(conn, changed) == []
    finally:
        conn.close()


def test_flavour_only_evolution_change_does_not_stale_effect_analysis() -> None:
    old_evo = '{"flavour_text":"昨日のアタシ","skill_text":"同じ能力"}'
    new_evo = '{"flavour_text":"昨日の私","skill_text":"同じ能力"}'
    assert _effect_changed({"evo_json": (old_evo, new_evo)}) is False
    changed_skill = '{"flavour_text":"昨日の私","skill_text":"新しい能力"}'
    assert _effect_changed({"evo_json": (old_evo, changed_skill)}) is True
