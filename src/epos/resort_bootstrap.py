"""Explicit bootstrap for the Resort world runtime.

Importing :mod:`epos` stays side-effect free. Resort-specific extensions are
installed only when a Resort entry point explicitly asks for them. GUI
extensions remain opt-in so headless tests and scripts never import PySide6.
"""

from __future__ import annotations

_RUNTIME_BOOTSTRAPPED = False
_GUI_BOOTSTRAPPED = False


def bootstrap_resort_runtime() -> None:
    """Install the remaining Resort runtime extensions without GUI imports."""

    global _RUNTIME_BOOTSTRAPPED
    if _RUNTIME_BOOTSTRAPPED:
        return

    from .resort_npc_action_patch import install_resort_npc_action_patch
    from .resort_beach_runtime_patch import install_resort_beach_runtime_patch
    from .resort_save_audit_patch import install_resort_save_audit_patch
    from .resort_single_call_intent_patch import install_resort_single_call_intent_patch

    install_resort_npc_action_patch()
    install_resort_beach_runtime_patch()
    install_resort_save_audit_patch()
    install_resort_single_call_intent_patch()
    _RUNTIME_BOOTSTRAPPED = True


def bootstrap_resort_gui() -> None:
    """Install Resort GUI extensions only from an explicit GUI entry point."""

    global _GUI_BOOTSTRAPPED
    if _GUI_BOOTSTRAPPED:
        return

    bootstrap_resort_runtime()
    from .resort_manual_time_gui_patch import install_resort_manual_time_gui_patch

    install_resort_manual_time_gui_patch()
    _GUI_BOOTSTRAPPED = True
