"""Legacy module names resolve to the one canonical implementation."""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from types import CodeType, ModuleType

_GROUPS = {'battle_env': ('battle', 'battle_ai', 'battle_cards', 'battle_combat', 'battle_compact', 'battle_decks', 'battle_frontier', 'battle_frontier_cache', 'battle_frontier_catalog', 'battle_frontier_compare', 'battle_frontier_export', 'battle_frontier_export_native', 'battle_frontier_fast', 'battle_frontier_io', 'battle_frontier_native', 'battle_frontier_native_core', 'battle_frontier_native_delta', 'battle_frontier_native_index', 'battle_frontier_packed', 'battle_frontier_por', 'battle_frontier_skyline', 'battle_lookahead', 'battle_meta_cards', 'battle_practical', 'battle_response', 'battle_role_ai', 'battle_role_response', 'battle_role_search', 'battle_roles', 'battle_rules', 'battle_server', 'battle_training', 'combat_benchmark'), 'common': ('db', 'experiments', 'inquiry_journal', 'journal_store', 'worker', 'worker_journal'), 'data_access': ('article_text', 'atoms', 'fetch', 'keywords', 'memo', 'meta', 'promote', 'retag', 'vectorize'), 'search': ('augment', 'bench', 'discovery', 'discovery_compare', 'discovery_cycle', 'discovery_evidence', 'discovery_inquiry', 'discovery_opponent', 'discovery_read', 'discovery_run', 'discovery_sources', 'explore', 'paraphrase', 'profile', 'require', 'reverse', 'strength', 'vector')}
_TARGETS = {"svdeck." + name: "svdeck." + group + "." + name
            for group, names in _GROUPS.items() for name in names}


class _AliasLoader(importlib.abc.InspectLoader):
    def __init__(self, name: str, target: str) -> None:
        # AI_NOTE: Alias imports return the canonical object so globals and monkeypatches are shared.
        self.name, self.target = name, target

    def create_module(self, spec: object) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        sys.modules[self.name] = importlib.import_module(self.target)

    def get_source(self, fullname: str) -> str:
        # AI_NOTE: Old python -m commands execute the real module's own __main__ path and exit handling.
        return "import runpy\nrunpy.run_module(" + repr(self.target) + ", run_name='__main__', alter_sys=True)\n"

    def get_code(self, fullname: str) -> CodeType:
        return compile(self.get_source(fullname), "<legacy " + fullname + ">", "exec")


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: object = None, target: ModuleType | None = None) -> importlib.machinery.ModuleSpec | None:
        # AI_NOTE: Only the finite old svdeck module list is redirected; all other imports use Python's loaders.
        destination = _TARGETS.get(fullname)
        return importlib.util.spec_from_loader(fullname, _AliasLoader(fullname, destination)) if destination else None


def install() -> None:
    # AI_NOTE: One finder preserves old saved scripts without restoring flat implementation files.
    if not any(isinstance(finder, _AliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder())
