"""GUI Qt (PySide6): widget, dialoghi e pannelli — tutto offscreen."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from epos.gm import DemoGameMaster
from epos.models import Thread
from epos.gui import (
    DecisionDialog,
    EposGameWindow,
    SplitDialog,
    dice_faces,
    find_turn_image,
)
from epos.state_store import StateStore
from epos.turn_service import TurnService
from epos.worldpack import load_pack

PACK_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def pack():
    return load_pack(PACK_DIR)


@pytest.fixture
def service(pack, tmp_path):
    return TurnService(gm=DemoGameMaster(), pack=pack, store=StateStore(tmp_path / "saves"))


@pytest.fixture
def state(pack):
    return pack.new_world("gui-session")


class TestHelpers:
    def test_dice_faces(self):
        assert dice_faces([1, 3, 6]) == "⚀ ⚂ ⚅"
        assert dice_faces([]) == ""

    def test_no_record_returns_none(self, tmp_path):
        store = StateStore(tmp_path / "saves")
        assert find_turn_image(store, "s1", 0) is None

    def test_complete_record_with_existing_image(self, tmp_path):
        store = StateStore(tmp_path / "saves")
        turn_dir = store.turn_dir("s1", 0)
        image = turn_dir / "image.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")  # placeholder
        store.save_turn_artifact(
            "s1", 0, "render_record",
            {"status": "complete", "image_path": str(image), "error": None, "backend": "test"},
        )
        assert find_turn_image(store, "s1", 0) == image

    def test_pending_record_returns_none(self, tmp_path):
        store = StateStore(tmp_path / "saves")
        store.save_turn_artifact(
            "s1", 0, "render_record",
            {"status": "pending", "image_path": None, "error": None, "backend": "pending"},
        )
        assert find_turn_image(store, "s1", 0) is None


class TestWindow:
    def test_creation_shows_opening_narration(self, app, service, state):
        window = EposGameWindow(service, state, title=service.pack.title)
        assert service.pack.title in window.windowTitle()
        assert window.story_layout.count() >= 1  # card di apertura

    def test_append_elements_grow_story(self, app, service, state):
        window = EposGameWindow(service, state)
        before = window.story_layout.count()
        window._append_narration("Una nuova scena.")
        window._append_dialogue("Maera", "«Benvenuta.»", to="Luna")
        window._append_dice("⚀ ⚄")
        window._append_outcome("full_success")
        window._append_system("[immagine pending]")
        assert window.story_layout.count() == before + 5

    def test_state_panel_reflects_state(self, app, service, state):
        state.riserva = 2
        state.player.trigger = "non lasciare che menta"
        state.player.outfit.wear("stivali infangati")
        window = EposGameWindow(service, state)
        window._refresh_state_panel()
        text = window.state_text.text()
        assert "Riserva: 2 dadi" in text
        assert "non lasciare che menta" in text
        assert "stivali infangati" in text

    def test_state_panel_shows_nuda_for_canonical_fully_nude(self, app, service, state):
        state.player.outfit.wear("bare thighs clearly visible")
        for item in list(state.player.outfit.worn):
            if item != "bare thighs clearly visible":
                state.player.outfit.remove_item(item)
        window = EposGameWindow(service, state)
        window._refresh_state_panel()
        text = window.state_text.text()
        assert "Nuda" in text
        assert "Indossa:" not in text
        assert "bare thighs clearly visible" not in text

    def test_prompt_toggle(self, app, service, state):
        window = EposGameWindow(service, state)
        assert window.prompt_debug.isHidden()
        window._toggle_prompt()
        assert not window.prompt_debug.isHidden()
        assert "Nascondi" in window.prompt_toggle.text()

    def test_state_panel_uses_application_view_for_threads(self, app, service, state):
        state.open_thread(
            Thread(
                id="t1",
                type="question",
                participants=["player"],
                summary="perche la porta e chiusa",
                opened_turn=state.turn,
            )
        )
        window = EposGameWindow(service, state)
        window._refresh_state_panel()
        text = window.state_text.text()
        assert "Thread attivi:" in text
        assert "perche la porta e chiusa" in text

    def test_progress_phase_label_updates_with_status_signal(self, app, service, state):
        window = EposGameWindow(service, state)
        window._apply_progress_message("Fase 2/3 - Narrazione")
        assert "Fase 2/3" in window.phase_label.text()
        assert "Narrazione" in window.statusBar().currentMessage()

    def test_session_buttons_exist_and_follow_busy_state(self, app, service, state):
        window = EposGameWindow(service, state)
        assert window.new_session_button.text() == "Nuova"
        assert window.save_button.text() == "Salva"
        assert window.load_button.text() == "Carica"
        window._set_busy(True, "Fase 1")
        assert not window.new_session_button.isEnabled()
        assert not window.save_button.isEnabled()
        assert not window.load_button.isEnabled()
        window._set_busy(False, "Pronta")
        assert window.new_session_button.isEnabled()
        assert window.save_button.isEnabled()
        assert window.load_button.isEnabled()

    def test_save_load_and_new_session_use_application_facade(self, app, service, state):
        window = EposGameWindow(service, state)
        original_id = state.session_id
        window.save_session()
        assert original_id in window.app_service.list_sessions()
        window.new_session()
        assert window.state.session_id != original_id
        window.load_latest_session()
        assert window.state.session_id in window.app_service.list_sessions()


class TestDecisionDialog:
    def _proposal(self):
        return SimpleNamespace(
            action_kind="intrufolarsi",
            skill="physical",
            reason="il corridoio è sorvegliato",
            stakes={"full_success": "entri inosservata", "failure": "ti scoprono"},
        )

    def test_roll_with_all_boosts(self, app, service, state):
        state.riserva = 2
        state.player.trigger = "fiuto le bugie"
        dialog = DecisionDialog(None, self._proposal(), rating=2, difficulty=4, state=state)
        dialog._riserva.setChecked(True)
        dialog._trigger.setChecked(True)
        dialog._price.setText("la sua fiducia")
        dialog._finish("roll")
        decision = dialog.decision
        assert decision.choice == "roll"
        assert decision.use_riserva is True
        assert decision.use_trigger is True
        assert decision.dado_temerario_price == "la sua fiducia"

    def test_safe_without_boosts(self, app, service, state):
        state.riserva = 0
        state.player.trigger = ""
        dialog = DecisionDialog(None, self._proposal(), rating=1, difficulty=3, state=state)
        assert dialog._riserva is None
        assert dialog._trigger is None
        dialog._finish("safe")
        assert dialog.decision.choice == "safe"
        assert dialog.decision.use_riserva is False
        assert dialog.decision.dado_temerario_price is None

    def test_default_decision_is_roll(self, app, service, state):
        dialog = DecisionDialog(None, self._proposal(), rating=1, difficulty=3, state=state)
        assert dialog.decision.choice == "roll"  # chiusura senza scelta = roll


class TestSplitDialog:
    def test_slider_sets_left_hand(self, app):
        proposal = SimpleNamespace(
            target_id="maera",
            skill="social",
            stakes={"win": "ottieni la chiave", "lose": "lei scopre il furto"},
        )
        dialog = SplitDialog(None, proposal, player_pool=5, npc_pool=3)
        dialog._slider.setValue(2)
        dialog._finish()
        assert dialog.left == 2

    def test_label_shows_both_hands(self, app):
        proposal = SimpleNamespace(target_id="maera", skill="social", stakes={})
        dialog = SplitDialog(None, proposal, player_pool=4, npc_pool=2)
        dialog._slider.setValue(3)
        text = dialog._split_label.text()
        assert "3" in text and "1" in text  # 3 sinistra, 1 destra
