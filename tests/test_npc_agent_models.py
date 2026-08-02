from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from epos.npc_agent_models import NpcAgentState
from epos.npc_agent_registry import NpcAgentRegistry


def test_npc_agent_state_minimal_defaults_roundtrip_and_immutability():
    state = NpcAgentState(npc_id="maera")

    assert state.npc_id == "maera"
    assert state.persona_summary == ""
    assert state.current_goal == ""
    assert state.current_intention == ""
    assert state.emotion == ""
    assert state.relationship_refs == ()
    assert state.knowledge_refs == ()
    assert state.open_thread_ids == ()
    assert state.mission_refs == ()
    assert state.initiative_priority == 0
    assert state.next_evaluation_turn == 0
    assert state.enabled is True
    assert NpcAgentState.from_dict(state.to_dict()) == state
    with pytest.raises(FrozenInstanceError):
        state.current_goal = "changed"  # type: ignore[misc]


def test_npc_agent_state_complete_normalizes_refs_without_changing_content():
    state = NpcAgentState(
        npc_id="maera",
        persona_summary="  guarded innkeeper  ",
        current_goal="  test the stranger  ",
        current_intention="  listen  ",
        emotion="  wary  ",
        relationship_refs=(" maera:player ", "maera:player", "maera:corren"),
        knowledge_refs=("maera:knowledge:0", "", "maera:knowledge:0", "maera:knowledge:1"),
        open_thread_ids=("thread_a", "thread_a", "thread_b"),
        mission_refs=("mission_a", "mission_a"),
        initiative_priority=40,
        next_evaluation_turn=3,
        enabled=False,
    )

    assert state.persona_summary == "guarded innkeeper"
    assert state.current_goal == "test the stranger"
    assert state.current_intention == "listen"
    assert state.emotion == "wary"
    assert state.relationship_refs == ("maera:player", "maera:corren")
    assert state.knowledge_refs == ("maera:knowledge:0", "maera:knowledge:1")
    assert state.open_thread_ids == ("thread_a", "thread_b")
    assert state.mission_refs == ("mission_a",)
    assert NpcAgentState.from_dict(state.to_dict()) == state


@pytest.mark.parametrize("npc_id", ["", " ", "Maera Dolk", "maera dolk"])
def test_npc_agent_state_rejects_empty_or_display_facing_ids(npc_id):
    with pytest.raises(ValueError):
        NpcAgentState(npc_id=npc_id)


@pytest.mark.parametrize("priority", [-1, 101])
def test_npc_agent_state_rejects_invalid_priority(priority):
    with pytest.raises(ValueError):
        NpcAgentState(npc_id="maera", initiative_priority=priority)


def test_npc_agent_state_rejects_negative_next_evaluation_turn():
    with pytest.raises(ValueError):
        NpcAgentState(npc_id="maera", next_evaluation_turn=-1)


def test_npc_agent_registry_empty_upsert_replace_remove_and_order():
    registry = NpcAgentRegistry()
    maera = NpcAgentState(npc_id="maera", initiative_priority=10)
    corren = NpcAgentState(npc_id="corren")

    registry = registry.upsert(maera).upsert(corren)
    assert registry.all() == (maera, corren)
    assert registry.get("maera") == maera
    assert registry.contains("corren") is True
    assert registry.get("missing") is None

    replacement = NpcAgentState(npc_id="maera", initiative_priority=20)
    registry = registry.upsert(replacement)
    assert registry.all() == (replacement, corren)
    assert registry.remove("maera").all() == (corren,)
    assert registry.enabled() == (replacement, corren)


def test_npc_agent_registry_serialization_and_duplicate_rejection():
    maera = NpcAgentState(npc_id="maera")
    corren = NpcAgentState(npc_id="corren", enabled=False)
    registry = NpcAgentRegistry((maera, corren))

    assert NpcAgentRegistry.from_dict(registry.to_dict()) == registry
    assert registry.enabled() == (maera,)
    assert NpcAgentRegistry.from_dict(None).all() == ()
    with pytest.raises(ValueError):
        NpcAgentRegistry((maera, maera))
