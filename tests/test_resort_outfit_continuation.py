from pathlib import Path

from epos.commit import apply_scene
from epos.models import outfit_state
from epos.resort_final_turn_service import (
    _agreed_complete_undress_request,
    _agreed_hosiery_request,
    _complete_undress_scene,
    _outfit_scene,
)
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


def test_fresh_complete_undress_request_is_not_automatic_consent():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "undress-fresh-request")
    _complete_intro(state)
    _put_luna_in_suite(state)
    state.last_scene = "Luna ascolta la richiesta senza avere ancora risposto."

    assert _agreed_complete_undress_request(
        state, "Luna, spogliati completamente nuda"
    ) is None


def test_agreed_complete_undress_continuation_removes_every_worn_item():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "undress-continuation")
    _complete_intro(state)
    _put_luna_in_suite(state)
    state.last_scene = (
        "Luna accetta di spogliarsi completamente e restare completamente nuda."
    )

    target = _agreed_complete_undress_request(state, "fallo ora per favore")
    assert target == "luna"

    worn_before = list(state.npcs["luna"].outfit.worn)
    assert worn_before

    scene = _complete_undress_scene(pack.world, state, target)
    removed_by_scene = [
        mutation.payload.get("item")
        for mutation in scene.mutations
        if mutation.type == "outfit_remove"
    ]
    assert removed_by_scene == worn_before
    assert "fully nude" in scene.visual.tags_en
    assert "barefoot" in scene.visual.tags_en
    assert "no clothes" in scene.visual.tags_en
    assert "no shoes" in scene.visual.tags_en

    apply_scene(state, scene, pack.world)
    luna_state = outfit_state(state.npcs["luna"].outfit)
    assert luna_state["worn_items"] == []
    assert set(worn_before).issubset(set(luna_state["removed_items"]))
    assert luna_state["torso_slot"] == []
    assert luna_state["lower_body_slot"] == []
    assert luna_state["footwear"] == []
    assert luna_state["nudity_mode"] == "nude"
