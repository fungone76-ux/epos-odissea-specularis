from pathlib import Path

from epos.contract import FinalScene
from epos.entity_ids import normalize_scene_entity_ids
from epos.models import Outfit, outfit_state
from epos.resort_runtime import load_resort_pack, new_resort_world

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _luna_only_state():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "placeholder-regression")
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.location_id = "loc_wild_beach"
    state.player.location_id = "loc_wild_beach"
    for npc_id, npc in state.npcs.items():
        npc.present = npc_id == "luna"
    state.npcs["luna"].location_id = "loc_wild_beach"
    return pack, state


def test_schema_npc_id_placeholder_resolves_to_only_present_speaker_before_validation():
    _pack, state = _luna_only_state()
    scene = FinalScene.from_dict(
        {
            "narration": "Luna risponde dalla spiaggia selvaggia.",
            "dialogue": [
                {
                    "speaker": "Luna",
                    "text": "Sono venuta qui per pensare, lontano dal trambusto.",
                    "to": "player",
                }
            ],
            "npc_actions": [],
            "intentions": [
                {
                    "npc_id": "luna",
                    "intention": "continue a private conversation",
                }
            ],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Luna stands on the wild beach.",
                "focus_character": "npc_id",
                "visible_characters": ["npc_id"],
                "shared_action": False,
                "moment_type": "speech",
                "speaker_character": "npc_id",
                "actor_character": "npc_id",
                "reactor_character": "player",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": [],
                "visual_en": "Luna on a wild beach in a sand colored micro bikini.",
                "tags_en": ["wild beach", "micro bikini"],
            },
        }
    )

    result = normalize_scene_entity_ids(
        state,
        scene,
        phase="proposal",
        attempt=1,
        source_payload="openai_attempt",
    )

    assert result.changed
    assert result.value.visual.focus_character == "luna"
    assert result.value.visual.visible_characters == ["luna"]
    assert result.value.visual.speaker_character == "luna"
    assert result.value.visual.actor_character == "luna"
    assert any(
        entry.alias_rule == "scene_placeholder_npc_id"
        for entry in result.entries
    )


def test_placeholder_is_not_guessed_when_multiple_npcs_are_present_without_participant():
    pack, state = _luna_only_state()
    state.npcs["maria"].present = True
    state.npcs["maria"].location_id = "loc_wild_beach"
    scene = FinalScene.from_dict(
        {
            "narration": "Una voce rompe il silenzio.",
            "dialogue": [],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Una figura sulla spiaggia.",
                "focus_character": "npc_id",
                "visible_characters": ["npc_id"],
                "shared_action": False,
                "moment_type": "reaction",
                "speaker_character": "",
                "actor_character": "",
                "reactor_character": "",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": [],
                "visual_en": "an adult woman on a wild beach",
                "tags_en": ["wild beach"],
            },
        }
    )

    result = normalize_scene_entity_ids(state, scene, phase="proposal")

    assert result.value.visual.focus_character == "npc_id"
    assert result.value.visual.visible_characters == ["npc_id"]


def test_resort_bikini_and_sarong_are_clothed_not_fully_nude():
    state = outfit_state(
        Outfit(
            worn=[
                "sand colored micro bikini",
                "sheer linen sarong",
                "woven bracelet",
                "barefoot",
            ]
        )
    )

    assert "sand colored micro bikini" in state["torso_slot"]
    assert "sand colored micro bikini" in state["lower_body_slot"]
    assert "sheer linen sarong" in state["lower_body_slot"]
    assert state["nudity_mode"] == "clothed"


def test_luxury_travel_suit_is_clothed_not_bottomless():
    state = outfit_state(
        Outfit(
            worn=[
                "luxury travel suit",
                "tailored shirt",
                "elegant shoes",
            ]
        )
    )

    assert "luxury travel suit" in state["torso_slot"]
    assert "luxury travel suit" in state["lower_body_slot"]
    assert "elegant shoes" in state["footwear"]
    assert state["nudity_mode"] == "clothed"
