"""公式カード取得の差分更新テスト。"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from svdeck.common.db import connect  # noqa: E402
from svdeck.data_access.fetch import _effect_changed, find_changed_card_ids, insert_card, update_card  # noqa: E402


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


def test_keyword_acquisition_and_database_refresh(tmp_path: Path, monkeypatch: Any) -> None:
    from svdeck.data_access import fetch
    db_path = tmp_path / 'cards.db'
    conn = connect(db_path)
    conn.execute("INSERT INTO ability_keyword(title,text) VALUES ('旧語','旧定義')")
    conn.commit()
    conn.close()
    urls = []
    def payload(url: str) -> dict[str, Any]:
        urls.append(url)
        return {'data': {'ability_key_word_list': [{'title': '守護', 'text': '公式の説明'}]}}
    monkeypatch.setattr(fetch, '_get_json', payload)
    monkeypatch.setattr(fetch, 'connect', lambda: connect(db_path))
    fetch.run_keywords()
    conn = connect(db_path)
    try:
        assert conn.execute('SELECT title,text FROM ability_keyword').fetchall() == [('守護', '公式の説明')]
        assert urls == [fetch.KEYWORDS_API_URL + '?lang=ja']
    finally:
        conn.close()


def test_keyword_failure_preserves_saved_dictionary(tmp_path: Path, monkeypatch: Any) -> None:
    from svdeck.data_access import fetch
    import pytest
    db_path = tmp_path / 'cards.db'
    conn = connect(db_path)
    conn.execute("INSERT INTO ability_keyword(title,text) VALUES ('守護','保存済み')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(fetch, 'connect', lambda: connect(db_path))
    def fail() -> list[tuple[str, str]]:
        raise OSError('offline')
    monkeypatch.setattr(fetch, 'fetch_keywords', fail)
    with pytest.raises(OSError, match='offline'):
        fetch.run_keywords()
    conn = connect(db_path)
    try:
        assert conn.execute('SELECT text FROM ability_keyword').fetchone()[0] == '保存済み'
    finally:
        conn.close()


def test_merged_fetch_cli_selects_card_and_keyword_operations(monkeypatch: Any) -> None:
    from svdeck.data_access import fetch
    import pytest
    calls = []
    monkeypatch.setattr(fetch, 'run', lambda refresh=False: calls.append(('cards', refresh)))
    monkeypatch.setattr(fetch, 'run_keywords', lambda: calls.append(('keywords',)))
    fetch.main([])
    assert calls == [('cards', False), ('keywords',)]
    calls.clear()
    fetch.main(['--refresh'])
    assert calls == [('cards', True), ('keywords',)]
    calls.clear()
    fetch.main(['--keywords-only'])
    assert calls == [('keywords',)]
    calls.clear()
    with pytest.raises(SystemExit) as error:
        fetch.main(['--unknown'])
    assert error.value.code == 1
    assert calls == []
