import os
import subprocess
import sys


def test_import_epos_is_headless_and_side_effect_free():
    code = r'''
import builtins
import sys

real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "PySide6" or name.startswith("PySide6."):
        raise AssertionError("import epos must not import PySide6")
    return real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import epos

assert "PySide6" not in sys.modules
assert "epos.resort_manual_time_gui_patch" not in sys.modules
assert "epos.resort_runtime_patches" not in sys.modules
assert "epos.resort_npc_action_patch" not in sys.modules
assert "epos.resort_beach_runtime_patch" not in sys.modules
assert "epos.resort_save_audit_patch" not in sys.modules
assert "epos.resort_single_call_intent_patch" not in sys.modules
'''
    env = dict(os.environ)
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_headless_resort_bootstrap_does_not_import_qt():
    code = r'''
import builtins
import sys

real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "PySide6" or name.startswith("PySide6."):
        raise AssertionError("headless Resort bootstrap must not import PySide6")
    return real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
from epos.resort_bootstrap import bootstrap_resort_runtime
bootstrap_resort_runtime()

assert "PySide6" not in sys.modules
assert "epos.resort_manual_time_gui_patch" not in sys.modules
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.getcwd(),
        env=dict(os.environ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
