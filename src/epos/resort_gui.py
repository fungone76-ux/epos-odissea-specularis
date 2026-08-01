"""GUI dedicata a Seven Nights at Azure Crown."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout

from .gui import EposGameWindow
from .resort_relationships import relationship_snapshot
from .resort_runtime import (
    ResortPack,
    campaign_score,
    campaign_score_tier,
    current_day,
    eligible_events,
)
from .turn_service import TurnResult


def build_resort_gui_status(state, pack: ResortPack) -> dict[str, Any]:
    """Proiezione read-only dello stato Resort destinata alla GUI."""

    location = pack.world.locations.get(state.location_id)
    mission_status = dict(state.flags.get("resort_mission_status", {}))
    revealed = list(state.flags.get("resort_revealed_missions", []))
    missions: list[dict[str, str]] = []
    for mission_id in revealed:
        mission = pack.world.missions.get(mission_id)
        if mission is None:
            continue
        missions.append(
            {
                "id": mission_id,
                "name": mission.name,
                "status": str(mission_status.get(mission_id, "active")),
            }
        )

    present_npcs = [
        npc.name
        for npc in state.npcs.values()
        if npc.present and npc.location_id == state.location_id
    ]
    npc_locations: list[dict[str, Any]] = []
    for npc_id, npc in state.npcs.items():
        npc_location = pack.world.locations.get(npc.location_id)
        npc_locations.append(
            {
                "id": npc_id,
                "name": npc.name,
                "location_id": npc.location_id,
                "location_name": (
                    npc_location.name if npc_location is not None else npc.location_id
                ),
                "with_player": npc.location_id == state.location_id,
            }
        )

    events = [event.title for event in eligible_events(state, pack)]
    relationships = {
        npc_id: relationship_snapshot(state, npc_id)
        for npc_id in pack.world.npc_canon
        if npc_id in state.npcs
    }
    debt_due = bool(state.flags.get("resort_debt_due", False))
    days_left = max(
        0,
        int(state.flags.get("resort_debt_due_day", 7)) - current_day(state),
    )

    return {
        "day": current_day(state),
        "phase": state.time_phase,
        "location_id": state.location_id,
        "location_name": location.name if location else state.location_id,
        "score": campaign_score(state),
        "score_tier": campaign_score_tier(state),
        "missions": missions,
        "present_npcs": present_npcs,
        "npc_locations": npc_locations,
        "intro_completed": bool(state.flags.get("resort_intro_completed", False)),
        "eligible_events": events,
        "relationships": relationships,
        "debt_due": debt_due,
        "days_left": days_left,
        "completed_missions": list(
            state.flags.get("resort_completed_missions", [])
        ),
        "failed_missions": list(state.flags.get("resort_failed_missions", [])),
    }


class ResortGameWindow(EposGameWindow):
    """Finestra PySide6 del Resort con LLM e renderer reali."""

    def __init__(
        self,
        service,
        state,
        resort_pack: ResortPack,
        title: str = "Seven Nights at Azure Crown",
    ):
        self.resort_pack = resort_pack
        self._resort_texts: list[QLabel] = []
        super().__init__(service, state, title)
        self._refresh_state_panel()

    def _scroll_to_bottom(self) -> None:
        """Mantiene visibile l'ultima riga anche dopo il relayout Qt.

        Un solo singleShot(0) può partire prima che word-wrap e altezze delle
        nuove card siano stati calcolati. Ripetiamo il posizionamento per pochi
        millisecondi e rendiamo visibile esplicitamente l'ultimo widget.
        """

        def apply_scroll() -> None:
            if not hasattr(self, "story_scroll"):
                return
            bar = self.story_scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
            if self.story_layout.count():
                item = self.story_layout.itemAt(self.story_layout.count() - 1)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    self.story_scroll.ensureWidgetVisible(widget, 0, 0)
            bar.setValue(bar.maximum())

        for delay in (0, 25, 75, 160, 300):
            QTimer.singleShot(delay, apply_scroll)

    def _state_extra_layout(self) -> QVBoxLayout | None:
        holder = self.state_text.parentWidget()
        return holder.layout() if holder is not None else None

    def _add_state_widget(self, layout: QVBoxLayout, widget: QLabel) -> None:
        idx = max(layout.count() - 1, 0)
        layout.insertWidget(idx, widget)
        self._resort_texts.append(widget)

    def _label(
        self,
        text: str,
        style: str = "color: #bbb; font-size: 10px;",
        *,
        wrap: bool = True,
    ) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(style)
        label.setWordWrap(wrap)
        return label

    def _refresh_state_panel(self) -> None:
        super()._refresh_state_panel()
        layout = self._state_extra_layout()
        if layout is None:
            return

        for widget in self._resort_texts:
            layout.removeWidget(widget)
            widget.deleteLater()
        self._resort_texts.clear()

        pack = getattr(self, "resort_pack", None)
        if pack is None:
            return
        status = build_resort_gui_status(self.state, pack)

        self._add_state_widget(
            layout,
            self._label("─" * 28, "color: #555; margin-top: 6px;", wrap=False),
        )
        self._add_state_widget(
            layout,
            self._label(
                f"AZURE CROWN · GIORNO {status['day']}/7",
                "color: #e4bd7b; font-weight: bold; font-size: 12px;",
            ),
        )
        self._add_state_widget(
            layout,
            self._label(
                f"{status['phase'].upper()} · {status['location_name']}",
                "color: #d7dce5; font-size: 11px;",
            ),
        )
        self._add_state_widget(
            layout,
            self._label(
                f"Punteggio: {status['score']} · {status['score_tier']}",
                "color: #ffd166; font-weight: bold; font-size: 11px;",
            ),
        )

        debt_text = (
            "SCADENZA DEL DEBITO ATTIVA"
            if status["debt_due"]
            else f"Debito bancario: {status['days_left']} giorni alla scadenza"
        )
        debt_style = (
            "color: #ef6f6c; font-weight: bold; font-size: 10px;"
            if status["debt_due"]
            else "color: #d9a66c; font-size: 10px;"
        )
        self._add_state_widget(layout, self._label(debt_text, debt_style))

        npcs = ", ".join(status["present_npcs"]) or "nessuno"
        self._add_state_widget(
            layout,
            self._label(f"Presenti con te: {npcs}", "color: #9ec5fe; font-size: 10px;"),
        )

        if status["intro_completed"]:
            self._add_state_widget(
                layout,
                self._label(
                    "POSIZIONE NPC",
                    "color: #e4bd7b; font-weight: bold; font-size: 10px; margin-top: 5px;",
                ),
            )
            for npc in status["npc_locations"]:
                marker = "● con te" if npc["with_player"] else "○"
                style = (
                    "color: #8fd694; font-size: 9px; font-weight: bold;"
                    if npc["with_player"]
                    else "color: #aeb6c5; font-size: 9px;"
                )
                self._add_state_widget(
                    layout,
                    self._label(
                        f"{marker} · {npc['name']}: {npc['location_name']}",
                        style,
                    ),
                )

        if status["eligible_events"]:
            self._add_state_widget(
                layout,
                self._label(
                    "Eventi disponibili: " + " · ".join(status["eligible_events"]),
                    "color: #efb6d5; font-size: 10px; font-weight: bold;",
                ),
            )

        if status["missions"]:
            self._add_state_widget(
                layout,
                self._label(
                    "MISSIONI NOTE",
                    "color: #e4bd7b; font-weight: bold; font-size: 10px; margin-top: 5px;",
                ),
            )
            icons = {"active": "•", "completed": "✓", "failed": "✕"}
            for mission in status["missions"]:
                icon = icons.get(mission["status"], "•")
                style = "color: #c8ced8; font-size: 9px;"
                if mission["status"] == "completed":
                    style = "color: #9bd59b; font-size: 9px;"
                elif mission["status"] == "failed":
                    style = "color: #e07a7a; font-size: 9px;"
                self._add_state_widget(
                    layout,
                    self._label(f"{icon} {mission['name']}", style),
                )

        self._add_state_widget(
            layout,
            self._label(
                "RELAZIONI",
                "color: #e4bd7b; font-weight: bold; font-size: 10px; margin-top: 5px;",
            ),
        )
        for npc_id, rel in status["relationships"].items():
            canon = pack.world.npc_canon.get(npc_id)
            name = canon.name if canon else npc_id
            self._add_state_widget(
                layout,
                self._label(
                    f"{name}: fiducia {rel['trust']} · attrazione {rel['attraction']} · rispetto {rel['respect']} · gelosia {rel['jealousy']}",
                    "color: #b7a7d8; font-size: 9px;",
                ),
            )

    def _on_result(self, payload) -> None:
        kind, data = payload
        super()._on_result(payload)
        if kind == "turn" and isinstance(data, TurnResult):
            changes = dict(data.campaign_changes or {})
            for mission_id in changes.get("unlocked_missions", []):
                mission = self.resort_pack.world.missions.get(mission_id)
                name = mission.name if mission else mission_id
                self._append_system(f"MISSIONE SBLOCCATA: {name}")

            for change in changes.get("mission_changes", []):
                mission = self.resort_pack.world.missions.get(change["mission_id"])
                name = mission.name if mission else change["mission_id"]
                delta = int(change.get("score_delta", 0))
                sign = "+" if delta >= 0 else ""
                status = (
                    "COMPLETATA"
                    if change.get("status") == "completed"
                    else "FALLITA"
                )
                self._append_system(
                    f"MISSIONE {status}: {name} · {sign}{delta} punti · "
                    f"totale {change.get('score_total', campaign_score(self.state))}"
                )

        self._refresh_state_panel()
        self._scroll_to_bottom()
