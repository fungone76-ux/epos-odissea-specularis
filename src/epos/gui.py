"""App desktop epos (PySide6/Qt).

Layout a tre pannelli affiancati (Stato | Scena | Storia) in tema scuro,
nello stile della UI canonica del progetto originale: card di narrazione,
bolle di dialogo colorate per personaggio, viewer immagine con zoom/pan,
prompt visuale ispezionabile. Dialoghi dedicati per la decisione della prova
(riserva / innesco / dado temerario), il confronto a due mani, la narrazione
del giocatore e il tiro temerario.

Le chiamate al GM avvengono in un worker thread: la finestra non si blocca
mai. Le richieste UI (dialoghi) del worker vengono smistate al thread
principale tramite segnali Qt accodati.
"""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .application import GameApplicationService, GuiServiceProviders, find_turn_image
from .state_store import StateStore
from .turn_service import PlayerDecision, TurnResult, TurnService

DICE_FACES = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

OUTCOME_LABELS = {
    "full_success": "SUCCESSO PIENO",
    "partial_success": "SUCCESSO PARZIALE",
    "failure": "FALLIMENTO",
    "critical_failure": "FALLIMENTO CRITICO",
}

OUTCOME_STYLES = {
    "full_success": "outcomeFull",
    "partial_success": "outcomePartial",
    "failure": "outcomeFail",
    "critical_failure": "outcomeFail",
}

STYLESHEET = """
QMainWindow, QWidget { background: #16181d; color: #eceff4; font-size: 15px; }
QFrame#panel { background: #20232a; border: 1px solid #343944; border-radius: 10px; }
QLabel#panelTitle { font-size: 20px; font-weight: 700; padding: 4px; }
QFrame#narrationCard { background: #252932; border-left: 4px solid #8f9bb3; border-radius: 8px; }
QFrame#dialogueBubble { background: #2a303a; border: 1px solid #414958; border-radius: 12px; }
QFrame#playerBubble { background: #233024; border: 1px solid #3c5340; border-radius: 12px; }
QLabel#speakerName { font-weight: 800; font-size: 16px; color: #f1c27d; }
QLabel#speakerTarget { color: #9aa7bd; font-size: 13px; font-style: italic; }
QTextEdit { background: #111318; border: 1px solid #3a404d; border-radius: 8px; padding: 10px; }
QPushButton { background: #3b6ea8; border: 0; border-radius: 8px; padding: 10px 16px; font-weight: 700; }
QPushButton:hover { background: #4780bd; }
QPushButton:disabled { background: #343841; color: #777777; }
QPushButton#secondary { background: #343944; }
QPushButton#secondary:hover { background: #414958; }
QScrollArea { border: 0; }
QLabel#systemLine { color: #aeb6c5; font-style: italic; padding: 4px; }
QLabel#diceLine { font-size: 28px; padding: 2px 6px; }
QLabel#outcomeFull { color: #7fc97f; font-weight: 800; padding: 2px 6px; }
QLabel#outcomePartial { color: #e6c07a; font-weight: 800; padding: 2px 6px; }
QLabel#outcomeFail { color: #e07a7a; font-weight: 800; padding: 2px 6px; }
QLabel#sectionHeader { color: #f1c27d; font-weight: 700; padding-top: 6px; }
QDialog { background: #16181d; }
QLineEdit { background: #111318; border: 1px solid #3a404d; border-radius: 8px; padding: 8px; }
QCheckBox { padding: 3px; }
QSlider::groove:horizontal { height: 6px; background: #343944; border-radius: 3px; }
QSlider::handle:horizontal { width: 18px; margin: -7px 0; border-radius: 9px; background: #3b6ea8; }
QStatusBar { background: #101216; color: #8d97aa; }
"""


def dice_faces(dice) -> str:
    return " ".join(DICE_FACES.get(d, str(d)) for d in dice)



# ---------------------------------------------------------------------------
# Widget di base
# ---------------------------------------------------------------------------


class SubmitTextEdit(QTextEdit):
    """Campo di input: Invio invia, Maiusc+Invio va a capo."""

    submitRequested = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
            event.modifiers() & Qt.ShiftModifier
        ):
            event.accept()
            self.submitRequested.emit()
            return
        super().keyPressEvent(event)


class ImagePreviewLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.pixmap() is not None and not self.pixmap().isNull():
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class ZoomableGraphicsView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(Qt.black)

    def wheelEvent(self, event) -> None:
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)
        event.accept()


class ImageViewer(QDialog):
    """Viewer a schermo intero: zoom con rotellina, pan trascinando."""

    def __init__(self, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(image_path.name)
        self.resize(1100, 800)
        layout = QVBoxLayout(self)
        scene = QGraphicsScene(self)
        pixmap = QPixmap(str(image_path))
        self.item = QGraphicsPixmapItem(pixmap)
        scene.addItem(self.item)
        self.view = ZoomableGraphicsView(scene)
        layout.addWidget(self.view)
        hint = QLabel("Rotellina: zoom  •  Trascina: pan  •  Doppio clic: adatta alla finestra")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        QTimer.singleShot(0, self._fit)

    def _fit(self) -> None:
        self.view.fitInView(self.item, Qt.KeepAspectRatio)

    def mouseDoubleClickEvent(self, event) -> None:
        self._fit()
        super().mouseDoubleClickEvent(event)


class NarrationCard(QFrame):
    """Card della narrazione del GM: accento laterale, testo selezionabile."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setObjectName("narrationCard")
        box = QVBoxLayout(self)
        box.setContentsMargins(14, 12, 14, 12)
        label = QLabel(text.strip())
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(label)


class DialogueBubble(QFrame):
    """Bolla di un parlante (NPC o giocatore), con eventuale destinatario."""

    def __init__(self, speaker: str, text: str, to: str = "", is_player: bool = False) -> None:
        super().__init__()
        self.setObjectName("playerBubble" if is_player else "dialogueBubble")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(5)
        name = QLabel(speaker)
        name.setObjectName("speakerName")
        layout.addWidget(name)
        if to:
            target = QLabel(f"→ a {to}")
            target.setObjectName("speakerTarget")
            layout.addWidget(target)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(body)


def _system_line(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("systemLine")
    label.setWordWrap(True)
    return label


# ---------------------------------------------------------------------------
# Dialoghi di gioco
# ---------------------------------------------------------------------------


class DecisionDialog(QDialog):
    """Proposta di prova: poste, riserva, innesco, dado temerario.

    Uso: `dlg = DecisionDialog(...); dlg.exec(); decision = dlg.decision`.
    Chiusura senza scelta equivale a "roll" (default di PlayerDecision).
    """

    def __init__(self, parent: QWidget | None, proposal: Any, rating: int, difficulty: int, state: Any):
        super().__init__(parent)
        self.decision = PlayerDecision()
        self.setWindowTitle("Proposta di prova")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        heading = QLabel(f"{proposal.action_kind} (abilità: {proposal.skill})")
        heading.setStyleSheet("font-size: 17px; font-weight: 800;")
        layout.addWidget(heading)
        layout.addWidget(QLabel(f"Difficoltà {difficulty}  ·  Pool base {1 + rating}d6"))
        if proposal.reason:
            reason = QLabel(proposal.reason)
            reason.setWordWrap(True)
            reason.setObjectName("systemLine")
            layout.addWidget(reason)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #414958;")
        layout.addWidget(divider)

        for outcome, stake in proposal.stakes.items():
            stake_label = QLabel(f"{OUTCOME_LABELS.get(outcome, outcome)} → {stake}")
            stake_label.setWordWrap(True)
            stake_label.setObjectName(OUTCOME_STYLES.get(outcome, "systemLine"))
            layout.addWidget(stake_label)

        self._riserva = None
        if state.riserva > 0:
            self._riserva = QCheckBox(f"Usa un dado di riserva ({state.riserva} disponibili)")
            layout.addWidget(self._riserva)

        self._trigger = None
        if state.player.trigger:
            self._trigger = QCheckBox(f"Attiva l'innesco «{state.player.trigger}»")
            layout.addWidget(self._trigger)

        layout.addWidget(QLabel("Dado temerario — prezzo scommesso (vuoto = no):"))
        self._price = QLineEdit()
        self._price.setPlaceholderText("es. la fiducia di Marea, una risorsa, una complicazione…")
        layout.addWidget(self._price)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        roll_button = QPushButton("Tira i dadi")
        roll_button.setDefault(True)
        roll_button.clicked.connect(lambda: self._finish("roll"))
        safe_button = QPushButton("Esito sicuro")
        safe_button.setObjectName("secondary")
        safe_button.clicked.connect(lambda: self._finish("safe"))
        buttons.addWidget(roll_button)
        buttons.addWidget(safe_button)
        layout.addLayout(buttons)

    def _finish(self, choice: str) -> None:
        self.decision.choice = choice
        if self._riserva is not None and self._riserva.isChecked():
            self.decision.use_riserva = True
        if self._trigger is not None and self._trigger.isChecked():
            self.decision.use_trigger = True
        price = self._price.text().strip()
        if price:
            self.decision.dado_temerario_price = price
        self.accept()


class SplitDialog(QDialog):
    """Confronto: divisione segreta dei dadi tra le due mani.

    `dlg.exec()` poi `dlg.left` = dadi nella mano sinistra (chi vince).
    """

    def __init__(self, parent: QWidget | None, proposal: Any, player_pool: int, npc_pool: int):
        super().__init__(parent)
        self.left = player_pool
        self.setWindowTitle("Confronto")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        heading = QLabel(f"Contesa con {proposal.target_id} — {proposal.skill}")
        heading.setStyleSheet("font-size: 17px; font-weight: 800;")
        layout.addWidget(heading)
        for key, stake in proposal.stakes.items():
            stake_label = QLabel(f"{key} → {stake}")
            stake_label.setWordWrap(True)
            layout.addWidget(stake_label)

        info = QLabel(
            f"Tuoi dadi: {player_pool} — suoi dadi: {npc_pool}\n"
            "La mano sinistra decide CHI VINCE, la destra CHI NARRA."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._split_label = QLabel()
        self._split_label.setStyleSheet("font-weight: 700; padding: 4px;")
        layout.addWidget(self._split_label)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, player_pool)
        self._slider.setValue(player_pool)
        self._slider.valueChanged.connect(self._update_label)
        layout.addWidget(self._slider)
        self._update_label(self._slider.value())

        bet_button = QPushButton("Punta")
        bet_button.setDefault(True)
        bet_button.clicked.connect(self._finish)
        layout.addWidget(bet_button, alignment=Qt.AlignCenter)

    def _update_label(self, value: int) -> None:
        right = self._slider.maximum() - value
        self._split_label.setText(f"✊ Sinistra (vincere): {value}   ·   ✍ Destra (narrare): {right}")

    def _finish(self) -> None:
        self.left = int(self._slider.value())
        self.accept()


def ask_narration(parent: QWidget | None, context: str) -> str:
    """Narrazione del giocatore su successo pieno. Vuota se annullata."""

    dialog = QDialog(parent)
    dialog.setWindowTitle("La tua narrazione")
    dialog.setMinimumWidth(520)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 16)
    context_label = QLabel(context)
    context_label.setWordWrap(True)
    layout.addWidget(context_label)
    entry = QTextEdit()
    entry.setPlaceholderText("Racconta come riesci…")
    entry.setMinimumHeight(110)
    layout.addWidget(entry)
    confirm = QPushButton("Conferma")
    confirm.setDefault(True)
    confirm.clicked.connect(dialog.accept)
    layout.addWidget(confirm, alignment=Qt.AlignCenter)
    dialog.exec()
    return entry.toPlainText().strip()


def ask_temerario(parent: QWidget | None, outcome_label: str) -> str | None:
    """Tiro temerario post-fallimento: prezzo da pagare, oppure None."""

    dialog = QDialog(parent)
    dialog.setWindowTitle("Tiro temerario")
    dialog.setMinimumWidth(500)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 16)
    text = QLabel(
        f"{outcome_label}.\nDichiara un prezzo da pagare in caso di nuovo fallimento\n"
        "per ritirare l'intero pool (il nuovo tiro sovrascrive il precedente):"
    )
    text.setWordWrap(True)
    layout.addWidget(text)
    entry = QLineEdit()
    entry.setPlaceholderText("es. una complicazione, una risorsa, la sua fiducia…")
    layout.addWidget(entry)

    result: dict[str, str | None] = {"price": None}

    def reroll() -> None:
        result["price"] = entry.text().strip() or "una complicazione"
        dialog.accept()

    buttons = QHBoxLayout()
    reroll_button = QPushButton("Ritira (paga se fallisci)")
    reroll_button.setDefault(True)
    reroll_button.clicked.connect(reroll)
    accept_button = QPushButton("Accetta l'esito")
    accept_button.setObjectName("secondary")
    accept_button.clicked.connect(dialog.reject)
    buttons.addWidget(reroll_button)
    buttons.addWidget(accept_button)
    layout.addLayout(buttons)

    dialog.exec()
    return result["price"]


# ---------------------------------------------------------------------------
# Finestra principale
# ---------------------------------------------------------------------------


class EposGameWindow(QMainWindow):
    """Finestra principale del gioco (Stato | Scena | Storia)."""

    _call_in_main = Signal(object)   # dialoghi richiesti dal worker thread
    _result_ready = Signal(object)   # risultati del worker thread
    _status_signal = Signal(str)     # avanzamento del turno dal worker

    def __init__(self, service: TurnService, state, title: str = "epos"):
        self.app = QApplication.instance() or QApplication(sys.argv)
        super().__init__()
        self.service = service
        self.app_service = GameApplicationService(service)
        self.state = state
        self._busy = False
        self.current_image_path: Path | None = None
        self.image_viewer: ImageViewer | None = None

        self.setWindowTitle(f"{title} — {state.session_id[:8]}")
        self.resize(1400, 820)
        self.setMinimumSize(980, 700)

        self._call_in_main.connect(self._run_call, Qt.QueuedConnection)
        self._result_ready.connect(self._on_result)
        self._status_signal.connect(self._apply_progress_message)

        self._build_ui()
        self.setStyleSheet(STYLESHEET)
        self._restore_last_image()
        self._refresh_state_panel()
        if state.last_scene:
            self._append_narration(state.last_scene)
        self.statusBar().showMessage("Pronta. Scrivi liberamente la tua azione.")

    # -- layout -----------------------------------------------------------------

    def _panel(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        heading = QLabel(title)
        heading.setObjectName("panelTitle")
        layout.addWidget(heading)
        return frame, layout

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_state_panel())
        splitter.addWidget(self._build_visual_panel())
        splitter.addWidget(self._build_story_panel())
        splitter.setSizes([300, 520, 580])
        self.setCentralWidget(splitter)

    def _build_state_panel(self) -> QWidget:
        frame, layout = self._panel("Stato")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        self.state_text = QLabel()
        self.state_text.setWordWrap(True)
        self.state_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.state_text.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        holder_layout.addWidget(self.state_text)
        holder_layout.addStretch(1)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)

        session_buttons = QHBoxLayout()
        self.new_session_button = QPushButton("Nuova")
        self.new_session_button.setObjectName("secondary")
        self.new_session_button.clicked.connect(self.new_session)
        session_buttons.addWidget(self.new_session_button)

        self.save_button = QPushButton("Salva")
        self.save_button.setObjectName("secondary")
        self.save_button.clicked.connect(self.save_session)
        session_buttons.addWidget(self.save_button)

        self.load_button = QPushButton("Carica")
        self.load_button.setObjectName("secondary")
        self.load_button.clicked.connect(self.load_latest_session)
        session_buttons.addWidget(self.load_button)
        layout.addLayout(session_buttons)

        journal_button = QPushButton("Diario")
        journal_button.setObjectName("secondary")
        journal_button.clicked.connect(self.show_journal)
        layout.addWidget(journal_button)
        return frame

    def _build_visual_panel(self) -> QWidget:
        frame, layout = self._panel("Scena")
        self.image = ImagePreviewLabel("Immagine non generata\nRenderer pending")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(360, 360)
        # Ignored: il label non cambia MAI le richieste di layout quando
        # arriva una pixmap — la finestra resta stabile, l'immagine si
        # adatta allo spazio esistente (scaled in _show_image).
        self.image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image.setStyleSheet("background:#0d0f13; border:1px solid #3a404d; border-radius:8px;")
        self.image.clicked.connect(self._open_image_viewer)
        layout.addWidget(self.image, 3)

        buttons = QHBoxLayout()
        self.rerender_button = QPushButton("Rerender")
        self.rerender_button.setObjectName("secondary")
        self.rerender_button.clicked.connect(self.rerender)
        buttons.addWidget(self.rerender_button)
        self.prompt_toggle = QPushButton("Mostra prompt visuale")
        self.prompt_toggle.setObjectName("secondary")
        self.prompt_toggle.clicked.connect(self._toggle_prompt)
        buttons.addWidget(self.prompt_toggle)
        layout.addLayout(buttons)

        self.prompt_debug = QTextEdit()
        self.prompt_debug.setReadOnly(True)
        self.prompt_debug.setVisible(False)
        self.prompt_debug.setMinimumHeight(140)
        layout.addWidget(self.prompt_debug, 2)
        return frame

    def _build_story_panel(self) -> QWidget:
        frame, layout = self._panel("Storia")
        self.story_scroll = QScrollArea()
        self.story_scroll.setWidgetResizable(True)
        self.story_container = QWidget()
        self.story_layout = QVBoxLayout(self.story_container)
        self.story_layout.setAlignment(Qt.AlignTop)
        self.story_layout.setSpacing(10)
        self.story_scroll.setWidget(self.story_container)
        layout.addWidget(self.story_scroll, 1)

        self.phase_label = QLabel("Fase: pronta")
        self.phase_label.setObjectName("systemLine")
        layout.addWidget(self.phase_label)

        self.input = SubmitTextEdit()
        self.input.setPlaceholderText(
            "Scrivi liberamente ciò che fai o dici… "
            "(Invio per inviare, Maiusc+Invio per andare a capo)"
        )
        self.input.setMaximumHeight(95)
        self.input.submitRequested.connect(self.submit_action)
        layout.addWidget(self.input)

        self.send_button = QPushButton("Invia")
        self.send_button.clicked.connect(self.submit_action)
        layout.addWidget(self.send_button)
        return frame

    # -- storia: elementi ---------------------------------------------------------

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, lambda: self.story_scroll.verticalScrollBar().setValue(
            self.story_scroll.verticalScrollBar().maximum()
        ))

    def _append_narration(self, text: str) -> None:
        if not text.strip():
            return
        self.story_layout.addWidget(NarrationCard(text))
        self._scroll_to_bottom()

    def _append_dialogue(self, speaker: str, text: str, to: str = "") -> None:
        is_player = speaker in {self.state.player.name, "player", "Luna"}
        self.story_layout.addWidget(DialogueBubble(speaker, text, to, is_player))
        self._scroll_to_bottom()

    def _append_system(self, text: str) -> None:
        self.story_layout.addWidget(_system_line(text))
        self._scroll_to_bottom()

    def _append_dice(self, faces: str) -> None:
        label = QLabel(faces)
        label.setObjectName("diceLine")
        self.story_layout.addWidget(label)
        self._scroll_to_bottom()

    def _append_outcome(self, outcome: str) -> None:
        label = QLabel(OUTCOME_LABELS.get(outcome, outcome))
        label.setObjectName(OUTCOME_STYLES.get(outcome, "systemLine"))
        self.story_layout.addWidget(label)
        self._scroll_to_bottom()

    # -- pannelli -----------------------------------------------------------------

    def _location_name(self) -> str:
        return self.app_service.location_name(self.state)

    def _refresh_state_panel(self) -> None:
        self.state_text.setText(self.app_service.state_view(self.state).text)

    def show_journal(self) -> None:
        lines = self.app_service.journal_lines(self.state)

        dialog = QDialog(self)
        dialog.setWindowTitle("Diario")
        dialog.resize(420, 560)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(lines))
        layout.addWidget(text)
        dialog.exec()


    # -- sessioni ---------------------------------------------------------------

    def _replace_state(self, state) -> None:
        self.state = state
        self.setWindowTitle(f"{self.service.pack.title} - {state.session_id[:8]}")
        self.current_image_path = None
        self.image.clear()
        self.image.setText("Immagine non generata\nRenderer pending")
        self._restore_last_image()
        self._refresh_state_panel()
        self._update_prompt_debug()

    def save_session(self) -> None:
        if self._busy:
            return
        try:
            self.app_service.save_current(self.state)
            self._append_system(f"[sessione salvata: {self.state.session_id}]")
            self._set_busy(False, "Sessione salvata.")
        except Exception as exc:
            self._append_system(f"[salvataggio fallito: {exc}]")

    def new_session(self) -> None:
        if self._busy:
            return
        try:
            state = self.app_service.new_session()
            self._replace_state(state)
            self._append_system(f"[nuova sessione: {state.session_id}]")
            if state.last_scene:
                self._append_narration(state.last_scene)
            self._set_busy(False, "Nuova sessione pronta.")
        except Exception as exc:
            self._append_system(f"[nuova sessione fallita: {exc}]")

    def load_latest_session(self) -> None:
        if self._busy:
            return
        try:
            session_id = self.app_service.latest_session_id()
            if session_id is None:
                self._append_system("[nessuna sessione salvata]")
                return
            state = self.app_service.load_session(session_id)
            self._replace_state(state)
            self._append_system(f"[sessione caricata: {session_id}]")
            if state.last_scene:
                self._append_narration(state.last_scene)
            self._set_busy(False, "Sessione caricata.")
        except Exception as exc:
            self._append_system(f"[caricamento fallito: {exc}]")

    # -- immagine e prompt ----------------------------------------------------------

    def _show_image(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.image.setText(f"(immagine: {path})")
            return
        self.current_image_path = path
        self.image.setPixmap(pixmap.scaled(
            self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        self.image.setCursor(Qt.PointingHandCursor)
        self.image.setToolTip("Clicca per aprire l'immagine con zoom e pan")

    def _restore_last_image(self) -> None:
        path = self.app_service.last_turn_image(self.state)
        if path is not None:
            QTimer.singleShot(200, lambda p=path: self._show_image(p))

    def _open_image_viewer(self) -> None:
        if not self.current_image_path or not self.current_image_path.exists():
            return
        self.image_viewer = ImageViewer(self.current_image_path, self)
        self.image_viewer.show()
        self.image_viewer.raise_()
        self.image_viewer.activateWindow()

    def _toggle_prompt(self) -> None:
        visible = not self.prompt_debug.isVisible()
        self.prompt_debug.setVisible(visible)
        self.prompt_toggle.setText("Nascondi prompt visuale" if visible else "Mostra prompt visuale")

    def _update_prompt_debug(self) -> None:
        self.prompt_debug.setPlainText(self.app_service.visual_prompt_view(self.state).text)

    # -- smistamento thread ---------------------------------------------------------

    def _ask_in_main(self, fn):
        """Esegue fn (dialogo modale) nel thread GUI, chiamato dal worker."""

        done = threading.Event()
        box: dict[str, Any] = {"fn": fn, "done": done, "result": None}
        self._call_in_main.emit(box)
        done.wait()
        return box["result"]

    def _run_call(self, box: dict) -> None:
        try:
            box["result"] = box["fn"]()
        finally:
            box["done"].set()

    def _decision_provider(self, proposal, rating, difficulty, state) -> PlayerDecision:
        def ask() -> PlayerDecision:
            dialog = DecisionDialog(self, proposal, rating, difficulty, state)
            dialog.exec()
            return dialog.decision

        return self._ask_in_main(ask)

    def _split_provider(self, proposal, player_pool, npc_pool) -> int:
        def ask() -> int:
            dialog = SplitDialog(self, proposal, player_pool, npc_pool)
            dialog.exec()
            return dialog.left

        return self._ask_in_main(ask)

    def _narration_provider(self, context: str) -> str:
        return self._ask_in_main(lambda: ask_narration(self, context))

    def _temerario_provider(self, roll):
        label = OUTCOME_LABELS[roll.outcome.value]
        return self._ask_in_main(lambda: ask_temerario(self, label))

    def _gui_service(self) -> TurnService:
        return self.app_service.service_with_providers(
            GuiServiceProviders(
                decision_provider=self._decision_provider,
                narration_provider=self._narration_provider,
                split_provider=self._split_provider,
                temerario_provider=self._temerario_provider,
                progress=self._report_progress,
            )
        )

    def _report_progress(self, message: str) -> None:
        """Aggiorna la barra di stato dal worker (signal = thread-safe)."""
        self._status_signal.emit(message)

    def _apply_progress_message(self, message: str) -> None:
        self.statusBar().showMessage(message)
        if hasattr(self, "phase_label"):
            self.phase_label.setText(f"Fase: {message}")

    # -- azioni -----------------------------------------------------------------

    def submit_action(self) -> None:
        if self._busy:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self._append_dialogue(self.state.player.name or "Tu", text)
        self._set_busy(True, "Il Game Master sta pensando…")
        threading.Thread(target=self._play_worker, args=(text,), daemon=True).start()

    def rerender(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Rerendering in corso…")
        threading.Thread(target=self._rerender_worker, daemon=True).start()

    def _play_worker(self, text: str) -> None:
        try:
            result = self.app_service.play(
                self.state,
                text,
                GuiServiceProviders(
                    decision_provider=self._decision_provider,
                    narration_provider=self._narration_provider,
                    split_provider=self._split_provider,
                    temerario_provider=self._temerario_provider,
                    progress=self._report_progress,
                ),
            )
            self._result_ready.emit(("turn", result))
        except Exception as exc:  # stato non corrotto: lo segnala la UI
            self._result_ready.emit(("error", exc))

    def _rerender_worker(self) -> None:
        try:
            record = self.app_service.rerender(self.state)
            self._result_ready.emit(("render", record))
        except Exception as exc:
            self._result_ready.emit(("error", exc))

    def _on_result(self, payload) -> None:
        kind, data = payload
        if kind == "turn":
            self._present_turn(data)
        elif kind == "render":
            self._present_render(data)
        else:
            self._append_system(f"[turno non applicato: {data}]")
        self._refresh_state_panel()
        self._update_prompt_debug()
        self._set_busy(False, "Pronta.")
        self.input.setFocus()

    # -- presentazione turno ------------------------------------------------------

    def _present_turn(self, result: TurnResult) -> None:
        if result.confront_result is not None:
            r = result.confront_result
            self._append_system(
                f"Confronto {r.player_left}⚔{r.npc_left} / {r.player_right}✎{r.npc_right}"
                f" → vince: {r.winner} · narra: {r.narrator}"
            )
        if result.roll is not None:
            faces = dice_faces(result.roll.dice)
            if faces:
                self._append_dice(faces)
            else:
                self._append_system("(esito sicuro, nessun tiro)")
            self._append_outcome(result.roll.outcome.value)
        if result.player_narration:
            self._append_system(f"(la tua narrazione: {result.player_narration})")
        self._append_narration(result.narration)
        for line in result.dialogue:
            self._append_dialogue(line["speaker"], f"«{line['text']}»", line.get("to") or "")
        if result.render_record is not None:
            self._present_render(result.render_record)

    def _present_render(self, record) -> None:
        if record.status == "complete" and record.image_path:
            self._show_image(Path(record.image_path))
        elif record.status == "failed":
            self._append_system(f"[rendering fallito: {record.error} — Rerender per riprovare]")
        else:
            self.image.setText(f"Turno {self.state.turn}\nRenderer: pending")

    # -- stato busy ---------------------------------------------------------------

    def _set_busy(self, busy: bool, status: str) -> None:
        self._busy = busy
        self.send_button.setEnabled(not busy)
        self.rerender_button.setEnabled(not busy)
        self.new_session_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.load_button.setEnabled(not busy)
        self.input.setEnabled(not busy)
        self._apply_progress_message(status)

    # -- avvio --------------------------------------------------------------------

    def run(self) -> None:
        self.show()
        self.app.exec()
