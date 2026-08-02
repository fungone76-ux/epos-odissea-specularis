from pathlib import Path

from epos.contract import FinalScene
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.resort_turn_service import (
    enforce_resort_player_pov,
    validate_resort_scene_policy,
)

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _state_with_only_maria_present():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "dict-npc-action")
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4
    state.flags["resort_intro_presented"] = ["victoria", "luna", "maria", "stella"]
    state.location_id = "loc_suite"
    state.player.location_id = "loc_suite"
    for npc_id, npc in state.npcs.items():
        npc.location_id = "loc_suite" if npc_id == "maria" else npc.location_id
        npc.present = npc_id == "maria"
    return pack, state


def test_dict_npc_action_satisfies_resort_response_policy():
    pack, state = _state_with_only_maria_present()
    scene = FinalScene.from_dict(
        {
            "narration": "Maria si avvicina lentamente, lusingata dalla richiesta.",
            "dialogue": [],
            "npc_actions": [
                {
                    "npc_id": "maria",
                    "action": "si avvicina al giocatore, creando un'atmosfera intima.",
                }
            ],
            "intentions": [],
            "mutations": [],
            "initiatives": [],
            "disclosure_events": [],
            "memory_events": [],
            "visual": {
                "summary": "Momento intimo nella suite.",
                "focus_character": "maria",
                "visible_characters": ["maria"],
                "shared_action": False,
                "moment_type": "intimate",
                "speaker_character": "",
                "actor_character": "maria",
                "reactor_character": "",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": [],
                "visual_en": "Maria moving closer in the presidential suite.",
                "tags_en": ["intimate atmosphere", "warm light"],
            },
        }
    )

    assert isinstance(scene.npc_actions[0], dict)
    report = validate_resort_scene_policy(state, pack.world, scene)

    assert report.ok
    assert not any(
        error.code == "resort_npc_response_required" for error in report.errors
    )


def test_dict_npc_action_becomes_visual_focus():
    pack, state = _state_with_only_maria_present()
    scene = FinalScene.from_dict(
        {
            "narration": "Maria compie un gesto concreto.",
            "dialogue": [],
            "npc_actions": [
                {"npc_id": "maria", "action": "si avvicina al giocatore"}
            ],
            "intentions": [],
            "mutations": [],
            "initiatives": [],
            "disclosure_events": [],
            "memory_events": [],
            "visual": {
                "summary": "Visual proposto con focus errato.",
                "focus_character": "player",
                "visible_characters": ["player"],
                "shared_action": False,
                "moment_type": "action",
                "speaker_character": "",
                "actor_character": "player",
                "reactor_character": "",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": [],
                "visual_en": "the player watches Maria in the suite",
                "tags_en": ["suite"],
            },
        }
    )

    corrected = enforce_resort_player_pov(state, pack.world, scene)

    assert corrected.visual.focus_character == "maria"
    assert corrected.visual.visible_characters == ["maria"]
    assert corrected.visual.actor_character == "maria"


def test_visual_actor_reaction_satisfies_resort_response_policy_without_dialogue_or_action():
    pack, state = _state_with_only_maria_present()
    scene = FinalScene.from_dict(
        {
            "narration": "Maria reagisce in silenzio ma in modo visibile.",
            "dialogue": [],
            "npc_actions": [],
            "intentions": [],
            "mutations": [],
            "initiatives": [],
            "disclosure_events": [],
            "memory_events": [],
            "visual": {
                "summary": "Maria reagisce chiaramente nella suite.",
                "focus_character": "maria",
                "visible_characters": ["maria"],
                "shared_action": False,
                "moment_type": "action",
                "speaker_character": "",
                "actor_character": "maria",
                "reactor_character": "maria",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": ["maria"],
                "visual_en": "Maria visibly reacts inside the presidential suite.",
                "tags_en": ["NPC reaction", "suite"],
            },
        }
    )

    report = validate_resort_scene_policy(state, pack.world, scene)

    assert report.ok


def test_absent_npc_action_does_not_satisfy_resort_response_policy():
    pack, state = _state_with_only_maria_present()
    scene = FinalScene.from_dict(
        {
            "narration": "Luna agirebbe, ma non e presente.",
            "dialogue": [],
            "npc_actions": [{"npc_id": "luna", "action": "risponde da lontano"}],
            "intentions": [],
            "mutations": [],
            "initiatives": [],
            "disclosure_events": [],
            "memory_events": [],
            "visual": None,
        }
    )

    report = validate_resort_scene_policy(state, pack.world, scene)

    assert any(error.code == "resort_npc_response_required" for error in report.errors)
