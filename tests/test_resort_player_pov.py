from pathlib import Path

from epos.contract import FinalScene
from epos.entity_ids import normalize_scene_entity_ids
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.resort_turn_service import (
    _canonicalize_resort_speakers,
    _speaker_id,
    enforce_resort_player_pov,
    validate_resort_scene_policy,
)
from epos.validators import validate_scene

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


def _victoria_short_name_scene():
    return FinalScene.from_dict(
        {
            "narration": "Victoria accetta i documenti per la registrazione.",
            "dialogue": [
                {
                    "speaker": "Victoria",
                    "to": "player",
                    "text": "Sì, sarebbero molto utili. Grazie.",
                }
            ],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Victoria accetta i documenti dal cliente fuori campo.",
                "focus_character": "victoria",
                "visible_characters": ["victoria"],
                "shared_action": False,
                "visual_en": "Victoria stands confidently in the lobby, addressing the unseen VIP guest.",
                "tags_en": ["full body", "confident stance", "lobby"],
                "moment_type": "speech",
                "speaker_character": "victoria",
                "actor_character": "victoria",
                "reactor_character": "",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": ["victoria"],
            },
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


def test_unique_short_first_name_resolves_to_victoria():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "victoria-alias")
    assert _speaker_id(state, "Victoria") == "victoria"
    assert _speaker_id(state, "Victoria Hale") == "victoria"
    assert _speaker_id(state, "victoria") == "victoria"


def test_short_victoria_speaker_is_canonicalized_before_generic_validation():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "victoria-canonical")
    scene = _canonicalize_resort_speakers(state, _victoria_short_name_scene())
    assert scene.dialogue[0].speaker == "Victoria Hale"
    assert validate_resort_scene_policy(state, pack.world, scene).ok


def test_central_entity_normalizer_preserves_short_victoria_display_name():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "victoria-central-normalizer")
    result = normalize_scene_entity_ids(
        state,
        _victoria_short_name_scene(),
        phase="semantic_validation",
        source_payload="provider_parsed_phase1",
    )

    # Dialogue speaker is display-facing text. Structural references such as
    # visual.speaker_character remain canonical ids and are normalized elsewhere.
    assert result.value.dialogue[0].speaker == "Victoria"
    assert not any(entry.field_path == "dialogue[0].speaker" for entry in result.entries)

    canonical = _canonicalize_resort_speakers(state, result.value)
    assert canonical.dialogue[0].speaker == "Victoria Hale"
    assert validate_scene(state, pack.world, canonical).ok
