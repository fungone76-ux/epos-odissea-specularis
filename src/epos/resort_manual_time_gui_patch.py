"""GUI patch: Resort time advances only when the player presses a button."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QPushButton

_INSTALLED = False


def install_resort_manual_time_gui_patch() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import resort_gui

    original_init = resort_gui.ResortGameWindow.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.manual_time_callback = None

        layout = self._state_extra_layout()
        if layout is None:
            return

        button = QPushButton("AVANZA TEMPO")
        button.setToolTip(
            "Fa avanzare volontariamente la fase del giorno e applica lo schedule delle NPC."
        )
        button.setStyleSheet(
            "QPushButton {"
            "background: #5b4636; color: #f5d7a1; border: 1px solid #9a744f; "
            "border-radius: 4px; padding: 7px; font-weight: bold; font-size: 10px;"
            "}"
            "QPushButton:hover { background: #725842; }"
            "QPushButton:pressed { background: #463629; }"
            "QPushButton:disabled { color: #777; background: #333; border-color: #444; }"
        )
        button.clicked.connect(lambda: _advance_time_clicked(self))
        layout.insertWidget(max(layout.count() - 1, 0), button)
        self._manual_time_button = button

    resort_gui.ResortGameWindow.__init__ = patched_init
    _INSTALLED = True


def _advance_time_clicked(window: Any) -> None:
    callback = getattr(window, "manual_time_callback", None)
    if not callable(callback):
        window._append_system("Avanzamento del tempo non configurato.")
        return

    button = getattr(window, "_manual_time_button", None)
    if button is not None:
        button.setEnabled(False)

    try:
        result = dict(callback() or {})
        if result.get("advanced"):
            day = result.get("day", "?")
            phase = str(result.get("phase", "")).upper()
            window._append_system(f"TEMPO AVANZATO: giorno {day} · {phase}")
            schedule = list(result.get("schedule", []) or [])
            if schedule:
                window._append_system(
                    f"Schedule applicato: {len(schedule)} spostamenti/aggiornamenti NPC."
                )
        else:
            window._append_system(
                str(result.get("message", "Il tempo non è stato modificato."))
            )
        window._refresh_state_panel()
        window._scroll_to_bottom()
    except Exception as exc:
        window._append_system(f"Errore durante l'avanzamento del tempo: {exc}")
    finally:
        if button is not None:
            button.setEnabled(True)
