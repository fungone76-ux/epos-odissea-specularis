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
from epos.visual import build_visual_contract

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



def _disable_intro(state):
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4


def _luna_present_on_private_beach(state):
    state.location_id = "loc_private_beach"
    for npc in state.npcs.values():
        npc.present = False
    state.npcs["luna"].present = True
    state.npcs["luna"].location_id = "loc_private_beach"


def _luna_sunscreen_scene():
    return FinalScene.from_dict(
        {
            "narration": "Luna inizia a spalmare la crema solare sulla pelle del cliente fuori campo.",
            "dialogue": [{"speaker": "Luna", "to": "player", "text": "Resta fermo, faccio piano."}],
            "npc_actions": [{"npc_id": "luna", "action": "applica la crema solare"}],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Momento intimo sulla spiaggia mentre Luna applica la crema solare.",
                "focus_character": "luna",
                "visible_characters": ["luna"],
                "shared_action": False,
                "visual_en": "Luna is applying sunscreen on the player, kneeling beside them, her hands gently spreading the cream over their skin.",
                "tags_en": ["intimate moment", "kneeling", "sunscreen application", "luxury beach"],
                "moment_type": "intimate",
                "speaker_character": "luna",
                "actor_character": "luna",
                "reactor_character": "",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": ["luna"],
            },
        }
    )


def test_valid_llm_sunscreen_visual_is_not_replaced_by_intro_fallback():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "luna-sunscreen-preserve")
    _disable_intro(state)
    _luna_present_on_private_beach(state)

    corrected = enforce_resort_player_pov(state, pack.world, _luna_sunscreen_scene())

    assert corrected.visual.focus_character == "luna"
    assert corrected.visual.visible_characters == ["luna"]
    assert corrected.visual.shared_action is False
    assert "sunscreen" in corrected.visual.visual_en.lower()
    assert "kneeling" in corrected.visual.visual_en.lower()
    assert "sunscreen application" in corrected.visual.tags_en
    assert "NPC introduction" not in corrected.visual.tags_en
    assert "addresses the unseen VIP guest" not in corrected.visual.visual_en


def test_sunscreen_visual_survives_until_visual_contract_prompt():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "luna-sunscreen-contract")
    _disable_intro(state)
    _luna_present_on_private_beach(state)

    corrected = enforce_resort_player_pov(state, pack.world, _luna_sunscreen_scene())
    before_outfit = state.npcs["luna"].outfit.to_dict()
    contract = build_visual_contract(state, pack.world, corrected.visual, state.turn)
    positive = contract.prompt_package["positive"]

    assert contract.focus_character == "luna"
    assert contract.visible_characters == ["luna"]
    assert state.npcs["luna"].outfit.to_dict() == before_outfit
    assert "fitted ivory VIP attendant mini dress" in positive
    assert "sunscreen application" in positive or "applying sunscreen" in positive
    assert "NPC introduction" not in positive
    assert "addresses the unseen VIP guest" not in positive


def test_already_present_luna_keeps_previous_action_visuals_like_turns_0012_0013():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "luna-previous-turns")
    _disable_intro(state)
    _luna_present_on_private_beach(state)

    for scene in (
        FinalScene.from_dict(
            {
                "narration": "Luna mostra i piedi con un gesto giocoso.",
                "dialogue": [],
                "npc_actions": [{"npc_id": "luna", "action": "mostra i piedi"}],
                "intentions": [],
                "initiatives": [],
                "disclosure_events": [],
                "mutations": [],
                "memory_events": [],
                "visual": {
                    "summary": "Luna si piega mostrando i piedi con un gesto giocoso.",
                    "focus_character": "luna",
                    "visible_characters": ["luna"],
                    "shared_action": False,
                    "visual_en": "Luna playfully shows her feet, bending slightly to present them.",
                    "tags_en": ["playful gesture", "beach setting", "intimate moment"],
                    "moment_type": "intimate",
                    "speaker_character": "",
                    "actor_character": "luna",
                    "reactor_character": "luna",
                    "intimate_shared_moment": False,
                    "multi_character_reason": "",
                    "multi_character_participants": ["luna"],
                },
            }
        ),
        FinalScene.from_dict(
            {
                "narration": "Luna sorride mostrando di nuovo i suoi piedi.",
                "dialogue": [{"speaker": "Luna", "to": "player", "text": "Grazie! Sono felice che ti piacciano."}],
                "npc_actions": [],
                "intentions": [],
                "initiatives": [],
                "disclosure_events": [],
                "mutations": [],
                "memory_events": [],
                "visual": {
                    "summary": "Luna is smiling while showing her feet slightly bent.",
                    "focus_character": "luna",
                    "visible_characters": ["luna"],
                    "shared_action": False,
                    "visual_en": "Luna is smiling brightly, slightly bending forward to show her feet, with the sun glistening on the water behind her.",
                    "tags_en": ["smiling", "showing feet", "sunlit", "private beach"],
                    "moment_type": "intimate",
                    "speaker_character": "luna",
                    "actor_character": "luna",
                    "reactor_character": "luna",
                    "intimate_shared_moment": False,
                    "multi_character_reason": "",
                    "multi_character_participants": ["luna"],
                },
            }
        ),
    ):
        corrected = enforce_resort_player_pov(state, pack.world, scene)
        assert corrected.visual.focus_character == "luna"
        assert corrected.visual.visible_characters == ["luna"]
        assert "NPC introduction" not in corrected.visual.tags_en
        assert "shows her feet" in corrected.visual.visual_en.lower() or "show her feet" in corrected.visual.visual_en.lower()


def test_resort_pov_preserves_valid_npc_action_when_rewriting_player_alias():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "stella-turn-0004-action")
    state.location_id = "loc_lobby"
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.npcs["stella"].location_id = "loc_lobby"
    for npc_id, npc in state.npcs.items():
        if npc_id != "stella":
            npc.location_id = "elsewhere"

    scene = FinalScene.from_dict(
        {
            "narration": "Stella sorride con sicurezza mentre osserva il cliente.",
            "dialogue": [],
            "npc_actions": [{"npc_id": "stella", "action": "reagisce con sicurezza"}],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Stella engages with the protagonist in the lobby.",
                "focus_character": "stella",
                "visible_characters": ["stella"],
                "shared_action": False,
                "visual_en": "Stella stands confidently as she engages with the protagonist in the lobby.",
                "tags_en": ["confident pose", "lobby"],
                "moment_type": "action",
                "speaker_character": "",
                "actor_character": "stella",
                "reactor_character": "stella",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": ["stella"],
            },
        }
    )

    corrected = enforce_resort_player_pov(state, pack.world, scene)

    assert corrected.visual.focus_character == "stella"
    assert corrected.visual.visible_characters == ["stella"]
    assert "stands confidently" in corrected.visual.visual_en
    assert "off-camera VIP guest" in corrected.visual.visual_en
    assert "protagonist" not in corrected.visual.visual_en.lower()
    assert "NPC introduction" not in corrected.visual.tags_en
    assert "reacts to the unseen VIP guest" not in corrected.visual.visual_en


def test_resort_sunscreen_prompt_uses_off_camera_player_reference():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "stella-sunscreen-off-camera")
    state.location_id = "loc_private_beach"
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.npcs["stella"].location_id = "loc_private_beach"
    for npc_id, npc in state.npcs.items():
        if npc_id != "stella":
            npc.location_id = "elsewhere"

    scene = FinalScene.from_dict(
        {
            "narration": "Stella spalma la crema solare sulla schiena del cliente fuori campo.",
            "dialogue": [],
            "npc_actions": [{"npc_id": "stella", "action": "applica la crema solare"}],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Stella applying sunscreen on the player's back.",
                "focus_character": "stella",
                "visible_characters": ["stella"],
                "shared_action": False,
                "visual_en": "Stella is leaning closer, applying sunscreen on the player's back with slow, deliberate movements.",
                "tags_en": ["sunscreen application", "private beach"],
                "moment_type": "intimate",
                "speaker_character": "",
                "actor_character": "stella",
                "reactor_character": "stella",
                "intimate_shared_moment": True,
                "multi_character_reason": "",
                "multi_character_participants": ["stella"],
            },
        }
    )

    corrected = enforce_resort_player_pov(state, pack.world, scene)
    contract = build_visual_contract(state, pack.world, corrected.visual, state.turn)
    positive = contract.prompt_package["positive"]

    assert contract.focus_character == "stella"
    assert contract.visible_characters == ["stella"]
    assert "sunscreen application" in positive or "applying sunscreen" in positive
    assert "off-camera VIP guest" in positive
    assert "player's back" not in positive
    assert "NPC introduction" not in positive
    assert "addresses the unseen VIP guest" not in positive
