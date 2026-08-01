"""Fase 1: missioni Odissea come dati validati del world-pack."""

from dataclasses import replace

from pathlib import Path

import pytest

from epos.odyssey_mission_tracker import LOCATION_ORDER, MISSIONS as LEGACY_MISSIONS, OdysseyMissionTracker
from epos.contract import CheckProposal
from epos.odyssey_gm import OdysseyDemoGameMaster
from epos.rules import Outcome, Roll
from epos.turn_service import TurnResult
from epos.worldpack import WorldPackError, load_pack

PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


def _mission_result(skill, stake, target_ids=None, outcome=Outcome.FULL_SUCCESS):
    return TurnResult(
        turn=0,
        mode="check",
        narration="test",
        proposal=CheckProposal(
            action_kind=skill,
            skill=skill,
            difficulty=3,
            target_ids=list(target_ids or []),
        ),
        roll=Roll(pool_size=5, difficulty=3, dice=(6, 6), outcome=outcome),
        stake=stake,
    )


def test_odyssey_worldpack_defines_one_mission_per_location_in_order():
    pack = load_pack(PACK)
    assert list(m.location_id for m in pack.missions.values()) == LOCATION_ORDER
    assert len(pack.missions) == 10


def test_odyssey_worldpack_missions_match_legacy_tracker_data():
    pack = load_pack(PACK)
    by_location = {mission.location_id: mission for mission in pack.missions.values()}
    for loc_id, legacy in LEGACY_MISSIONS.items():
        mission = by_location[loc_id]
        objective_skills = mission.objectives[0]["required_skills"]
        assert mission.name == legacy.name
        assert mission.description == legacy.description
        assert mission.objectives[0]["difficulty"] == legacy.difficulty
        assert legacy.primary_skill in objective_skills
        if legacy.alternative_skill:
            assert legacy.alternative_skill in objective_skills
        if legacy.required_target:
            assert mission.objectives[0]["target"] == legacy.required_target


def test_odyssey_worldpack_missions_have_explicit_completion_and_failure():
    pack = load_pack(PACK)
    for mission in pack.missions.values():
        assert mission.objectives
        assert mission.success_conditions
        assert mission.failure_conditions
        assert mission.rewards
        assert mission.consequences
        assert mission.transitions
        assert any(c.get("type") == "mission_complete" for c in mission.success_conditions)


def test_odyssey_worldpack_mission_transitions_are_valid_locations():
    pack = load_pack(PACK)
    location_ids = set(pack.locations)
    for mission in pack.missions.values():
        for transition in mission.transitions:
            assert transition["location_id"] in location_ids


def test_itaca_mission_is_three_phase_data_not_keyword_only():
    pack = load_pack(PACK)
    itaca = pack.missions["mission_itaca"]
    assert [o["id"] for o in itaca.objectives] == ["disguise", "bow", "bed_recognition"]
    assert [o["required_skills"][0] for o in itaca.objectives] == ["dolos", "sarissa", "eros"]


def test_invalid_odyssey_mission_missing_required_fields_is_rejected(tmp_path):
    (tmp_path / "world.yaml").write_text(
        """id: bad
title: Bad
start_location_id: loc_a
locations:
  - id: loc_a
    name: A
missions:
  - id: mission_bad
    location_id: loc_a
    name: Bad
""",
        encoding="utf-8",
    )
    with pytest.raises(WorldPackError, match="missing required"):
        load_pack(tmp_path)


def test_odyssey_mission_tracker_uses_worldpack_mission_data():
    pack = load_pack(PACK)
    state = pack.new_world("tracker-pack-data")
    tracker = OdysseyMissionTracker(state, pack=pack)

    assert tracker.location_order == [mission.location_id for mission in pack.missions.values()]
    assert tracker.current_mission().name == pack.missions["mission_ciclopi"].name
    assert tracker.current_mission().description == pack.missions["mission_ciclopi"].description
    assert tracker.required_skills() == tuple(
        pack.missions["mission_ciclopi"].objectives[0]["required_skills"]
    )
    assert tracker.current_mission().required_target == "polifemo"


def test_odyssey_demo_gm_uses_worldpack_mission_data():
    pack = load_pack(PACK)
    mission = pack.missions["mission_ciclopi"]
    custom_mission = replace(
        mission,
        description="Missione modificata solo nel world-pack.",
        objectives=[{**mission.objectives[0], "difficulty": 7}],
    )
    pack = replace(pack, missions={**pack.missions, "mission_ciclopi": custom_mission})
    state = pack.new_world("gm-pack-data")

    response = OdysseyDemoGameMaster().propose(
        state, pack, "Inganno Polifemo dicendo di chiamarmi Nessuno"
    )

    assert response.check.difficulty == 7
    assert "Missione modificata solo nel world-pack." in response.check.reason


def test_odyssey_tracker_applies_yaml_effect_reward():
    pack = load_pack(PACK)
    state = pack.new_world("yaml-effect-reward")
    tracker = OdysseyMissionTracker(state, pack=pack)
    state.flags["odyssey_location_index"] = LOCATION_ORDER.index("loc_eolo")
    state.location_id = "loc_eolo"
    state.player.location_id = "loc_eolo"

    changes = tracker.process_turn(
        _mission_result("thumos", pack.missions["mission_eolo"].success_conditions[1]["text"])
    )

    assert changes["mission_completed"] is True
    assert state.flags["wind_bag_active"] is True
    assert state.flags["wind_bag_remaining"] == 1
    assert {r["type"] for r in changes["rewards_applied"]} >= {"resource_delta", "effect"}


def test_odyssey_tracker_applies_yaml_resource_set_reward():
    pack = load_pack(PACK)
    state = pack.new_world("yaml-resource-set")
    tracker = OdysseyMissionTracker(state, pack=pack)
    state.flags["odyssey_location_index"] = LOCATION_ORDER.index("loc_circe")
    state.location_id = "loc_circe"
    state.player.location_id = "loc_circe"

    changes = tracker.process_turn(
        _mission_result(
            "thumos",
            pack.missions["mission_circe"].success_conditions[1]["text"],
            target_ids=["circe"],
        )
    )

    assert changes["mission_completed"] is True
    assert state.flags["underworld_passage"] is True
    assert any(r.get("resource") == "underworld_passage" for r in changes["rewards_applied"])


def test_odyssey_tracker_applies_yaml_conditional_pressure_consequence():
    pack = load_pack(PACK)
    state = pack.new_world("yaml-pressure")
    tracker = OdysseyMissionTracker(state, pack=pack)

    changes = tracker.process_turn(
        _mission_result(
            "sarissa",
            pack.missions["mission_ciclopi"].success_conditions[1]["text"],
            target_ids=["polifemo"],
        )
    )

    assert changes["mission_completed"] is True
    assert state.pressures["press_poseidone"].level == 1
    assert changes["consequences_applied"] == [
        {"type": "pressure_advance", "pressure_id": "press_poseidone", "when": "sarissa_success"}
    ]


def test_odyssey_tracker_applies_yaml_failure_skill_delta():
    pack = load_pack(PACK)
    state = pack.new_world("yaml-failure-skill-delta")
    tracker = OdysseyMissionTracker(state, pack=pack)
    state.flags["odyssey_location_index"] = LOCATION_ORDER.index("loc_eolo")
    state.location_id = "loc_eolo"
    state.player.location_id = "loc_eolo"
    before = state.player.skill_rating("thumos")

    changes = tracker.process_turn(
        _mission_result("thumos", "fallisci", outcome=Outcome.FAILURE)
    )

    assert state.player.skill_rating("thumos") == before - 1
    assert changes["penalty"] == "-1 Thumos permanente"
    assert changes["failure_consequences_applied"] == [
        {"type": "skill_delta", "skill": "thumos", "delta": -1}
    ]


def test_odyssey_tracker_applies_yaml_terminal_failure_condition():
    pack = load_pack(PACK)
    state = pack.new_world("yaml-terminal-failure")
    tracker = OdysseyMissionTracker(state, pack=pack)
    state.flags["odyssey_location_index"] = LOCATION_ORDER.index("loc_calipso")
    state.location_id = "loc_calipso"
    state.player.location_id = "loc_calipso"

    changes = tracker.process_turn(
        _mission_result("thumos", "fallisci", target_ids=["calipso"], outcome=Outcome.FAILURE)
    )

    assert changes["game_over"] is True
    assert state.flags["game_over"] is True
    assert "Itaca" in changes["reason"]


def test_odyssey_tracker_applies_yaml_second_failure_condition():
    pack = load_pack(PACK)
    state = pack.new_world("yaml-second-failure")
    tracker = OdysseyMissionTracker(state, pack=pack)

    first = tracker.process_turn(
        _mission_result("dolos", "fallisci", target_ids=["polifemo"], outcome=Outcome.FAILURE)
    )
    second = tracker.process_turn(
        _mission_result("dolos", "fallisci", target_ids=["polifemo"], outcome=Outcome.FAILURE)
    )

    assert not first.get("game_over")
    assert second["game_over"] is True
    assert second["reason"] == "Polifemo ti ha divorata."
