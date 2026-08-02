from pathlib import Path

from epos.contract import FinalScene
from epos.gm import DemoGameMaster
from epos.resort_gui import build_resort_gui_status
from epos.resort_playable_turn_service import (
    ResortPlayableTurnService,
    _allow_solo_navigation,
)
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


def test_natural_room_request_moves_player_without_calling_llm():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "deterministic-room")
    _complete_intro(state)
    service = ResortPlayableTurnService(gm=DemoGameMaster(), pack=pack.world)
    service.store.save_state(state)

    result = service.play(
        state,
        "Adesso andrei nella mia stanza: vorrei rilassarmi dopo il viaggio.",
    )

    assert result.mode == "no_check"
    assert state.location_id == "loc_suite"
    assert state.player.location_id == "loc_suite"
    assert all(not npc.present for npc in state.npcs.values())


def test_requested_npc_reaches_player_and_becomes_present():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "summon-luna")
    _complete_intro(state)
    state.location_id = "loc_suite"
    state.player.location_id = "loc_suite"
    for npc in state.npcs.values():
        npc.present = False
    service = ResortPlayableTurnService(gm=DemoGameMaster(), pack=pack.world)
    service.store.save_state(state)

    result = service.play(state, "Fate venire Luna nella mia stanza, per favore.")

    assert result.mode == "no_check"
    assert state.npcs["luna"].location_id == "loc_suite"
    assert state.npcs["luna"].present is True
    assert any(line["speaker"] == "Luna" for line in result.dialogue)


def test_gui_status_lists_all_npc_locations_after_intro():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "npc-location-panel")
    _complete_intro(state)
    state.location_id = "loc_suite"
    state.player.location_id = "loc_suite"
    state.npcs["luna"].location_id = "loc_suite"
    state.npcs["luna"].present = True

    status = build_resort_gui_status(state, pack)
    locations = {item["id"]: item for item in status["npc_locations"]}

    assert status["intro_completed"] is True
    assert set(locations) == {"victoria", "luna", "maria", "stella"}
    assert locations["luna"]["location_name"] == "Suite presidenziale"
    assert locations["luna"]["with_player"] is True
    assert locations["victoria"]["location_name"] == "Lobby"
