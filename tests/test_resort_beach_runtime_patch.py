from pathlib import Path

from epos.gm import DemoGameMaster
from epos.resort_playable_turn_service import ResortPlayableTurnService
from epos.resort_runtime import load_resort_pack, new_resort_world

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _complete_intro(state) -> None:
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4
    state.flags["resort_intro_presented"] = ["victoria", "luna", "maria", "stella"]


def _service_and_state(session_id: str):
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, session_id)
    _complete_intro(state)
    state.location_id = "loc_private_beach"
    state.player.location_id = "loc_private_beach"
    for npc in state.npcs.values():
        npc.present = False
    service = ResortPlayableTurnService(gm=DemoGameMaster(), pack=pack.world)
    service.store.save_state(state)
    return service, state


def test_summoned_luna_uses_outdoor_beach_visual_and_default_beach_outfit():
    service, state = _service_and_state("beach-summon-luna")

    result = service.play(state, "chiamo Luna")

    assert result.mode == "no_check"
    assert state.npcs["luna"].location_id == "loc_private_beach"
    assert state.npcs["luna"].present is True
    assert "interior" not in result.visual_contract.positive_prompt.lower()
    assert "private mediterranean beach" in result.visual_contract.positive_prompt.lower()
    assert "ivory bikini" in result.visual_contract.positive_prompt.lower()
    assert "barefoot" in result.visual_contract.positive_prompt.lower()


def test_beach_summon_preserves_manual_outfit_override():
    service, state = _service_and_state("beach-manual-outfit")
    luna = state.npcs["luna"]
    luna.outfit.revision = 2

    result = service.play(state, "chiamo Luna")

    assert "ivory bikini" not in result.visual_contract.positive_prompt.lower()
    assert "fitted ivory vip attendant mini dress" in result.visual_contract.positive_prompt.lower()


def test_relaxing_with_one_present_npc_is_deterministic_and_gets_npc_response():
    service, state = _service_and_state("beach-relax-luna")
    state.npcs["luna"].location_id = "loc_private_beach"
    state.npcs["luna"].present = True
    service.store.save_state(state)

    result = service.play(state, "Vorrei rilassarmi un po")

    assert result.mode == "no_check"
    assert any(line["speaker"] == "Luna" for line in result.dialogue)
    assert "quiet relaxation" in result.visual_contract.positive_prompt.lower()
    assert "interior" not in result.visual_contract.positive_prompt.lower()
