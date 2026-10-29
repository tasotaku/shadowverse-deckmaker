"""対戦環境・対戦AIとその検証。"""
from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
    # Older callers used svdeck.battle as the engine module.
    return getattr(import_module("svdeck.battle.battle"), name)
