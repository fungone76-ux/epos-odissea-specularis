"""Fase 1: schemi espliciti per contratti GM, visual e missioni."""

import pytest

from epos.contract import ContractError, GmPhaseResponse, VisualMoment
from epos.schemas import (
    GM_PHASE_RESPONSE_SCHEMA,
    VISUAL_MOMENT_SCHEMA,
    WORLDPACK_MISSION_SCHEMA,
    SchemaError,
    validate_worldpack_mission_shape,
)
from epos.worldpack import WorldPackError, load_pack


def test_gm_phase_schema_declares_all_modes():
    assert set(GM_PHASE_RESPONSE_SCHEMA["modes"]) == {
        "no_check",
        "check_proposal",
        "confront_proposal",
        "clarification",
    }


def test_visual_schema_declares_required_authoritative_fields():
    assert VISUAL_MOMENT_SCHEMA["required"] == [
        "focus_character",
        "visible_characters",
        "visual_en",
    ]


def test_contract_uses_schema_before_domain_parsing():
    with pytest.raises(ContractError, match="missing required"):
        GmPhaseResponse.from_dict({"mode": "check_proposal"})


def test_visual_schema_rejects_focus_outside_visible_characters():
    with pytest.raises(ContractError, match="focus_character"):
        VisualMoment.from_dict(
            {
                "focus_character": "player",
                "visible_characters": ["polifemo"],
                "visual_en": "a mythic cave",
            }
        )


def test_worldpack_mission_schema_declares_required_data_driven_fields():
    required = set(WORLDPACK_MISSION_SCHEMA["required"])
    assert {
        "id",
        "location_id",
        "objectives",
        "success_conditions",
        "failure_conditions",
        "rewards",
        "consequences",
        "transitions",
    } <= required


def test_worldpack_mission_shape_accepts_structured_mission():
    validate_worldpack_mission_shape(
        {
            "id": "mission_ciclopi_escape",
            "location_id": "loc_ciclopi",
            "name": "La Cieca e il Pasto",
            "description": "Fuggire dalla caverna di Polifemo.",
            "prerequisites": [],
            "objectives": [{"id": "escape", "target": "polifemo"}],
            "success_conditions": [{"type": "mission_complete", "target": "loc_ciclopi"}],
            "failure_conditions": [{"type": "outcome", "outcome": "critical_failure"}],
            "rewards": [{"type": "resource_delta", "resource": "kleos", "delta": 1}],
            "consequences": [{"type": "pressure_advance", "pressure": "press_poseidone"}],
            "transitions": [{"location_id": "loc_eolo"}],
            "alternative_solutions": [{"skill": "sarissa"}],
        },
        location_ids={"loc_ciclopi", "loc_eolo"},
        known_ids={"player", "polifemo"},
    )


def test_worldpack_mission_shape_rejects_unknown_transition_location():
    with pytest.raises(SchemaError, match="unknown location"):
        validate_worldpack_mission_shape(
            {
                "id": "mission_bad",
                "location_id": "loc_ciclopi",
                "name": "Bad",
                "description": "Bad",
                "objectives": [{"id": "escape", "target": "polifemo"}],
                "success_conditions": [{"type": "mission_complete"}],
                "failure_conditions": [{"type": "outcome"}],
                "rewards": [{"type": "resource_delta"}],
                "consequences": [{"type": "pressure_advance"}],
                "transitions": [{"location_id": "loc_missing"}],
            },
            location_ids={"loc_ciclopi"},
            known_ids={"player", "polifemo"},
        )


def test_load_pack_parses_optional_missions(tmp_path):
    (tmp_path / "world.yaml").write_text(
        """id: x
name: X
title: X
start_location_id: loc_a
locations:
  - id: loc_a
    name: A
  - id: loc_b
    name: B
missions:
  - id: mission_a
    location_id: loc_a
    name: Mission A
    description: A mission.
    objectives:
      - id: objective_a
        target: player
    success_conditions:
      - type: mission_complete
        target: mission_a
    failure_conditions:
      - type: outcome
        outcome: critical_failure
    rewards:
      - type: resource_delta
        resource: kleos
        delta: 1
    consequences:
      - type: pressure_advance
        pressure: press_test
    transitions:
      - location_id: loc_b
""",
        encoding="utf-8",
    )
    pack = load_pack(tmp_path)
    mission = pack.missions["mission_a"]
    assert mission.location_id == "loc_a"
    assert mission.transitions == [{"location_id": "loc_b"}]


def test_load_pack_rejects_invalid_mission_schema(tmp_path):
    (tmp_path / "world.yaml").write_text(
        """id: x
title: X
start_location_id: loc_a
locations:
  - id: loc_a
    name: A
missions:
  - id: mission_a
    location_id: loc_missing
    name: Mission A
    description: A mission.
    objectives: []
    success_conditions: []
    failure_conditions: []
    rewards: []
    consequences: []
    transitions: []
""",
        encoding="utf-8",
    )
    with pytest.raises(WorldPackError, match="location_id"):
        load_pack(tmp_path)
