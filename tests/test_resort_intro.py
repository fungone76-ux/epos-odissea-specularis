from pathlib import Path

from epos.contract import FinalScene
from epos.gm import DemoGameMaster
from epos.resort_intro import (
    INTRO_ORDER,
    advance_resort_intro,
    current_intro_step,
    initialise_resort_intro,
    intro_active,
    intro_context,
)
from epos.resort_intro_turn_service import ResortIntroTurnService
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.resort_turn_service import (
    enforce_resort_player_pov,
    validate_resort_scene_policy,
)
from epos.turn_service import TurnResult

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _intro_scene(npc_id: str, name: str) -> FinalScene:
    return FinalScene.from_dict(
        {
            "narration": f"{name} viene presentata al cliente VIP.",
            "dialogue": [
                {
                    "speaker": name,
                    "to": "player",
                    "text": f"Piacere, sono {name}.",
                }
            ],
            "npc_actions": [
                {"npc_id": npc_id, "action": "si presenta personalmente"}
            ],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": f"{name} si presenta al cliente fuori campo.",
                "focus_character": npc_id,
                "visible_characters": [npc_id],
                "shared_action": False,
                "visual_en": f"{name} addresses the unseen VIP guest in the resort lobby.",
                "tags_en": ["NPC introduction", "luxury resort"],
                "moment_type": "speech",
                "speaker_character": npc_id,
                "actor_character": npc_id,
                "reactor_character": npc_id,
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": [npc_id],
            },
        }
    )


def test_intro_starts_with_victoria_and_exposes_hard_context():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "intro-start")
    initialise_resort_intro(state)

    step = current_intro_step(state)
    context = intro_context(state)

    assert intro_active(state) is True
    assert step is not None
    assert step.npc_id == "victoria"
    assert context["target_npc_id"] == "victoria"
    assert context["step"] == 1
    assert context["total_steps"] == 4


def test_intro_advances_exactly_one_npc_per_player_turn():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "intro-order")
    initialise_resort_intro(state)

    observed = []
    for expected in INTRO_ORDER:
        step = current_intro_step(state)
        assert step is not None
        assert step.npc_id == expected
        observed.append(expected)
        result = TurnResult(turn=state.turn, mode="no_check", narration="ok")
        advance_resort_intro(state, result)

    assert observed == ["victoria", "luna", "maria", "stella"]
    assert intro_active(state) is False
    assert state.flags["resort_intro_completed"] is True
    assert state.flags["resort_intro_presented"] == list(INTRO_ORDER)


def test_intro_rejects_wrong_npc_and_wrong_image_subject():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "intro-wrong")
    initialise_resort_intro(state)

    wrong = _intro_scene("luna", "Luna")
    report = validate_resort_scene_policy(state, pack.world, wrong)
    codes = {error.code for error in report.errors}

    assert "resort_intro_target_response_required" in codes
    assert "resort_intro_visual_target_required" in codes


def test_intro_pov_forces_current_target_even_if_llm_selects_player():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "intro-pov")
    initialise_resort_intro(state)
    scene = FinalScene.from_dict(
        {
            "narration": "Il cliente scende e Victoria lo accoglie.",
            "dialogue": [
                {"speaker": "Victoria", "to": "player", "text": "Benvenuto."}
            ],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Il miliardario scende davanti a Victoria.",
                "focus_character": "player",
                "visible_characters": ["player", "victoria"],
                "shared_action": False,
                "visual_en": "The billionaire man descends while Victoria watches.",
                "tags_en": ["arrival"],
                "moment_type": "action",
                "speaker_character": "victoria",
                "actor_character": "player",
                "reactor_character": "victoria",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": ["player", "victoria"],
            },
        }
    )

    corrected = enforce_resort_player_pov(state, pack.world, scene)

    assert corrected.visual.focus_character == "victoria"
    assert corrected.visual.visible_characters == ["victoria"]
    assert "billionaire man" not in corrected.visual.visual_en.lower()


def test_after_stella_intro_next_turn_is_normal_gameplay():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "intro-complete")
    initialise_resort_intro(state)

    for _ in INTRO_ORDER:
        result = TurnResult(turn=state.turn, mode="no_check", narration="ok")
        advance_resort_intro(state, result)

    assert current_intro_step(state) is None
    assert intro_context(state) == {"active": False, "completed": True}


def test_strict_intro_rejects_stella_during_victoria_step():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "intro-strict-victoria")
    initialise_resort_intro(state)
    service = ResortIntroTurnService(gm=DemoGameMaster(), pack=pack.world)

    scene = FinalScene.from_dict(
        {
            "narration": "Victoria accoglie il cliente mentre Stella interviene.",
            "dialogue": [
                {"speaker": "Victoria", "to": "player", "text": "Benvenuto."},
                {"speaker": "Stella", "to": "player", "text": "Sarà indimenticabile."},
            ],
            "npc_actions": [
                {"npc_id": "victoria", "action": "si presenta"},
                {"npc_id": "stella", "action": "si avvicina"},
            ],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Victoria presenta il resort.",
                "focus_character": "victoria",
                "visible_characters": ["victoria"],
                "shared_action": False,
                "visual_en": "Victoria addresses the unseen VIP guest in the lobby.",
                "tags_en": ["NPC introduction", "luxury resort"],
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

    report = service._strict_intro_report(state, scene)
    assert any(error.code == "resort_intro_other_npc_forbidden" for error in report.errors)
