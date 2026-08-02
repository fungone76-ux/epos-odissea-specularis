import subprocess
import sys

import pytest

from epos.contract import FinalScene
from epos.entity_ids import normalize_scene_entity_ids
from epos.models import (
    FOOTWEAR_TERMS,
    LOWER_CLOTHING_TERMS,
    TORSO_CLOTHING_TERMS,
    NpcState,
    Outfit,
    PlayerState,
    WorldState,
    outfit_state,
)


def _state() -> WorldState:
    return WorldState(
        session_id="canonical-no-patch",
        turn=0,
        time_phase="morning",
        location_id="loc_lobby",
        player=PlayerState(name="Guest", location_id="loc_lobby"),
        npcs={
            "victoria": NpcState(
                id="victoria",
                name="Victoria Hale",
                age=32,
                location_id="loc_lobby",
                present=True,
            )
        },
    )


def test_outfit_vocabularies_are_immutable():
    assert isinstance(TORSO_CLOTHING_TERMS, frozenset)
    assert isinstance(LOWER_CLOTHING_TERMS, frozenset)
    assert isinstance(FOOTWEAR_TERMS, frozenset)
    with pytest.raises(AttributeError):
        TORSO_CLOTHING_TERMS.update({"mutation forbidden"})


def test_modern_outfit_terms_are_canonical_without_resort_bootstrap():
    state = outfit_state(
        Outfit(worn=["black luxury bikini", "sheer black beach sarong", "high heels"])
    )
    assert state["nudity_mode"] == "clothed"
    assert state["torso_slot"] == ["black luxury bikini"]
    assert state["lower_body_slot"] == [
        "black luxury bikini",
        "sheer black beach sarong",
    ]
    assert state["footwear"] == ["high heels"]


def test_placeholder_npc_id_is_resolved_by_canonical_normalizer():
    scene = FinalScene.from_dict(
        {
            "narration": "Victoria risponde.",
            "dialogue": [
                {"speaker": "Victoria", "to": "player", "text": "Certamente."}
            ],
            "npc_actions": [{"npc_id": "npc_id", "action": "annuisce"}],
            "intentions": [{"npc_id": "npc_id", "intention": "help"}],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": "Victoria annuisce.",
                "focus_character": "npc_id",
                "visible_characters": ["npc_id"],
                "shared_action": False,
                "visual_en": "Victoria nods in the lobby.",
                "tags_en": ["lobby"],
                "moment_type": "speech",
                "speaker_character": "npc_id",
                "actor_character": "npc_id",
                "reactor_character": "",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": ["npc_id"],
            },
        }
    )
    result = normalize_scene_entity_ids(_state(), scene, phase="test")
    assert result.value.npc_actions[0]["npc_id"] == "victoria"
    assert result.value.intentions[0]["npc_id"] == "victoria"
    assert result.value.visual.focus_character == "victoria"
    assert result.value.visual.visible_characters == ["victoria"]
    assert result.value.dialogue[0].speaker == "Victoria"
    assert any(entry.alias_rule == "scene_placeholder_npc_id" for entry in result.entries)


def test_headless_bootstrap_does_not_load_deleted_runtime_patch_module():
    code = """
import sys
from epos.resort_bootstrap import bootstrap_resort_runtime
bootstrap_resort_runtime()
assert not any(name.startswith('epos.resort_') and name.endswith('_patch') for name in sys.modules)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
