from pathlib import Path

from epos.gm import DemoGameMaster
from epos.resort_production_turn_service import ResortProductionTurnService
from epos.resort_runtime import load_resort_pack, new_resort_world

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _complete_intro(state) -> None:
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4
    state.flags["resort_intro_presented"] = ["victoria", "luna", "maria", "stella"]


def test_generic_beach_request_moves_without_check_or_npc_scene():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "generic-beach-navigation")
    _complete_intro(state)
    state.location_id = "loc_lobby"
    state.player.location_id = "loc_lobby"
    for npc in state.npcs.values():
        npc.location_id = "loc_lobby"
        npc.present = True

    service = ResortProductionTurnService(gm=DemoGameMaster(), pack=pack.world)
    service.store.save_state(state)

    result = service.play(state, "vado in spiaggia")

    assert result.mode == "no_check"
    assert state.location_id == "loc_private_beach"
    assert state.player.location_id == "loc_private_beach"
    assert result.dialogue == []
    assert result.roll is None
    assert result.visual_contract is None
    assert all(not npc.present for npc in state.npcs.values())
    assert "Spiaggia privata" in result.narration


def test_specific_wild_beach_still_uses_canonical_navigation():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "wild-beach-navigation")
    _complete_intro(state)
    service = ResortProductionTurnService(gm=DemoGameMaster(), pack=pack.world)
    service.store.save_state(state)

    result = service.play(state, "vado alla spiaggia selvaggia")

    assert result.mode == "no_check"
    assert state.location_id == "loc_wild_beach"
    assert state.player.location_id == "loc_wild_beach"
