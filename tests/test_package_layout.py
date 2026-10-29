"""Responsibility packages keep one implementation behind legacy names."""
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('old,new', [
    ('svdeck.battle', 'svdeck.battle_env.battle'),
    ('svdeck.discovery', 'svdeck.search.discovery'),
    ('svdeck.explore', 'svdeck.search.explore'),
    ('svdeck.fetch', 'svdeck.data_access.fetch'),
    ('svdeck.db', 'svdeck.common.db'),
    ('svdeck.worker', 'svdeck.common.worker'),
])
def test_legacy_import_shares_implementation(old: str, new: str) -> None:
    # AI_NOTE: Shared module identity preserves patches, classes and mutable globals across both import forms.
    assert importlib.import_module(old) is importlib.import_module(new)


@pytest.mark.parametrize('old,new', [
    ('svdeck.discovery', 'svdeck.search.discovery'),
    ('svdeck.worker', 'svdeck.common.worker'),
    ('svdeck.battle', 'svdeck.battle_env.battle'),
])
def test_legacy_and_canonical_cli_help(old: str, new: str) -> None:
    # AI_NOTE: Only --help is used; no card collection, database writes, server or worker is started.
    results = [subprocess.run([sys.executable, '-m', name, '--help'], capture_output=True, text=True) for name in (old, new)]
    assert [result.returncode for result in results] == [0, 0]
    assert results[0].stdout == results[1].stdout
    assert not results[0].stderr


def test_owned_assets_and_database_location() -> None:
    # AI_NOTE: Moving Python files must not silently create a new card DB or lose shipped browser/data assets.
    from svdeck.battle_env import battle, battle_server
    from svdeck.common import db, experiments
    from svdeck.search.bench import FULFILLMENT_MAP_PATH
    from svdeck.data_prep.promote import PROMOTED_PATH
    root = Path(__file__).resolve().parents[1]
    assert db.DB_PATH == root / 'data/cards.db'
    assert json.loads((Path(battle.__file__).parent / 'data/battle_cases.json').read_text())
    assert (battle_server.WEB_ROOT / 'index.html').is_file()
    assert (experiments.ASSETS / 'index.html').is_file()
    assert FULFILLMENT_MAP_PATH.is_file()
    assert PROMOTED_PATH.is_file()


@pytest.mark.parametrize('old,new', [
    ('svdeck.atoms', 'svdeck.data_prep.atoms'),
    ('svdeck.data_access.atoms', 'svdeck.data_prep.atoms'),
    ('svdeck.data_access.memo', 'svdeck.data_prep.memo'),
    ('svdeck.data_access.promote', 'svdeck.data_prep.promote'),
    ('svdeck.data_access.retag', 'svdeck.data_prep.retag'),
    ('svdeck.vectorize', 'svdeck.battle_env.vectorize'),
    ('svdeck.data_access.vectorize', 'svdeck.battle_env.vectorize'),
])
def test_relocated_data_modules_share_implementation(old: str, new: str) -> None:
    assert importlib.import_module(old) is importlib.import_module(new)


def test_legacy_keyword_cli_only_updates_keywords(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    from svdeck.data_access import fetch
    calls = []
    monkeypatch.setattr(fetch, 'run_keywords', lambda: calls.append('keywords'))
    monkeypatch.setattr(fetch, 'run', lambda **kwargs: pytest.fail('must not crawl cards'))
    for name in ('svdeck.keywords', 'svdeck.data_access.keywords'):
        runpy.run_module(name, run_name='__main__')
    assert calls == ['keywords', 'keywords']
