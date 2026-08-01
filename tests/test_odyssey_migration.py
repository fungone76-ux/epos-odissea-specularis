"""Regressioni della migrazione Odissea come campagna canonica."""

from pathlib import Path

import pytest

from epos.contract import FinalScene, GmPhaseResponse, VisualMoment
from epos.gm import DemoGameMaster
from epos.state_store import StateStore
from epos.turn_service import TurnService
from epos.worldpack import load_pack

PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


def test_clarification_phase_is_parsed_without_scene_or_mutation():
    response = GmPhaseResponse.from_dict(
        {"mode": "clarification", "clarification": "Vuoi avvicinarti o restare nascosta?"}
    )
    assert response.mode == "clarification"
    assert response.clarification.startswith("Vuoi")
    assert response.scene is None
    assert response.check is None
    assert response.confront is None


@pytest.mark.parametrize("extra", ["scene", "check", "confront"])
def test_clarification_rejects_payload_that_would_commit(extra):
    payload = {"mode": "clarification", "clarification": "Che cosa fai?", extra: {}}
    with pytest.raises(Exception, match="clarification"):
        GmPhaseResponse.from_dict(payload)


def test_odyssey_initial_presence_is_limited_to_start_location():
    pack = load_pack(PACK)
    state = pack.new_world()
    assert state.location_id == "loc_ciclopi"
    assert state.present_npc_ids() == ["polifemo"]


class FailingSaveStore(StateStore):
    def __init__(self, root):
        super().__init__(root)
        self._saved_once = False

    def save_state(self, state):
        if not self._saved_once:
            self._saved_once = True
            return super().save_state(state)
        raise RuntimeError("simulated save failure")


class MutatingNoCheckGM(DemoGameMaster):
    def propose(self, state, pack, player_text):
        return GmPhaseResponse(
            mode="no_check",
            scene=FinalScene(
                narration="Ulisse si sposta sulla spiaggia senza chiudere il turno.",
                mutations=[
                    type("M", (), {
                        "type": "location_change",
                        "target": "player",
                        "payload": {"location_id": "loc_eolo"},
                        "reason": "test",
                    })()
                ],
                visual=VisualMoment(
                    summary="Ulisse sulla riva",
                    focus_character="player",
                    visible_characters=["player"],
                    shared_action=False,
                    visual_en="a mythic queen on a shore",
                ),
            ),
        )


def test_commit_failure_does_not_mutate_live_state(tmp_path):
    pack = load_pack(PACK)
    service = TurnService(
        gm=MutatingNoCheckGM(),
        pack=pack,
        store=FailingSaveStore(tmp_path / "saves"),
    )
    state = service.new_session()
    before = state.to_dict()

    with pytest.raises(RuntimeError, match="simulated save failure"):
        service.play(state, "Vado alla prossima isola.")

    assert state.to_dict() == before
