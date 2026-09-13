"""公開開始で実験の採点履歴だけを除き、カード注記と旧版を保持する。"""
import hashlib
import re
from pathlib import Path

import pytest

from svdeck.discovery import packet, start
from svdeck.discovery_evidence import operational_principles
from test_discovery import make_db


def test_unmarked_document_keeps_previous_selection() -> None:
    text = "# 表題\n## 1. 目的\n本命\n## 2. 外\n別途\n## 3. 工程\n用途\n## 5. 判断\n基準\n"
    previous = "\n".join(s for s in re.split(r"(?=^## )", text, flags=re.MULTILINE)
                         if re.match(r"## (?:1\.|1\.5 |3\.|5\.|6\.|7\.|8\.)", s))
    assert operational_principles(text) == previous


def test_history_heading_cannot_change_operational_section() -> None:
    text = ("## 1. 目的\n本人の用途評価は残す\n<!-- discovery-history:start -->\n"
            "## 2. 実験の正解\nA=test/B=drop\n<!-- discovery-history:end -->\n"
            "追加原則\n<!-- discovery-history:start -->\n別試行の採点\n"
            "<!-- discovery-history:end -->\n末尾原則\n")
    assert operational_principles(text) == "## 1. 目的\n本人の用途評価は残す\n追加原則\n末尾原則\n"


@pytest.mark.parametrize("boundary", [
    "<!-- discovery-history:start -->\n未終了",
    "<!-- discovery-history:end -->\n未開始",
    "<!-- discovery-history:start -->\n<!-- discovery-history:start -->\n<!-- discovery-history:end -->",
    "<!-- discovery-history:start -->\n<!-- discovery-history:end -->\n<!-- discovery-history:end -->",
    "<!-- discovery-history:stop -->",
    "同じ行 <!-- discovery-history:start -->",
])
def test_broken_history_boundaries_are_rejected(boundary: str) -> None:
    with pytest.raises(ValueError, match="実験履歴"):
        operational_principles("## 1. 目的\n" + boundary)


def test_new_packet_changes_only_principles_and_keeps_frozen_input(tmp_path: Path) -> None:
    db = tmp_path / "cards.db"
    make_db(db)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "rules.md").write_text("完全なルール本文\n", encoding="utf-8")
    source = "## 1. 目的\n役割分担の評価原則\n過去試行の採点A=test/B=drop\n## 5. 判断\n供給側の注記も参照\n"
    (docs / "design.md").write_text(source, encoding="utf-8")
    old = tmp_path / "old"
    start(old, db, "ウィッチ", "rotation", "新しい種", docs)
    old_packet = packet(old, None, "develop")
    old_files = {p.relative_to(old): hashlib.sha256(p.read_bytes()).hexdigest() for p in old.rglob("*") if p.is_file()}
    db_hash = hashlib.sha256(db.read_bytes()).hexdigest()
    fixed = source.replace("過去試行の採点A=test/B=drop\n", "<!-- discovery-history:start -->\n過去試行の採点A=test/B=drop\n<!-- discovery-history:end -->\n")
    (docs / "design.md").write_text(fixed, encoding="utf-8")
    new = tmp_path / "new"
    start(new, db, "ウィッチ", "rotation", "新しい種", docs)
    new_packet = packet(new, None, "develop")
    before, after = old_packet["data"]["context"], new_packet["data"]["context"]
    assert "A=test/B=drop" not in after["principles"]
    assert "役割分担の評価原則" in after["principles"]
    assert "供給側の注記も参照" in after["principles"]
    assert {k: v for k, v in before.items() if k not in {"principles", "captured_at"}} == {k: v for k, v in after.items() if k not in {"principles", "captured_at"}}
    assert {c["card_id"]: c["note"] for c in after["cards"]}[2] == "効果では進化時を誘発しない"
    assert packet(old, None, "develop") == old_packet
    assert old_files == {p.relative_to(old): hashlib.sha256(p.read_bytes()).hexdigest() for p in old.rglob("*") if p.is_file()}
    assert hashlib.sha256(db.read_bytes()).hexdigest() == db_hash


def test_bad_document_does_not_publish_a_session(tmp_path: Path) -> None:
    db = tmp_path / "cards.db"
    make_db(db)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "rules.md").write_text("ルール", encoding="utf-8")
    (docs / "design.md").write_text("## 1. 目的\n<!-- discovery-history:start -->\n採点", encoding="utf-8")
    session = tmp_path / "run"
    with pytest.raises(ValueError, match="実験履歴"):
        start(session, db, "ウィッチ", "rotation", "新しい種", docs)
    assert not (session / "context.json").exists()
