"""旧 python -m svdeck.battle の起動を維持する。"""
import runpy

runpy.run_module("svdeck.battle.battle", run_name="__main__", alter_sys=True)
