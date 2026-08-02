from pathlib import Path

from epos.contract import FinalScene
from epos.resort_production_turn_service import validate_concrete_sexy_outfit
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.validators import ValidationReport

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _state_with_luna_present():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "sexy-outfit-policy")
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4
    state.location_id = "loc_suite"
    state.player.location_id = "loc_suite"
    for npc_id, npc in state.npcs.items():
        npc.present = npc_id == "luna"
    state.npcs["luna"].location_id = "loc_suite"
    return state


def _scene(*, narration: str, mutations=None):
    return FinalScene.from_dict(
        {
            "narration": narration,
            "dialogue": [],
            "npc_actions": [{"npc_id": "luna", "action": narration}],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": mutations or [],
            "memory_events": [],
            "visual": None,
        }
    )


def test_generic_sexy_outfit_refusal_needs_no_mutation():
    state = _state_with_luna_present()
    report = validate_concrete_sexy_outfit(
        ValidationReport(),
        state,
        "Luna, indossa qualcosa di sexy",
        _scene(narration="Luna rifiuta con gentilezza e preferisce di no."),
    )
    assert report.errors == []


def test_generic_sexy_outfit_acceptance_requires_outfit_wear():
    state = _state_with_luna_present()
    report = validate_concrete_sexy_outfit(
        ValidationReport(),
        state,
        "Luna, indossa qualcosa di sexy",
        _scene(narration="Luna accetta e va a cambiarsi."),
    )
    assert [error.code for error in report.errors] == [
        "resort_outfit_wear_mutation_required"
    ]


def test_generic_sexy_outfit_rejects_vague_item():
    state = _state_with_luna_present()
    report = validate_concrete_sexy_outfit(
        ValidationReport(),
        state,
        "Luna, indossa qualcosa di sexy",
        _scene(
            narration="Luna accetta e si cambia.",
            mutations=[
                {
                    "type": "outfit_wear",
                    "target": "luna",
                    "payload": {"item": "sexy outfit"},
                    "reason": "Cambio richiesto.",
                }
            ],
        ),
    )
    assert [error.code for error in report.errors] == [
        "resort_concrete_outfit_items_required"
    ]


def test_generic_sexy_outfit_accepts_concrete_items():
    state = _state_with_luna_present()
    report = validate_concrete_sexy_outfit(
        ValidationReport(),
        state,
        "Luna, indossa qualcosa di sexy",
        _scene(
            narration="Luna accetta e sceglie un completo preciso.",
            mutations=[
                {
                    "type": "outfit_wear",
                    "target": "luna",
                    "payload": {"item": "black lace lingerie"},
                    "reason": "Scelta coerente con la richiesta.",
                },
                {
                    "type": "outfit_wear",
                    "target": "luna",
                    "payload": {"item": "sheer black stockings"},
                    "reason": "Scelta coerente con la richiesta.",
                },
            ],
        ),
    )
    assert report.errors == []
