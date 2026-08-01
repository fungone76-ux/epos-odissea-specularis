from pathlib import Path

from epos.contract import CheckProposal, ConfrontProposal, GmPhaseResponse
from epos.odyssey_runtime import (
    OdysseyRuleAwareGameMaster,
    effective_mission_difficulty,
    normalize_odyssey_phase_response,
    process_odyssey_turn,
)
from epos.rules import ConfrontResult
from epos.turn_service import TurnResult
from epos.worldpack import load_pack


PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


def _check(skill: str, difficulty: int = 6, target: str = "polifemo") -> CheckProposal:
    return CheckProposal(
        action_kind="social",
        skill=skill,
        difficulty=difficulty,
        target_ids=[target],
        opposition="npc_resistance",
        reason="prova missione",
        stakes={
            "critical_failure": "disastro",
            "failure": "fallimento",
            "partial_success": "progresso",
            "full_success": "successo",
        },
    )


def test_retry_changes_authoritative_difficulty_before_roll():
    pack = load_pack(PACK)
    state = pack.new_world("retry-pre-roll")
    state.flags["retry_difficulty_offset"] = 2

    response = GmPhaseResponse(mode="check_proposal", check=_check("dolos", difficulty=6))
    adjusted = normalize_odyssey_phase_response(state, pack, response)

    assert adjusted.check is not None
    assert adjusted.check.difficulty == 1  # Ciclopi base 3, retry -2


def test_non_mission_check_keeps_gm_difficulty():
    pack = load_pack(PACK)
    state = pack.new_world("unrelated-check")
    proposal = _check("eros", difficulty=5)

    assert effective_mission_difficulty(state, pack, proposal) == 5


def test_moly_and_poseidon_are_applied_before_resolution():
    pack = load_pack(PACK)
    state = pack.new_world("named-effects")

    state.location_id = "loc_circe"
    state.player.location_id = "loc_circe"
    state.flags["odyssey_location_index"] = 4
    state.flags["moly_possessed"] = True
    circe = _check("eros", difficulty=6, target="circe")
    assert effective_mission_difficulty(state, pack, circe) == 3

    state.location_id = "loc_scilla_cariddi"
    state.player.location_id = "loc_scilla_cariddi"
    state.flags["odyssey_location_index"] = 3
    state.flags["poseidon_curse_active"] = True
    strait = _check("pontos", difficulty=2, target="")
    assert effective_mission_difficulty(state, pack, strait) == 6


class _ConfrontGM:
    def propose(self, state, pack, player_text):
        return GmPhaseResponse(
            mode="confront_proposal",
            confront=ConfrontProposal(
                skill="dolos",
                target_id="polifemo",
                reason="Ingannare direttamente Polifemo.",
                stakes={
                    "win": "Sblocca Isola di Eolo.",
                    "lose": "Polifemo blocca la fuga.",
                    "stall": "La fuga resta incerta.",
                },
            ),
        )


def test_won_confront_can_complete_campaign_mission():
    pack = load_pack(PACK)
    state = pack.new_world("confront-progress")
    gm = OdysseyRuleAwareGameMaster(_ConfrontGM())
    gm.propose(state, pack, "Convinco Polifemo che il mio nome e Nessuno.")

    result = TurnResult(
        turn=0,
        mode="confront",
        narration="Polifemo viene ingannata e Ulisse fugge.",
        confront_result=ConfrontResult(
            player_pool=5,
            npc_pool=3,
            player_left=4,
            player_right=1,
            npc_left=2,
            npc_right=1,
            winner="player",
            narrator="shared",
        ),
        stake="Sblocca Isola di Eolo.",
        scene_mutations=[
            {
                "type": "mission_complete",
                "target": "loc_ciclopi",
                "payload": {"completed_objectives": ["escape_polifemo"]},
                "reason": "Polifemo e stata ingannata.",
            }
        ],
    )

    changes = process_odyssey_turn(state, pack, result, gm=gm)

    assert changes["mission_completed"] is True
    assert changes["location_changed"] is True
    assert state.location_id == "loc_eolo"
    assert state.flags["odyssey_kleos"] == 1
