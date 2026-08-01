"""Odyssey Game Window — estende EposGameWindow con mission tracker.

Aggiunge nel pannello Stato (dopo il contenuto base di EPOS):
- Isola attuale e missione
- Skill richiesta con difficoltà nominale ed effettiva (retry offset)
- Fase di Itaca (missione a 3 fasi)
- Log delle ultime 3 azioni
- Kleos, intuizione, stato emotivo, effetti attivi

Dopo ogni turno, processa il mission tracker per avanzare location.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout

from epos.gui import EposGameWindow
from epos.turn_service import TurnResult

from .odyssey_mission_tracker import OdysseyMissionTracker


class OdysseyGameWindow(EposGameWindow):
    """Finestra di gioco per Odissea Specularis."""

    def __init__(self, service, state, title: str = "Odissea Specularis"):
        # Inizializza PRIMA di super().__init__: il costruttore base chiama
        # _refresh_state_panel(), che qui e sovrascritto e usa questa lista.
        self._odyssey_texts: list[QLabel] = []
        super().__init__(service, state, title)
        self.tracker = OdysseyMissionTracker(state, pack=getattr(service, "pack", None))
        self._refresh_state_panel()

    # -- pannello stato esteso -----------------------------------------------

    def _state_extra_layout(self) -> QVBoxLayout | None:
        """Layout del contenitore del pannello Stato della GUI base.

        La GUI base mette `state_text` + stretch dentro un holder scrollabile:
        le info di Odissea vengono inserite fra i due.
        """
        holder = self.state_text.parentWidget()
        return holder.layout() if holder is not None else None

    def _add_state_widget(self, layout: QVBoxLayout, widget: QLabel) -> None:
        # Inserisce prima dello stretch finale (se presente)
        idx = max(layout.count() - 1, 0)
        layout.insertWidget(idx, widget)
        self._odyssey_texts.append(widget)

    def _refresh_state_panel(self) -> None:
        """Aggiorna il pannello Stato con le info di Odissea."""
        # Chiama il metodo originale per tutto il contenuto base EPOS
        super()._refresh_state_panel()

        layout = self._state_extra_layout()
        if layout is None:
            return

        # Rimuovi eventuali widget odissea precedenti
        for w in self._odyssey_texts:
            layout.removeWidget(w)
            w.deleteLater()
        self._odyssey_texts.clear()

        # Il tracker esiste solo dopo super().__init__
        tracker = getattr(self, "tracker", None)
        if tracker is None:
            return

        # Info missione
        status = tracker.get_status()

        # Separatore
        sep = QLabel("─" * 28)
        sep.setStyleSheet("color: #555; margin-top: 6px;")
        self._add_state_widget(layout, sep)

        # Titolo isola
        loc_label = QLabel(f"🏝️  {status['location_name']}")
        loc_label.setStyleSheet("color: #d4a76a; font-weight: bold; font-size: 12px;")
        loc_label.setWordWrap(True)
        self._add_state_widget(layout, loc_label)

        # Missione
        mission_label = QLabel(f"📜 {status['mission_description']}")
        mission_label.setStyleSheet("color: #bbb; font-size: 10px;")
        mission_label.setWordWrap(True)
        self._add_state_widget(layout, mission_label)

        # Skill richiesta (diff nominale + effettiva dopo retry)
        skill_text = f"Skill: {status['mission_skill'].upper()}"
        if status['mission_alt_skill']:
            skill_text += f" o {status['mission_alt_skill'].upper()}"
        diff_text = f" (diff: {status['mission_difficulty']}"
        if status['retry_offset'] > 0:
            diff_text += f", effettiva: {status['effective_difficulty']} dopo retry"
        diff_text += ")"
        skill_label = QLabel(skill_text + diff_text)
        skill_label.setStyleSheet("color: #888; font-size: 9px; font-style: italic;")
        self._add_state_widget(layout, skill_label)

        # Obiettivo della missione (l'antagonista da affrontare)
        if status.get('mission_target'):
            target_label = QLabel(f"🎯 Obiettivo: {status['mission_target'].upper()}")
            target_label.setStyleSheet("color: #d88; font-size: 10px; font-weight: bold;")
            self._add_state_widget(layout, target_label)

        # Fase di Itaca (missione a 3 fasi)
        if status.get('itaca_phase') is not None:
            phase_label = QLabel(
                f"🏹 Fase {status['itaca_phase'] + 1}/3: {status['itaca_phase_name']}"
            )
            phase_label.setStyleSheet("color: #b9c; font-size: 10px; font-weight: bold;")
            self._add_state_widget(layout, phase_label)

        # Log ultime 3 azioni
        history = status.get('action_history', [])
        if history:
            outcome_icons = {
                "full_success": "✅", "partial_success": "☑️",
                "failure": "❌", "critical_failure": "💥",
            }
            lines = []
            for entry in reversed(history):  # la piu recente in alto
                icon = outcome_icons.get(entry["outcome"], "•")
                mark = "" if entry["relevant"] else " (non rilevante)"
                lines.append(f"{icon} {entry['skill'].upper()}{mark}")
            log_label = QLabel("🕘 " + "  ·  ".join(lines))
            log_label.setStyleSheet("color: #789; font-size: 9px;")
            log_label.setWordWrap(True)
            self._add_state_widget(layout, log_label)

        # Kleos
        kleos_label = QLabel(f"⭐ Kleos: {status['kleos']}")
        kleos_label.setStyleSheet("color: #ffd700; font-weight: bold; font-size: 11px;")
        self._add_state_widget(layout, kleos_label)

        # Stato emotivo
        emotion_label = QLabel(f"❤️  {status['emotional_state']}")
        emotion_label.setStyleSheet("color: #c77; font-size: 10px; font-style: italic;")
        emotion_label.setWordWrap(True)
        self._add_state_widget(layout, emotion_label)

        # Intuizione (se presente)
        if status['intuition']:
            intuition_label = QLabel(f"💭 {status['intuition']}")
            intuition_label.setStyleSheet("color: #aad; font-size: 10px; font-style: italic; padding-left: 4px;")
            intuition_label.setWordWrap(True)
            self._add_state_widget(layout, intuition_label)

        # Turni senza progresso
        if status['turns_without_progress'] > 0:
            twp_label = QLabel(f"⚠️  Senza progresso: {status['turns_without_progress']} turni")
            twp_label.setStyleSheet("color: #a85; font-size: 9px;")
            self._add_state_widget(layout, twp_label)

        # Effetti attivi
        effects = status['active_effects']
        active = [k for k, v in effects.items() if v]
        if active:
            effects_label = QLabel(f"✨ {', '.join(active)}")
            effects_label.setStyleSheet("color: #8c8; font-size: 9px;")
            self._add_state_widget(layout, effects_label)

        # Blocco azioni
        if not status['can_attempt']:
            block_label = QLabel(f"🚫 {status['block_reason']}")
            block_label.setStyleSheet("color: #c44; font-weight: bold; font-size: 10px;")
            block_label.setWordWrap(True)
            self._add_state_widget(layout, block_label)

        # Game Over / Vittoria
        if status['game_over']:
            go_label = QLabel("💀 GAME OVER")
            go_label.setStyleSheet("color: #c44; font-weight: bold; font-size: 13px; margin-top: 6px;")
            self._add_state_widget(layout, go_label)
        elif status['victory']:
            vic_label = QLabel("🏆 VITTORIA")
            vic_label.setStyleSheet("color: #ffd700; font-weight: bold; font-size: 13px; margin-top: 6px;")
            self._add_state_widget(layout, vic_label)

    # -- post-turno ----------------------------------------------------------

    def _on_result(self, payload) -> None:
        """Dopo ogni turno, processa il mission tracker."""
        # Il payload della GUI base e una tupla (kind, data):
        # ("turn", TurnResult) | ("render", RenderRecord) | ("error", exc)
        kind, data = payload

        # Chiama il metodo originale per presentare il turno
        super()._on_result(payload)

        if kind != "turn":
            return

        result = data
        if not isinstance(result, TurnResult):
            return

        # La progressione di campagna e gia stata applicata dal TurnService.
        changes = dict(result.campaign_changes or {})

        # Mostra cambiamenti significativi nella storia (in evidenza)
        messages = []

        if changes.get("wrong_skill"):
            messages.append(f"⚠️  {changes['message']}")

        if changes.get("itaca_phase_advanced"):
            messages.append(f"🏹 FASE COMPLETATA: {changes['itaca_phase_completed']}")
            messages.append(
                f"   Prossima fase: {changes['itaca_phase_next']} "
                f"(richiede {changes['itaca_next_skill'].upper()})"
            )

        if changes.get("mission_completed"):
            messages.append(f"🎯 MISSIONE COMPLETATA: {changes['mission_name']}")
            messages.append(f"   +1 Kleos. Totale: {self.tracker.get_kleos()}")
            if changes.get("effect"):
                messages.append(f"   Effetto: {changes['effect']}")
            if changes.get("special"):
                messages.append(f"   ⚠️ {changes['special']}")

        if changes.get("location_changed"):
            messages.append(f"🌊 NUOVA LOCATION: {changes['new_location_name']}")
            new_location = changes["new_location"]
            messages.append(f"   {self.tracker.missions[new_location].description}")

        if changes.get("retry"):
            messages.append(f"🔄 {changes['retry']}")

        if changes.get("penalty"):
            messages.append(f"⚠️  PENALITÀ: {changes['penalty']}")

        if changes.get("game_over"):
            reason = changes.get("reason", "La partita è terminata.")
            messages.append(f"💀 GAME OVER: {reason}")

        if changes.get("victory"):
            kleos = changes.get("final_kleos", 0)
            messages.append(f"🏆 VITTORIA! Kleos finale: {kleos}")
            messages.append("   Ulisse è tornata a Itaca.")
            if changes.get("epilogue"):
                messages.append(f"\n📖 EPILOGO:\n{changes['epilogue']}")

        for msg in messages:
            self._append_system_message(msg)

        # Aggiorna il pannello stato
        self._refresh_state_panel()

    def _append_system_message(self, text: str) -> None:
        """Aggiunge un messaggio di sistema alla storia."""
        self._append_system(text)
