"""Fase 4: snapshot compatto con missioni rilevanti dal world-pack."""

from pathlib import Path

from epos.contract import CheckProposal
from epos.prompt import build_snapshot, phase1_messages, phase2_messages
from epos.rules import Outcome, Roll
from epos.worldpack import load_pack

ODYSSEY_PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"
DEMO_PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


def test_snapshot_includes_current_and_upcoming_worldpack_missions():
    pack = load_pack(ODYSSEY_PACK)
    state = pack.new_world("mission-snapshot")

    missions = build_snapshot(state, pack, "Osservo la caverna.")["missions"]

    assert [m["id"] for m in missions["current"]] == ["mission_ciclopi"]
    assert missions["current"][0]["objectives"][0]["target"] == "polifemo"
    assert missions["current"][0]["success_conditions"][1]["text"] == "Sblocca Isola di Eolo."
    assert [m["id"] for m in missions["upcoming"]] == ["mission_eolo"]
    assert missions["upcoming"][0]["prerequisites"] == ["mission_ciclopi"]


def test_snapshot_missions_section_is_stable_for_pack_without_missions():
    pack = load_pack(DEMO_PACK)
    state = pack.new_world("no-missions-snapshot")

    snapshot = build_snapshot(state, pack, "Mi guardo intorno.")

    assert snapshot["missions"] == {"current": [], "upcoming": []}


def test_phase1_prompt_contains_mission_context_but_not_full_worldpack_dump():
    pack = load_pack(ODYSSEY_PACK)
    state = pack.new_world("mission-prompt")

    content = phase1_messages(state, pack, "Mi guardo intorno.")[-1]["content"]

    assert '"missions"' in content
    assert '"mission_ciclopi"' in content
    assert '"mission_eolo"' in content
    assert '"mission_itaca"' not in content


def test_phase_prompts_are_explicitly_separated():
    pack = load_pack(ODYSSEY_PACK)
    state = pack.new_world("phase-separated-prompt")
    proposal = CheckProposal(
        action_kind="deception",
        skill="dolos",
        difficulty=3,
        target_ids=["polifemo"],
        stakes={
            "full_success": "Sblocca Isola di Eolo.",
            "partial_success": "Sblocca Isola di Eolo.",
            "failure": "Polifemo capisce.",
            "critical_failure": "Polifemo divora Ulisse.",
        },
    )
    roll = Roll(pool_size=5, difficulty=3, dice=(), outcome=Outcome.FULL_SUCCESS)

    phase1 = phase1_messages(state, pack, "Mi guardo intorno.")[-1]["content"]
    phase2 = phase2_messages(
        state, pack, "Mi chiamo Nessuno.", proposal.to_dict(), roll.to_dict(), "Sblocca Isola di Eolo."
    )[-1]["content"]

    assert phase1.startswith("FASE_GM: proposal")
    assert "check_proposal" in phase1
    assert "ESITO AUTOREVOLE" not in phase1
    assert phase2.startswith("FASE_GM: final_scene")
    assert "ESITO AUTOREVOLE" in phase2
    assert "Se la situazione richiede una prova" not in phase2
