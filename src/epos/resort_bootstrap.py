"""Explicit bootstrap for the Resort world runtime.

Importing :mod:`epos` stays side-effect free. Resort-specific behavior now
lives in canonical services, so the bootstrap remains as a compatibility hook
for entry points that call it explicitly.
"""

from __future__ import annotations

_RUNTIME_BOOTSTRAPPED = False
_GUI_BOOTSTRAPPED = False


def bootstrap_resort_runtime() -> None:
    """Initialize the Resort runtime compatibility hook without runtime replacements."""

    global _RUNTIME_BOOTSTRAPPED
    _RUNTIME_BOOTSTRAPPED = True


def bootstrap_resort_gui() -> None:
    """Initialize the Resort GUI compatibility hook without runtime replacements."""

    global _GUI_BOOTSTRAPPED
    bootstrap_resort_runtime()
    _GUI_BOOTSTRAPPED = True
