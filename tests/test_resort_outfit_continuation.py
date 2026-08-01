from pathlib import Path

from epos.commit import apply_scene
from epos.models import outfit_state
from epos.resort_final_turn_service import _agreed_hosiery_request, _outfit_scene
from epos.resort_runtime import load_resort_pack, new_resort_world

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _complete_intro(state) -> None:
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4
    state.flags["resort_intro_presented"] = ["victoria", "luna", "maria", "stella"]


def _put_luna_in_suite(state) -> None:
    state.location_id = "loc_suite"
    state.player.location_id = "loc_suite"
    for npc_id, npc in state.npcs.items():
        npc.present = npc_id == "luna"
    state.npcs["luna"].location_id = "loc_suite"


def test_agreed_hosiery_continuation_removes_footwear_and_adds_prompt_tags():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "outfit-continuation")
    _complete_intro(state)
    _put_luna_in_suite(state)
    state.last_scene = "Luna accetta di indossare pantyhose nere senza scarpe."

    request = _agreed_hosiery_request(state, "fallo ora per favore")
    assert request == ("luna", "black pantyhose")

    scene = _outfit_scene(pack.world, state, *request)
    mutation_pairs = {(m.type, m.payload.get("item")) for m in scene.mutations}
    assert ("outfit_remove", "delicate sandals") in mutation_pairs
    assert ("outfit_wear", "black pantyhose") in mutation_pairs
    assert "black pantyhose" in scene.visual.tags_en
    assert "barefoot" in scene.visual.tags_en
    assert "no shoes" in scene.visual.tags_en
    assert "delicate sandals" not in scene.visual.visual_en

    apply_scene(state, scene, pack.world)
    luna_state = outfit_state(state.npcs["luna"].outfit)
    assert "black pantyhose" in luna_state["worn_items"]
    assert "delicate sandals" not in luna_state["worn_items"]
    assert "delicate sandals" in luna_state["removed_items"]
    assert luna_state["footwear"] == []
