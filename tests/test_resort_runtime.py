from pathlib import Path

from epos.models import WorldState
from epos.resort_relationships import apply_player_relationship_delta, record_preference
from epos.resort_runtime import (
    RESORT_PHASES,
    advance_resort_time,
    campaign_score,
    campaign_score_tier,
    complete_event,
    current_day,
    eligible_events,
    evaluate_resort_missions,
    llm_context_for_npc,
    load_resort_pack,
    new_resort_world,
    process_resort_turn,
    update_luna_disclosure_gates,
    update_mission_unlocks,
)


PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def test_resort_pack_loads_all_data_files():
    pack = load_resort_pack(PACK_DIR)
    assert pack.world.id == "resort_world"
    assert len(pack.world.locations) == 9
    assert set(pack.world.npc_canon) == {"victoria", "stella", "maria", "luna"}
    assert set(pack.world.missions) == set(pack.mission_policies)
    assert "event_bath_for_two" in pack.events
    assert pack.mission_policies["mission_resort_future"].success_points == 25


def test_resort_has_no_odyssey_ids_or_dependencies():
    pack = load_resort_pack(PACK_DIR)
    serialized = repr(pack)
    for forbidden in ("odyssey", "odissea", "polifemo", "poseidon", "itaca"):
        assert forbidden not in serialized.lower()


def test_new_state_initialises_calendar_relationships_outfits_and_score():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "resort-new")
    assert current_day(state) == 1
    assert state.time_phase == "mattina"
    assert state.flags["resort_debt_due_day"] == 7
    assert campaign_score(state) == 0
    assert state.flags["resort_mission_status"]["mission_resort_future"] == "active"
    for npc_id in ("victoria", "stella", "maria", "luna"):
        assert state.npcs[npc_id].age >= 18
        assert state.npcs[npc_id].outfit.worn
        assert state.npcs[npc_id].relationship_towards("player") is not None


def test_calendar_reaches_debt_deadline_on_seventh_evening():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "deadline")
    for _ in range(26):
        advance_resort_time(state, force=True)
    assert current_day(state) == 7
    assert state.time_phase == "sera"
    assert state.flags["resort_debt_due"] is True


def test_short_turns_do_not_always_advance_phase():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "mixed-time")
    for _ in range(3):
        assert advance_resort_time(state, force=False, turn_limit=4) is False
    assert state.time_phase == "mattina"
    assert advance_resort_time(state, force=False, turn_limit=4) is True
    assert state.time_phase == "pomeriggio"


def test_bath_for_two_event_is_eligible_and_completes():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "bath")
    state.location_id = "loc_suite"
    state.player.location_id = "loc_suite"
    state.time_phase = "sera"
    events = eligible_events(state, pack)
    event = next(event for event in events if event.id == "event_bath_for_two")
    assert event.consent_exit_required is True
    assert any(
        choice in {"decline", "cancel", "skip", "leave_event"}
        or "decline" in choice
        for choice in event.choices
    )
    complete_event(state, event)
    assert state.flags["maria_bath_service_recovered"] is True
    assert event.id in state.flags["resort_completed_events"]


def test_maria_mission_unlocks_after_bath_event():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "maria-unlock")
    event = pack.events["event_bath_for_two"]
    complete_event(state, event)
    unlocked = update_mission_unlocks(state, pack)
    assert "mission_maria_stability" in unlocked
    assert state.flags["resort_mission_status"]["mission_maria_stability"] == "active"


def test_luna_letter_is_not_revealed_early():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "luna-locked")
    context = llm_context_for_npc(state, pack, "luna")
    assert context["unlocked_secrets"] == []
    assert not any("lettera" in fact.lower() for fact in context["unlocked_secrets"])


def test_luna_disclosure_uses_python_gates():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "luna-gates")
    apply_player_relationship_delta(state, "luna", trust=2)
    update_luna_disclosure_gates(state)
    context = llm_context_for_npc(state, pack, "luna")
    assert state.flags["luna_letter_mention_unlocked"] is True
    assert any("lettera" in fact.lower() for fact in context["unlocked_secrets"])
    assert state.flags["luna_letter_reveal_unlocked"] is False


def test_relationship_preference_creates_persisted_jealousy_without_consent():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "preference")
    jealousy = record_preference(state, "maria")
    assert jealousy["stella"] == 1
    assert jealousy["luna"] == 1
    assert state.flags["resort_last_preferred_npc"] == "maria"
    context = llm_context_for_npc(state, pack, "maria")
    assert context["relationship"]["consent_is_never_implied"] is True


def test_all_events_are_adult_and_have_exit_when_required():
    pack = load_resort_pack(PACK_DIR)
    exit_tokens = ("decline", "cancel", "skip", "leave", "alone", "postpone", "end", "refuse")
    for event in pack.events.values():
        assert event.adult_component
        assert all(pack.world.npc_canon[npc_id].age >= 18 for npc_id in event.npc_ids)
        if event.consent_exit_required:
            assert any(token in choice for choice in event.choices for token in exit_tokens)


def test_llm_context_contains_only_one_npc_internal_state():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "context")
    context = llm_context_for_npc(state, pack, "maria")
    assert context["npc_id"] == "maria"
    assert "victoria" not in context.get("unlocked_secrets", [])
    assert context["outfit"]["worn"] == state.npcs["maria"].outfit.worn
    assert context["campaign_score"] == 0
    assert "intimate_profile" in context


def test_successful_maria_mission_awards_score_and_trust_once():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "maria-success")
    complete_event(state, pack.events["event_bath_for_two"])
    update_mission_unlocks(state, pack)
    state.flags["maria_contract_approved"] = True

    first = evaluate_resort_missions(state, pack)
    second = evaluate_resort_missions(state, pack)

    assert first == [
        {
            "mission_id": "mission_maria_stability",
            "status": "completed",
            "score_delta": 10,
            "score_total": 10,
            "rewards": [
                {
                    "type": "relationship",
                    "target_id": "maria",
                    "field": "trust",
                    "delta": 2,
                }
            ],
        }
    ]
    assert second == []
    assert campaign_score(state) == 10
    assert state.npcs["maria"].relationship_towards("player").trust == 2
    assert state.flags["resort_completed_missions"] == ["mission_maria_stability"]
    assert state.flags["resort_rewarded_missions"] == ["mission_maria_stability"]


def test_failed_luna_mission_applies_penalty_without_reward():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "luna-failure")
    apply_player_relationship_delta(state, "luna", trust=2)
    update_mission_unlocks(state, pack)
    state.flags["luna_letter_abused"] = True

    changes = evaluate_resort_missions(state, pack)

    assert changes[0]["mission_id"] == "mission_luna_letter"
    assert changes[0]["status"] == "failed"
    assert changes[0]["score_delta"] == -10
    assert changes[0]["rewards"] == []
    assert campaign_score(state) == -10
    assert state.npcs["luna"].relationship_towards("player").trust == 2


def test_main_and_victoria_can_complete_together_with_separate_rewards():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "shared-resort-success")
    state.flags["bank_debt_disclosed"] = True
    update_mission_unlocks(state, pack)
    state.flags["resort_saved"] = True

    changes = evaluate_resort_missions(state, pack)

    assert {change["mission_id"] for change in changes} == {
        "mission_resort_future",
        "mission_victoria_save_resort",
    }
    assert campaign_score(state) == 35
    assert state.flags["campaign_complete"] is True
    assert state.npcs["victoria"].relationship_towards("player").trust == 2
    assert campaign_score_tier(state) == "settimana_positiva"


def test_process_resort_turn_returns_unlocks_scores_and_changes():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "post-turn")
    complete_event(state, pack.events["event_bath_for_two"])
    result = process_resort_turn(state, pack)
    assert "mission_maria_stability" in result["unlocked_missions"]
    assert result["mission_changes"] == []
    assert result["campaign_score"] == 0
    assert result["score_tier"] == "soggiorno_fallimentare"


def test_state_roundtrip_preserves_resort_flags_relationships_outfit_and_score():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "roundtrip")
    state.flags["resort_day"] = 4
    state.flags["resort_campaign_score"] = 20
    state.npcs["stella"].relationship_towards("player").attraction = 3
    state.npcs["stella"].outfit.wear("red gala gloves")
    restored = WorldState.from_dict(state.to_dict())
    assert restored.flags["resort_day"] == 4
    assert restored.flags["resort_campaign_score"] == 20
    assert restored.npcs["stella"].relationship_towards("player").attraction == 3
    assert "red gala gloves" in restored.npcs["stella"].outfit.worn


def test_phases_are_exactly_the_four_canonical_values():
    assert RESORT_PHASES == ("mattina", "pomeriggio", "sera", "notte")
