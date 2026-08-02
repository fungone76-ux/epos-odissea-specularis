"""Explicit bootstrap for the Resort world runtime.

Importing :mod:`epos` must stay side-effect free.  Resort-specific runtime
extensions are installed only when a Resort entry point explicitly asks for
them.  GUI extensions are opt-in so headless tests and scripts never import
PySide6 through the package root.
"""

from __future__ import annotations

_RUNTIME_BOOTSTRAPPED = False
_GUI_BOOTSTRAPPED = False


def bootstrap_resort_runtime() -> None:
    """Install Resort runtime extensions without importing GUI dependencies."""

    global _RUNTIME_BOOTSTRAPPED
    if _RUNTIME_BOOTSTRAPPED:
        return

    from .resort_runtime_patches import install_resort_runtime_patches
    from .resort_npc_action_patch import install_resort_npc_action_patch
    from .resort_beach_runtime_patch import install_resort_beach_runtime_patch
    from .resort_save_audit_patch import install_resort_save_audit_patch
    from .resort_single_call_intent_patch import install_resort_single_call_intent_patch

    install_resort_runtime_patches()
    install_resort_npc_action_patch()
    install_resort_beach_runtime_patch()
    install_resort_save_audit_patch()
    install_resort_single_call_intent_patch()
    _RUNTIME_BOOTSTRAPPED = True


def bootstrap_resort_gui() -> None:
    """Install Resort GUI extensions.

    PySide6 is imported only inside the GUI patch module, and only after a GUI
    entry point calls this function.
    """

    global _GUI_BOOTSTRAPPED
    if _GUI_BOOTSTRAPPED:
        return

    bootstrap_resort_runtime()
    from .resort_manual_time_gui_patch import install_resort_manual_time_gui_patch

    install_resort_manual_time_gui_patch()
    _GUI_BOOTSTRAPPED = True
