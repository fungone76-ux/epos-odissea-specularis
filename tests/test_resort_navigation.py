from pathlib import Path

from epos.contract import FinalScene
from epos.resort_playable_turn_service import _allow_solo_navigation
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.resort_turn_service import validate_resort_scene_policy

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _complete_intro(state) -> None:
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4
    state.flags["resort_intro_presented"] = ["victoria", "luna", "maria", "stella"]


def _suite_navigation_scene() -> FinalScene:
    return FinalScene.from_dict(
        {
            "narration": (
                "Il cliente VIP lascia la lobby e raggiunge la suite presidenziale "
                "per riposarsi dopo il viaggio."
            ),
            "dialogue": [],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [
                {
                    "type": "location_change",
                    "target": "player",
                    "payload": {"location_id": "loc_suite"},
                    "reason": "Il giocatore ha chiesto di andare nella propria stanza.",
                }
            ],
            "memory_events": [],
            "visual": None,
        }
    )


def test_player_location_change_does_not_require_npc_response_after_intro():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "solo-navigation")
    _complete_intro(state)
    scene = _suite_navigation_scene()

    strict_report = validate_resort_scene_policy(state, pack.world, scene)
    assert any(
        error.code == "resort_npc_response_required"
        for error in strict_report.errors
    )
    assert not any(
        error.code == "resort_intro_target_response_required"
        for error in strict_report.errors
    )

    playable_report = _allow_solo_navigation(strict_report, scene)
    assert playable_report.ok
    assert not any(
        error.code == "resort_npc_response_required"
        for error in playable_report.errors
    )


def test_navigation_during_intro_still_requires_target_npc_response():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "navigation-during-intro")
    scene = _suite_navigation_scene()

    strict_report = validate_resort_scene_policy(state, pack.world, scene)
    playable_report = _allow_solo_navigation(strict_report, scene)

    assert any(
        error.code == "resort_intro_target_response_required"
        for error in playable_report.errors
    )


def test_non_navigation_turn_still_requires_npc_response():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "strict-social")
    _complete_intro(state)
    scene = FinalScene.from_dict(
        {
            "narration": "Il cliente resta in silenzio nella lobby.",
            "dialogue": [],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": None,
        }
    )
    strict_report = validate_resort_scene_policy(state, pack.world, scene)
    playable_report = _allow_solo_navigation(strict_report, scene)
    assert any(
        error.code == "resort_npc_response_required"
        for error in playable_report.errors
    )
