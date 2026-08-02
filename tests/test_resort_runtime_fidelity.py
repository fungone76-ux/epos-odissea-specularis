from pathlib import Path

import pytest

from epos.contract import FinalScene, InitiativeEvent
from epos.initiative import initiative_context, validate_initiative
from epos.resort_fidelity import (
    resort_fidelity_diagnostics,
    validate_dialogue_substance,
    validate_initiative_obligation,
    validate_resort_visual_requirements,
    validate_scene_progression,
)
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.resort_turn_service import enforce_resort_player_pov, validate_resort_scene_policy
from epos.validators import validate_scene
from epos.visual import build_visual_contract

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _state(session="resort-fidelity"):
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, session)
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4
    state.location_id = "loc_spa"
    for npc in state.npcs.values():
        npc.present = False
        npc.location_id = "elsewhere"
    state.npcs["luna"].present = True
    state.npcs["luna"].location_id = "loc_spa"
    return pack, state


def _scene(
    *,
    narration="Luna prepara il lettino e invita il cliente fuori campo a rilassarsi.",
    dialogue_text="Ti guido io: prima respira, poi inizio il massaggio con l'olio.",
    action="prepara un massaggio con olio sul lettino",
    visual_en="Luna stands beside the massage table, preparing warm oil for the off-camera VIP guest.",
    summary="Luna prepara il lettino per il cliente fuori campo.",
    tags=("spa", "massage oil"),
    focus="luna",
    visible=("luna",),
    initiatives=(),
):
    return FinalScene.from_dict(
        {
            "narration": narration,
            "dialogue": [{"speaker": "Luna", "to": "player", "text": dialogue_text}] if dialogue_text else [],
            "npc_actions": [{"npc_id": "luna", "action": action}] if action else [],
            "intentions": [],
            "initiatives": list(initiatives),
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": summary,
                "focus_character": focus,
                "visible_characters": list(visible),
                "shared_action": False,
                "visual_en": visual_en,
                "tags_en": list(tags),
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


def test_on_the_player_does_not_imply_player_visible():
    pack, state = _state("on-player")
    scene = _scene(
        visual_en="Luna is applying sunscreen on the player, kneeling beside them.",
        summary="Luna applica la crema sul cliente fuori campo.",
        tags=("sunscreen application", "kneeling"),
    )

    corrected = enforce_resort_player_pov(state, pack.world, scene)

    assert corrected.visual.focus_character == "luna"
    assert corrected.visual.visible_characters == ["luna"]
    assert "applying sunscreen" in corrected.visual.visual_en
    assert "NPC introduction" not in corrected.visual.tags_en


def test_beside_the_player_does_not_imply_player_visible():
    pack, state = _state("beside-player")
    scene = _scene(
        visual_en="Luna kneels beside the player while presenting the bottle of sunscreen.",
        tags=("sunscreen application", "kneeling"),
    )

    corrected = enforce_resort_player_pov(state, pack.world, scene)

    assert "kneels beside" in corrected.visual.visual_en
    assert "off-camera VIP guest" in corrected.visual.visual_en
    assert "NPC introduction" not in corrected.visual.tags_en


def test_npc_introduction_not_applied_to_already_introduced_npc():
    pack, state = _state("intro-not-reused")
    scene = _scene(visual_en="Luna reclined on the spa couch, bare feet clearly visible.")

    corrected = enforce_resort_player_pov(state, pack.world, scene)

    assert "reclined" in corrected.visual.visual_en
    assert "NPC introduction" not in corrected.visual.tags_en


def test_npc_introduction_allowed_during_true_intro():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "intro-allowed")
    state.flags["resort_intro_active"] = True
    state.flags["resort_intro_completed"] = False
    state.flags["resort_intro_index"] = 1
    state.location_id = "loc_private_beach"
    state.npcs["luna"].location_id = "loc_private_beach"
    scene = _scene(focus="player", visible=("player",), visual_en="The player sees Luna on the beach.")

    corrected = enforce_resort_player_pov(state, pack.world, scene)

    assert corrected.visual.focus_character == "luna"
    assert corrected.visual.visible_characters == ["luna"]
    assert "NPC introduction" in corrected.visual.tags_en


def test_intro_completed_is_recorded_in_resort_fidelity_diagnostics():
    pack, state = _state("diag")
    original = _scene(visual_en="Luna is applying sunscreen on the player.")
    normalized = enforce_resort_player_pov(state, pack.world, original)

    diag = resort_fidelity_diagnostics(
        pack=pack.world,
        state=state,
        turn=15,
        player_text="comincia pure",
        original_scene=original,
        normalized_scene=normalized,
        player_leaked=False,
        wrong_intro_focus=False,
        fallback_applied=False,
        fallback_reason="",
    ).to_dict()

    assert diag["intro_active"] is False
    assert diag["expected_intro_npc"] == ""
    assert diag["visual_preserved"] is True
    assert diag["fallback_applied"] is False


def test_applying_sunscreen_survives_until_positive_prompt():
    pack, state = _state("sunscreen-prompt")
    scene = _scene(
        visual_en="Luna is applying sunscreen on the player, kneeling beside them.",
        tags=("sunscreen application", "kneeling", "luxury spa"),
    )
    corrected = enforce_resort_player_pov(state, pack.world, scene)
    contract = build_visual_contract(state, pack.world, corrected.visual, state.turn)

    assert "sunscreen application" in contract.prompt_package["positive"] or "applying sunscreen" in contract.prompt_package["positive"]
    assert "NPC introduction" not in contract.prompt_package["positive"]
    assert "addresses the unseen VIP guest" not in contract.prompt_package["positive"]


def test_lying_and_feet_requirements_survive_until_prompt():
    pack, state = _state("lying-feet")
    scene = _scene(
        visual_en="Luna reclined on the massage table, bare feet clearly visible and soles visible toward camera.",
        summary="Luna e sdraiata sul lettino e mostra bene i piedi.",
        tags=("lying down", "bare feet clearly visible", "soles visible"),
    )

    report = validate_resort_visual_requirements(pack.world, state, scene, "sdraiati e mostrameli bene")
    contract = build_visual_contract(state, pack.world, scene.visual, state.turn)
    positive = contract.prompt_package["positive"]

    assert report.ok
    assert "lying" in positive or "reclined" in positive
    assert "feet" in positive or "soles visible" in positive


def test_missing_mandatory_visual_requirement_triggers_retry_error():
    pack, state = _state("missing-mandatory")
    scene = _scene(visual_en="Luna stands beside the massage table with warm oil.", tags=("spa",))

    report = validate_resort_visual_requirements(pack.world, state, scene, "sdraiati e mostrameli bene")

    assert not report.ok
    assert any(error.code == "resort_mandatory_visual_requirement_missing" for error in report.errors)
    assert report.errors[0].details["retry_triggered"] is True


def test_visible_characters_match_named_visual_character():
    pack, state = _state("visible-ok")
    scene = _scene(visual_en="Luna reclined on the massage table.")

    assert validate_scene(state, pack.world, scene).ok


def test_named_visual_character_missing_from_visible_characters_is_detected():
    pack, state = _state("visible-missing")
    scene = _scene(visual_en="Luna and Maria stand near the massage table.", visible=("luna",))

    report = validate_scene(state, pack.world, scene)

    assert any(error.code == "visible_character_text_conflict" for error in report.errors)


def test_five_reactive_turns_require_concrete_initiative():
    pack, state = _state("initiative-required")
    state.initiative.consecutive_reactive_turns = 5
    scene = _scene(initiatives=(), action="resta in attesa", dialogue_text="Resto qui.")

    report = validate_initiative_obligation(state, scene, "che succede?")

    assert any(error.code == "resort_autonomous_initiative_required" for error in report.errors)


def test_three_reactive_turns_create_strong_hint_without_blocking():
    pack, state = _state("initiative-hint")
    state.initiative.consecutive_reactive_turns = 3
    scene = _scene(initiatives=(), action="resta in attesa", dialogue_text="Resto qui.")

    report = validate_initiative_obligation(state, scene, "che succede?")
    context = initiative_context(state)

    assert report.ok
    assert "valuta fortemente" in context["hint"]


def test_false_initiative_smile_is_rejected():
    pack, state = _state("false-initiative")
    event = InitiativeEvent(source="luna", type="other", summary="Luna sorride", target="player")

    assert any("reazione pura" in problem for problem in validate_initiative(state, event))


def test_concrete_initiative_is_accepted():
    pack, state = _state("concrete-initiative")
    event = InitiativeEvent(
        source="luna",
        type="offer",
        summary="Luna propone un massaggio con olio caldo nella sala spa.",
        reason="vuole guidare attivamente il rilassamento del cliente",
        target="player",
    )

    assert validate_initiative(state, event) == []


def test_dimmi_come_requires_substantial_npc_response():
    pack, state = _state("dimmi-come")
    scene = _scene(dialogue_text="Certo, posso aiutarti.")

    report = validate_dialogue_substance(state, scene, "dimmi come")

    assert any(error.code == "resort_npc_dialogue_evasive" for error in report.errors)


def test_continua_accepts_advanced_scene():
    pack, state = _state("continua-advance")
    state.last_scene = "Luna resta accanto al lettino e prepara l'ambiente."
    scene = _scene(
        narration="Luna versa l'olio sulle mani e comincia il massaggio lento sulla spalla.",
        dialogue_text="Comincio dalle spalle, poi scendo con calma.",
        action="inizia un massaggio con olio sulle spalle",
    )

    assert validate_scene_progression(state, scene, "continua").ok


def test_continua_rejects_nearly_identical_scene():
    pack, state = _state("continua-repeat")
    state.last_scene = "Luna resta accanto al lettino e prepara l'ambiente."
    scene = _scene(
        narration="Luna resta accanto al lettino e prepara l'ambiente.",
        dialogue_text="Resto accanto al lettino e preparo l'ambiente.",
        action="resta accanto al lettino",
    )

    report = validate_scene_progression(state, scene, "continua")

    assert any(error.code == "resort_scene_did_not_progress" for error in report.errors)


def test_repetition_without_progression_request_only_warns():
    pack, state = _state("repeat-warning")
    state.last_scene = "Luna resta accanto al lettino e prepara l'ambiente."
    scene = _scene(
        narration="Luna resta accanto al lettino e prepara l'ambiente.",
        dialogue_text="",
        action="",
    )

    report = validate_scene_progression(state, scene, "ti guardo")

    assert report.ok
    assert any(warning.code == "resort_scene_repetition_warning" for warning in report.warnings)


def test_player_input_echo_as_npc_dialogue_is_detected():
    pack, state = _state("echo")
    scene = _scene(dialogue_text="Comincia pure!")

    report = validate_resort_scene_policy(state, pack.world, scene, "comincia pure!")

    assert any(error.code == "npc_dialogue_copies_player_input" for error in report.errors)


@pytest.mark.parametrize("reply", ["si", "s?", "no", "va bene", "ok", "okay"])
def test_short_replies_remain_allowed_when_context_is_not_explanatory(reply):
    pack, state = _state(f"short-{reply}")
    scene = _scene(dialogue_text=reply)

    assert validate_dialogue_substance(state, scene, "ti guardo").ok


def test_resort_policy_keeps_focus_outfit_player_off_camera_and_single_character_default():
    pack, state = _state("invariants")
    scene = _scene(
        visual_en="Luna kneels beside the player while applying sunscreen on the player.",
        tags=("sunscreen application", "single-character composition"),
    )
    before_outfit = state.npcs["luna"].outfit.to_dict()

    corrected = enforce_resort_player_pov(state, pack.world, scene)
    report = validate_resort_scene_policy(state, pack.world, corrected, "comincia pure")
    contract = build_visual_contract(state, pack.world, corrected.visual, state.turn)

    assert report.ok
    assert corrected.visual.focus_character == "luna"
    assert corrected.visual.visible_characters == ["luna"]
    assert corrected.visual.shared_action is False
    assert "off-camera VIP guest" in contract.prompt_package["positive"]
    assert state.npcs["luna"].outfit.to_dict() == before_outfit
    assert "fitted ivory VIP attendant mini dress" in contract.prompt_package["positive"]
