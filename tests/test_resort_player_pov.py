from pathlib import Path

from epos.contract import FinalScene
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.resort_turn_service import (
    enforce_resort_player_pov,
    validate_resort_scene_policy,
)

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _scene(**visual_overrides):
    visual = {
        "summary": "Il protagonista scende le scale guardando Victoria.",
        "focus_character": "player",
        "visible_characters": ["player", "victoria"],
        "shared_action": False,
        "visual_en": (
            "The protagonist descends the stairs and glances towards Victoria, "
            "who stands in the lobby."
        ),
        "tags_en": ["descending stairs", "elegant lobby"],
        "moment_type": "action",
        "speaker_character": "",
        "actor_character": "player",
        "reactor_character": "victoria",
        "intimate_shared_moment": False,
        "multi_character_reason": "",
        "multi_character_participants": ["player", "victoria"],
    }
    visual.update(visual_overrides)
    return FinalScene.from_dict(
        {
            "narration": "Victoria osserva il protagonista nella lobby.",
            "dialogue": [],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": visual,
        }
    )


def test_resort_rejects_player_as_visual_subject():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "pov-reject")
    report = validate_resort_scene_policy(state, pack.world, _scene())
    codes = {error.code for error in report.errors}
    assert "resort_player_visual_forbidden" in codes
    assert "resort_player_visual_text_forbidden" in codes


def test_resort_requires_an_npc_response_reaction_or_initiative():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "npc-response")
    report = validate_resort_scene_policy(state, pack.world, _scene())
    assert any(error.code == "resort_npc_response_required" for error in report.errors)


def test_resort_pov_normalizer_replaces_player_with_reacting_npc():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "pov-normalize")
    corrected = enforce_resort_player_pov(state, pack.world, _scene())
    assert corrected.visual.focus_character == "victoria"
    assert corrected.visual.visible_characters == ["victoria"]
    assert corrected.visual.shared_action is False
    assert "player" not in corrected.visual.visible_characters
    assert "protagonist" not in corrected.visual.visual_en.lower()
    assert "victoria" in corrected.visual.visual_en.lower()


def test_valid_victoria_reply_passes_resort_policy():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "valid-victoria")
    scene = FinalScene.from_dict(
        {
            "narration": "Victoria solleva appena il mento e segue il gesto del miliardario.",
            "dialogue": [
                {
                    "speaker": "Victoria Hale",
                    "to": "player",
                    "text": "Buongiorno. Vedo che ha deciso di farsi notare.",
                }
            ],
            "npc_actions": [
                {"npc_id": "victoria", "action": "inclina il capo con sottile ironia"}
            ],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Victoria reagisce al saluto del miliardario fuori campo.",
                "focus_character": "victoria",
                "visible_characters": ["victoria"],
                "shared_action": False,
                "visual_en": "Victoria reacts to the unseen VIP guest in the elegant lobby.",
                "tags_en": ["NPC reaction", "unseen guest POV", "elegant lobby"],
                "moment_type": "speech",
                "speaker_character": "victoria",
                "actor_character": "victoria",
                "reactor_character": "victoria",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": ["victoria"],
            },
        }
    )
    report = validate_resort_scene_policy(state, pack.world, scene)
    assert report.ok
