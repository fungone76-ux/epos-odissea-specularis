"""Fase 2: progressione Odissea orchestrata dal TurnService."""

from pathlib import Path

from epos.contract import CheckProposal, FinalScene, GmPhaseResponse, Mutation, VisualMoment
from epos.odyssey_mission_tracker import OdysseyMissionTracker
from epos.rules import Roll
from epos.state_store import StateStore
from epos.turn_service import PlayerDecision, TurnService
from epos.worldpack import load_pack

PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


class MissionCompleteGM:
    def propose(self, state, pack, player_text):
        return GmPhaseResponse(
            mode="check_proposal",
            check=CheckProposal(
                action_kind="stealth",
                skill="dolos",
                difficulty=3,
                target_ids=["polifemo"],
                opposition="npc_resistance",
                reason="Ulisse inganna Polifemo con il nome Nessuno.",
                stakes={
                    "full_success": "Sblocca Isola di Eolo.",
                    "partial_success": "Sblocca Isola di Eolo.",
                    "failure": "Polifemo blocca l'uscita.",
                    "critical_failure": "Polifemo divora Ulisse.",
                },
            ),
        )

    def revise(self, state, pack, player_text, problems):
        raise AssertionError(problems)

    def narrate(self, state, pack, player_text, proposal, roll, stake, extras=None):
        return FinalScene(
            narration="Ulisse fugge dalla caverna mentre Polifemo urla il nome Nessuno.",
            mutations=[
                Mutation(
                    type="mission_complete",
                    target="loc_ciclopi",
                    payload={"completed_objectives": ["escape_polifemo"]},
                    reason="Polifemo e stata ingannata e la fuga e avvenuta.",
                )
            ],
            visual=VisualMoment(
                summary="Ulisse alla soglia della caverna",
                focus_character="player",
                visible_characters=["player"],
                shared_action=False,
                visual_en="a lone Greek hero at the threshold of a volcanic cave",
                tags_en=["volcanic cave"],
            ),
        )


def process_odyssey_turn(state, result):
    return OdysseyMissionTracker(state).process_turn(result)


def test_turn_service_applies_and_persists_odyssey_campaign_progress(tmp_path):
    pack = load_pack(PACK)
    service = TurnService(
        gm=MissionCompleteGM(),
        pack=pack,
        store=StateStore(tmp_path / "saves"),
        decision_provider=lambda *_: PlayerDecision(choice="safe"),
        post_turn_processor=process_odyssey_turn,
    )
    state = service.new_session()

    result = service.play(state, "Mi chiamo Nessuno e offro vino a Polifemo.")

    assert result.mode == "check"
    assert result.roll is not None
    assert isinstance(result.roll, Roll)
    assert result.campaign_changes["mission_completed"] is True
    assert result.campaign_changes["location_changed"] is True
    assert state.location_id == "loc_eolo"
    assert state.flags["odyssey_location_index"] == 1
    assert state.flags["odyssey_kleos"] == 1

    loaded = service.load_session(state.session_id)
    assert loaded.location_id == "loc_eolo"
    assert loaded.flags["odyssey_location_index"] == 1
    assert loaded.flags["odyssey_kleos"] == 1
    artifact = service.store.load_turn_artifact(state.session_id, 0, "campaign_changes")
    assert artifact["mission_name"] == "La Cieca e il Pasto"
