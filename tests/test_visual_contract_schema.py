"""Fase 1: schema esplicito del VisualContract."""

from pathlib import Path

import pytest

from epos.contract import VisualMoment
from epos.schemas import VISUAL_CONTRACT_SCHEMA, SchemaError, validate_visual_contract_shape
from epos.visual import VisualContract, build_visual_contract
from epos.worldpack import load_pack

DEMO_PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"
ODYSSEY_PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


def test_visual_contract_schema_declares_renderer_and_authoritative_state_fields():
    required = set(VISUAL_CONTRACT_SCHEMA["required"])
    assert {
        "turn",
        "location_id",
        "focus_character",
        "visible_characters",
        "characters",
        "time_phase",
        "visual_en",
        "tags_en",
        "prompt_package",
        "concrete_action",
        "place",
        "canonical_outfit",
        "pose",
        "shot_type",
        "camera_side",
        "camera_angle",
        "lighting",
        "positive_prompt",
        "negative_prompt",
        "visual_reason",
    } <= required
    assert VISUAL_CONTRACT_SCHEMA["prompt_package_required"] == ["positive", "negative"]
    assert "outfit_worn" in VISUAL_CONTRACT_SCHEMA["character_required"]


def test_visual_contract_from_dict_rejects_missing_negative_prompt():
    payload = {
        "turn": 0,
        "location_id": "loc_ciclopi",
        "moment": "Ulisse guarda la caverna",
        "focus_character": "player",
        "visible_characters": ["player"],
        "shared_action": False,
        "characters": [
            {"id": "player", "outfit_worn": [], "outfit_removed": [], "wounds": []}
        ],
        "time_phase": "giorno",
        "visual_en": "a mythic queen watching a cave",
        "tags_en": [],
        "prompt_package": {"positive": "a mythic queen"},
        "concrete_action": "Ulisse guarda la caverna",
        "place": "Caverna dei Ciclopi",
        "canonical_outfit": {"player": {"worn": [], "removed": [], "outfit_state": {}, "conditions": [], "wounds": []}},
        "pose": "standing",
        "shot_type": "full_body",
        "camera_side": "front_three_quarter",
        "camera_angle": "eye_level",
        "lighting": "worldpack_default",
        "positive_prompt": "a mythic queen",
        "negative_prompt": "bad anatomy",
        "visual_reason": "test",
    }
    with pytest.raises(SchemaError, match="negative"):
        VisualContract.from_dict(payload)


def test_visual_contract_shape_rejects_character_not_visible():
    payload = {
        "turn": 0,
        "location_id": "loc_ciclopi",
        "moment": "Ulisse guarda la caverna",
        "focus_character": "player",
        "visible_characters": ["player"],
        "shared_action": False,
        "characters": [
            {"id": "polifemo", "outfit_worn": [], "outfit_removed": [], "wounds": []}
        ],
        "time_phase": "giorno",
        "visual_en": "a mythic queen watching a cave",
        "tags_en": [],
        "prompt_package": {"positive": "a mythic queen", "negative": "bad anatomy"},
        "concrete_action": "Ulisse guarda la caverna",
        "place": "Caverna dei Ciclopi",
        "canonical_outfit": {"polifemo": {"worn": [], "removed": [], "outfit_state": {}, "conditions": [], "wounds": []}},
        "pose": "standing",
        "shot_type": "full_body",
        "camera_side": "front_three_quarter",
        "camera_angle": "eye_level",
        "lighting": "worldpack_default",
        "positive_prompt": "a mythic queen",
        "negative_prompt": "bad anatomy",
        "visual_reason": "test",
    }
    with pytest.raises(SchemaError, match="visible_characters"):
        validate_visual_contract_shape(payload)


def test_built_demo_visual_contract_passes_explicit_schema():
    pack = load_pack(DEMO_PACK)
    state = pack.new_world()
    moment = VisualMoment.from_dict(
        {
            "summary": "Maera studia il viandante",
            "focus_character": "maera",
            "visible_characters": ["maera"],
            "shared_action": False,
            "visual_en": "an innkeeper studying a stranger",
            "tags_en": ["firelight"],
        }
    )
    contract = build_visual_contract(state, pack, moment, turn=0)
    validate_visual_contract_shape(contract.to_dict())
    assert VisualContract.from_dict(contract.to_dict()) == contract


def test_built_visual_contract_exposes_phase5_director_fields():
    pack = load_pack(ODYSSEY_PACK)
    state = pack.new_world()
    moment = VisualMoment.from_dict(
        {
            "summary": "Ulisse raises the bronze bow",
            "focus_character": "player",
            "visible_characters": ["player"],
            "shared_action": False,
            "moment_type": "action",
            "actor_character": "player",
            "visual_en": "Ulisse raises her bronze bow in the cave firelight",
            "tags_en": ["tense posture"],
        }
    )
    contract = build_visual_contract(state, pack, moment, turn=3)
    payload = contract.to_dict()
    validate_visual_contract_shape(payload)
    assert payload["concrete_action"] == "Ulisse raises the bronze bow"
    assert payload["place"] == pack.locations[state.location_id].name
    assert payload["canonical_outfit"]["player"]["outfit_state"]
    assert payload["positive_prompt"] == payload["prompt_package"]["positive"]
    assert payload["negative_prompt"] == payload["prompt_package"]["negative"]
    assert payload["visual_reason"]
    assert payload["shot_type"] == payload["camera_director"]["shot_type"]
    assert payload["camera_side"] == payload["camera_director"]["camera_side"]
    assert payload["camera_angle"] == payload["camera_director"]["camera_angle"]
    assert payload["lighting"] == "firelight"


def test_odyssey_visual_contract_contains_structured_camera_director_when_enabled():
    pack = load_pack(ODYSSEY_PACK)
    state = pack.new_world()
    moment = VisualMoment.from_dict(
        {
            "summary": "Ulisse avanza verso la caverna",
            "focus_character": "player",
            "visible_characters": ["player"],
            "shared_action": False,
            "visual_en": "Low angle side shot of Ulisse advancing toward the cave",
            "tags_en": ["wide shot", "side view", "low angle"],
        }
    )
    contract = build_visual_contract(state, pack, moment, turn=0)
    validate_visual_contract_shape(contract.to_dict())
    for field in VISUAL_CONTRACT_SCHEMA["camera_director_required_when_present"]:
        assert field in contract.camera_director
    assert contract.prompt_package["positive"]
    assert contract.prompt_package["negative"]
