"""取得用CLIの引数を、DBやネットワーク操作より先に検査する。"""

from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from svdeck import meta
from svdeck.db import connect
from test_discovery import make_db


@pytest.mark.parametrize("args,code", [(["--help"], 0), (["--unknown-option"], 2)])
def test_help_and_invalid_args_do_not_start_fetch(
    monkeypatch: pytest.MonkeyPatch, args: list[str], code: int,
) -> None:
    # AI_NOTE: 引数の表示・拒否だけで取得処理に到達しないことを確認する。
    def forbidden_run(db: Path) -> None:
        raise AssertionError(f"取得処理に入ってはいけない: {db}")

    monkeypatch.setattr(meta, "run", forbidden_run)
    with pytest.raises(SystemExit) as result:
        meta.main(args)
    assert result.value.code == code


def test_selected_database_receives_only_meta_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 指定先への書込みを実際に通し、カード本文とユーザー注記を維持する。
    selected = tmp_path / "comparison.db"
    make_db(selected)
    conn = connect(selected)
    original_cards = conn.execute("SELECT * FROM card ORDER BY card_id").fetchall()
    original_notes = conn.execute("SELECT * FROM card_note ORDER BY card_id").fetchall()
    conn.close()

    def selected_connect(path: Path) -> sqlite3.Connection:
        assert path == selected
        return connect(path)

    monkeypatch.setattr(meta, "connect", selected_connect)
    monkeypatch.setattr(meta, "collect_deck_links", lambda: [meta.DeckLink("gamewith", "test://deck", "保存例", "1", "rotation")])
    monkeypatch.setattr(meta, "collect_deck_detail", lambda link: meta.DeckDetail("2026-09-08", [("核", 3)]))
    meta.main(["--db", str(selected)])
    conn = connect(selected)
    assert conn.execute("SELECT name,url,format FROM meta_deck").fetchall() == [("保存例", "test://deck", "rotation")]
    assert conn.execute("SELECT card_id,count FROM meta_deck_card").fetchall() == [(1, 3)]
    assert conn.execute("SELECT * FROM card ORDER BY card_id").fetchall() == original_cards
    assert conn.execute("SELECT * FROM card_note ORDER BY card_id").fetchall() == original_notes
    conn.close()


def test_public_help_exits_without_creating_database(tmp_path: Path) -> None:
    # AI_NOTE: 問題が起きたpython -mの入口で、未作成のDBを指定してもヘルプだけを返す。
    db = tmp_path / "not-created.db"
    result = subprocess.run([sys.executable, "-m", "svdeck.meta", "--db", str(db), "--help"],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    assert "--db" in result.stdout and "[meta]" not in result.stdout
    assert not db.exists()
