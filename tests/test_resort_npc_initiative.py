from pathlib import Path

from epos.contract import FinalScene
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.resort_turn_service import (
    enforce_resort_player_pov,
    validate_resort_scene_policy,
)

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _multi_npc_state():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "resort-npc-initiative")
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4
    state.flags["resort_intro_presented"] = ["victoria", "luna", "maria", "stella"]
    state.location_id = "loc_lounge"
    state.player.location_id = "loc_lounge"
    for npc_id, npc in state.npcs.items():
        npc.location_id = "loc_lounge" if npc_id in {"stella", "maria"} else npc.location_id
        npc.present = npc_id in {"stella", "maria"}
    return pack, state


def _visual(*, focus: str, visible: list[str], moment_type: str = "speech") -> dict:
    return {
        "summary": "Un momento di conversazione nella lounge.",
        "focus_character": focus,
        "visible_characters": visible,
        "shared_action": len(visible) > 1,
        "visual_en": "luxury resort lounge, cinematic conversation",
        "tags_en": ["luxury lounge", "conversation"],
        "moment_type": moment_type,
        "speaker_character": focus if moment_type == "speech" else "",
        "actor_character": "",
        "reactor_character": "",
        "intimate_shared_moment": False,
        "multi_character_reason": "conversation" if len(visible) > 1 else "",
        "multi_character_participants": visible,
    }


def test_autonomous_initiative_source_satisfies_resort_response_policy():
    pack, state = _multi_npc_state()
    scene = FinalScene.from_dict(
        {
            "narration": "Stella prende spontaneamente la parola e coinvolge Maria.",
            "dialogue": [],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [
                {
                    "source": "stella",
                    "type": "question",
                    "summary": "Stella propone a Maria di organizzare insieme la serata VIP.",
                    "reason": "Vuole dimostrare iniziativa e capacità di collaborazione.",
                    "target": "maria",
                }
            ],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": _visual(focus="player", visible=["player"], moment_type="action"),
        }
    )

    report = validate_resort_scene_policy(state, pack.world, scene)

    assert not any(
        error.code == "resort_npc_response_required" for error in report.errors
    )


def test_autonomous_initiative_source_overrides_wrong_present_npc_visual_focus():
    pack, state = _multi_npc_state()
    scene = FinalScene.from_dict(
        {
            "narration": "Stella interrompe il silenzio con una proposta concreta.",
            "dialogue": [],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [
                {
                    "source": "stella",
                    "type": "offer",
                    "summary": "Stella offre a Maria il proprio aiuto per il prossimo evento.",
                    "reason": "Vuole prendere il controllo della situazione.",
                    "target": "maria",
                }
            ],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": _visual(focus="maria", visible=["maria"], moment_type="action"),
        }
    )

    corrected = enforce_resort_player_pov(state, pack.world, scene)

    assert corrected.visual.focus_character == "stella"
    assert corrected.visual.visible_characters == ["stella"]
    assert corrected.visual.multi_character_participants == ["stella"]
    assert corrected.visual.shared_action is False


def test_npc_to_npc_dialogue_is_valid_and_first_speaker_gets_visual_focus():
    pack, state = _multi_npc_state()
    scene = FinalScene.from_dict(
        {
            "narration": "Stella coinvolge Maria, che le risponde senza attendere il giocatore.",
            "dialogue": [
                {
                    "speaker": "Stella",
                    "text": "Maria, prepariamo insieme qualcosa che il nostro ospite ricorderà.",
                    "to": "maria",
                },
                {
                    "speaker": "Maria",
                    "text": "D'accordo, ma lo faremo con precisione e senza improvvisare.",
                    "to": "stella",
                },
            ],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [
                {
                    "source": "stella",
                    "type": "offer",
                    "summary": "Stella propone a Maria una collaborazione concreta.",
                    "reason": "Vuole guidare l'iniziativa della serata.",
                    "target": "maria",
                }
            ],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": _visual(focus="maria", visible=["maria", "stella"]),
        }
    )

    corrected = enforce_resort_player_pov(state, pack.world, scene)
    report = validate_resort_scene_policy(state, pack.world, corrected)

    assert report.ok
    assert [line.to for line in corrected.dialogue] == ["maria", "stella"]
    assert corrected.visual.focus_character == "stella"
    assert corrected.visual.visible_characters == ["stella"]
    assert corrected.visual.speaker_character == "stella"


def test_absent_npc_initiative_does_not_satisfy_resort_policy():
    pack, state = _multi_npc_state()
    scene = FinalScene.from_dict(
        {
            "narration": "Victoria tenta di intervenire pur non essendo presente.",
            "dialogue": [],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [
                {
                    "source": "victoria",
                    "type": "question",
                    "summary": "Victoria pone una domanda dalla propria assenza.",
                    "reason": "Caso volutamente non valido.",
                    "target": "maria",
                }
            ],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": None,
        }
    )

    report = validate_resort_scene_policy(state, pack.world, scene)

    assert any(error.code == "resort_npc_response_required" for error in report.errors)
