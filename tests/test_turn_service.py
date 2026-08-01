"""Ciclo canonico del turno: end-to-end con GM controllati."""

import random
from pathlib import Path

import pytest

from epos.contract import FinalScene, GmPhaseResponse
from epos.gm import DemoGameMaster, GameMasterError
from epos.renderers import RenderRecord
from epos.state_store import StateStore
from epos.turn_service import PlayerDecision, TurnService
from epos.worldpack import load_pack

PACK_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


@pytest.fixture
def service(tmp_path):
    pack = load_pack(PACK_DIR)
    return TurnService(
        gm=DemoGameMaster(),
        pack=pack,
        store=StateStore(tmp_path / "saves"),
        rng=random.Random(11),
    )


class TestNoCheckTurn:
    def test_full_cycle(self, service):
        state = service.new_session()
        result = service.play(state, "Mi siedo vicino al camino e ordino da bere.")

        assert result.mode == "no_check"
        assert result.narration
        assert state.turn == 1
        assert result.visual_contract is not None
        assert result.render_record.status == "pending"
        assert result.render_record.retryable is True

        # artefatti persistiti
        store = service.store
        proposal_snapshot = store.load_turn_artifact(state.session_id, 0, "gm_snapshot_proposal")
        assert proposal_snapshot["phase"] == "proposal"
        assert proposal_snapshot["snapshot"]["player_input"] == "Mi siedo vicino al camino e ordino da bere."
        assert store.load_turn_artifact(state.session_id, 0, "gm_phase1") is not None
        assert store.load_turn_artifact(state.session_id, 0, "scene") is not None
        assert store.load_turn_artifact(state.session_id, 0, "visual_contract") is not None
        assert store.load_checkpoint(state.session_id) is None

    def test_memory_of_turn_recorded(self, service):
        state = service.new_session()
        service.play(state, "Offro da bere a Maera.")
        assert len(state.npcs["maera"].memories) == 1

    def test_state_roundtrip_after_turn(self, service):
        state = service.new_session()
        service.play(state, "Osservo la sala in silenzio.")
        loaded = service.load_session(state.session_id)
        assert loaded.turn == 1
        assert loaded.last_scene == state.last_scene


class TestCheckTurn:
    def test_check_cycle_with_roll(self, service):
        state = service.new_session()
        result = service.play(state, "Tento di aprire la dispensa con uno stratagemma.")

        assert result.mode == "check"
        assert result.proposal is not None
        assert result.roll is not None
        assert result.roll.outcome is not None
        assert state.turn == 1
        # il tiro è persistito e il checkpoint cancellato dopo il commit
        assert service.store.load_turn_artifact(state.session_id, 0, "roll") is not None
        final_snapshot = service.store.load_turn_artifact(state.session_id, 0, "gm_snapshot_final_scene")
        assert final_snapshot["phase"] == "final_scene"
        assert final_snapshot["snapshot"]["turn"] == 0
        assert service.store.load_checkpoint(state.session_id) is None

    def test_check_cycle_with_safe_choice(self, tmp_path):
        pack = load_pack(PACK_DIR)
        service = TurnService(
            gm=DemoGameMaster(),
            pack=pack,
            store=StateStore(tmp_path / "saves"),
            rng=random.Random(11),
            decision_provider=lambda p, rating, diff, state: PlayerDecision(choice="safe"),
        )
        state = service.new_session()
        result = service.play(state, "Tento di aprire la dispensa.")
        assert result.roll.dice == ()  # esito sicuro: nessun tiro

    def test_resume_after_crash_reuses_same_roll(self, tmp_path):
        """Crash dopo il tiro: la ripresa non ritira i dadi."""

        class CrashOnceGM(DemoGameMaster):
            def __init__(self):
                self.crashed = False

            def narrate(self, state, pack, player_text, proposal, roll, stake, extras=None):
                if not self.crashed:
                    self.crashed = True
                    raise GameMasterError("simulated crash")
                return super().narrate(state, pack, player_text, proposal, roll, stake, extras=extras)

        pack = load_pack(PACK_DIR)
        gm = CrashOnceGM()
        service = TurnService(
            gm=gm,
            pack=pack,
            store=StateStore(tmp_path / "saves"),
            rng=random.Random(5),
        )
        state = service.new_session()
        with pytest.raises(GameMasterError, match="simulated crash"):
            service.play(state, "Tento di forzare la dispensa.")

        # lo stato NON è avanzato, ma il checkpoint col tiro esiste
        assert state.turn == 0
        checkpoint = service.store.load_checkpoint(state.session_id)
        assert checkpoint is not None
        original_roll = checkpoint["roll"]

        result = service.resume_pending(state, "Tento di forzare la dispensa.")
        assert result is not None
        assert result.resumed is True
        assert result.roll.to_dict() == original_roll  # STESSO tiro
        assert state.turn == 1
        assert service.store.load_checkpoint(state.session_id) is None


class TestStrictness:
    def test_invalid_scene_blocks_turn_state_untouched(self, tmp_path):
        """Una scena con mutazioni invalide ferma il turno: stato invariato."""

        class BadSceneGM:
            def propose(self, state, pack, player_text):
                return GmPhaseResponse.from_dict(
                    {
                        "mode": "no_check",
                        "scene": {
                            "narration": "Maera ti consegna un oggetto che non esiste.",
                            "mutations": [
                                {
                                    "type": "outfit_remove",
                                    "target": "player",
                                    "payload": {"item": "armatura mai posseduta"},
                                }
                            ],
                            "visual": {
                                "summary": "m",
                                "focus_character": "maera",
                                "visible_characters": ["maera"],
                                "shared_action": False,
                                "visual_en": "an innkeeper",
                                "tags_en": [],
                            },
                        },
                    }
                )

            def narrate(self, *args, **kwargs):  # pragma: no cover
                raise AssertionError("non deve narrare")

        pack = load_pack(PACK_DIR)
        service = TurnService(gm=BadSceneGM(), pack=pack, store=StateStore(tmp_path / "saves"))
        state = service.new_session()
        snapshot = state.to_dict()

        with pytest.raises(GameMasterError, match="Scena non valida"):
            service.play(state, "Prendo l'armatura.")

        assert state.to_dict() == snapshot  # nessuna mutazione applicata

    def test_invalid_proposal_triggers_semantic_revision(self, tmp_path):
        """Proposta invalida → UNA revisione semantica, tracciata, poi il turno
        prosegue come no_check."""

        class BadProposalGM(DemoGameMaster):
            def propose(self, state, pack, player_text):
                return GmPhaseResponse.from_dict(
                    {
                        "mode": "check_proposal",
                        "check": {
                            "action_kind": "social",
                            "skill": "social",
                            "difficulty": 3,
                            "target_ids": ["personaggio_fantasma"],
                            "stakes": {
                                "full_success": "a",
                                "partial_success": "b",
                                "failure": "c",
                                "critical_failure": "d",
                            },
                        },
                    }
                )

        pack = load_pack(PACK_DIR)
        service = TurnService(
            gm=BadProposalGM(), pack=pack, store=StateStore(tmp_path / "saves")
        )
        state = service.new_session()

        result = service.play(state, "Parlo col fantasma.")
        assert result.mode == "no_check"  # revisione: niente prova
        assert state.turn == 1
        assert state.flags["metrics"]["semantic_revisions"] == 1
        diagnostics = service.store.load_turn_artifact(state.session_id, 0, "diagnostics")
        assert diagnostics["kind"] == "invalid_check_proposal"
        revision_snapshot = service.store.load_turn_artifact(
            state.session_id, 0, "gm_snapshot_semantic_revision"
        )
        assert revision_snapshot["phase"] == "semantic_revision"
        assert revision_snapshot["problems"]
        assert service.store.load_turn_artifact(state.session_id, 0, "gm_revision")

    def test_failed_revision_blocks_turn_strictly(self, tmp_path):
        """Se anche la revisione fallisce, il turno si ferma: stato invariato."""

        class StubbornGM(DemoGameMaster):
            def propose(self, state, pack, player_text):
                return GmPhaseResponse.from_dict(
                    {
                        "mode": "check_proposal",
                        "check": {
                            "action_kind": "social",
                            "skill": "social",
                            "difficulty": 3,
                            "target_ids": ["personaggio_fantasma"],
                            "stakes": {
                                "full_success": "a",
                                "partial_success": "b",
                                "failure": "c",
                                "critical_failure": "d",
                            },
                        },
                    }
                )

            def revise(self, state, pack, player_text, problems):
                # il GM testardo ripropone una prova invece della scena
                return self.propose(state, pack, player_text)

        pack = load_pack(PACK_DIR)
        service = TurnService(gm=StubbornGM(), pack=pack, store=StateStore(tmp_path / "saves"))
        state = service.new_session()

        with pytest.raises(GameMasterError, match="revisione semantica"):
            service.play(state, "Parlo col fantasma.")
        assert state.turn == 0


class TestRerender:
    def test_rerender_does_not_call_gm(self, tmp_path):
        pack = load_pack(PACK_DIR)
        service = TurnService(
            gm=DemoGameMaster(), pack=pack, store=StateStore(tmp_path / "saves")
        )
        state = service.new_session()
        service.play(state, "Mi presento a Maera.")
        turn_before = state.turn

        record = service.rerender(state)
        assert record.status == "pending"
        assert state.turn == turn_before  # nessun turno ripetuto
        updated = service.store.load_turn_artifact(state.session_id, 0, "render_record")
        assert updated is not None
        assert updated["retryable"] is True

    def test_failed_render_record_is_retryable_and_does_not_cancel_turn(self, tmp_path):
        class FailingRenderer:
            def render(self, prompt_package, out_dir):
                return RenderRecord(
                    status="failed",
                    error="renderer offline",
                    backend="test",
                    retryable=True,
                    diagnostics={"cause": "offline"},
                )

        pack = load_pack(PACK_DIR)
        service = TurnService(
            gm=DemoGameMaster(),
            pack=pack,
            store=StateStore(tmp_path / "saves"),
            renderer=FailingRenderer(),
        )
        state = service.new_session()
        result = service.play(state, "Mi presento a Maera.")
        assert state.turn == 1
        assert result.render_record.status == "failed"
        assert result.render_record.retryable is True
        record = service.store.load_turn_artifact(state.session_id, 0, "render_record")
        assert record["retryable"] is True
        assert service.store.load_turn_artifact(state.session_id, 0, "visual_contract") is not None

    def test_rerender_without_contract_fails(self, tmp_path):
        pack = load_pack(PACK_DIR)
        service = TurnService(
            gm=DemoGameMaster(), pack=pack, store=StateStore(tmp_path / "saves")
        )
        state = service.new_session()
        with pytest.raises(GameMasterError, match="nessun turno"):
            service.rerender(state)


class TestDemoPlaythrough:
    """Tre turni liberi consecutivi: il ciclo regge la partita reale."""

    def test_three_free_turns(self, service):
        state = service.new_session()
        service.play(state, "Entro e mi tolgo il mantello bagnato.")
        service.play(state, "Chiedo a Maera perché non passano carovane.")
        result = service.play(state, "Cerco di leggere il registro sul banco mentre è distratta.")
        assert state.turn == 3
        assert result.mode in ("no_check", "check")
