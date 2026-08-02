from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from epos.models import MemoryEvent
from epos.npc_agent_models import NpcAgentState
from epos.npc_agent_persistence import load_npc_agent_registry, registry_payload_from_legacy, save_npc_agent_registry
from epos.npc_agent_registry import NpcAgentRegistry
from epos.npc_memory_policy import NpcShortMemoryPolicy
from epos.npc_memory_short import (
    NpcShortMemory,
    build_short_memories_from_event,
    dedupe_short_memories,
    deterministic_memory_id,
    effective_importance,
    prune_short_memories,
)
from epos.worldpack import load_pack

PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


def _world():
    pack = load_pack(PACK)
    state = pack.new_world("short-memory")
    return pack, state


def _memory(**overrides):
    data = {
        "memory_id": "mem_maera_1",
        "npc_id": "maera",
        "turn": 2,
        "memory_type": "observed_action",
        "summary": "Maera saw the player open the locked door.",
        "source_event_id": "event_2_1",
        "importance": 0.6,
        "observed": True,
        "tags": ("door", "door", "observed"),
        "active": True,
    }
    data.update(overrides)
    return NpcShortMemory(**data)


def test_short_memory_minimal_complete_roundtrip_and_immutability():
    minimal = NpcShortMemory(
        memory_id="mem_maera_min",
        npc_id="maera",
        turn=0,
        memory_type="observed_action",
        summary="Maera saw the player arrive.",
    )
    complete = _memory()

    assert minimal.importance == 0.5
    assert minimal.observed is True
    assert complete.tags == ("door", "observed")
    assert NpcShortMemory.from_dict(complete.to_dict()) == complete
    with pytest.raises(FrozenInstanceError):
        complete.summary = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("memory_id", ""),
        ("npc_id", "Maera Dolk"),
        ("turn", -1),
        ("importance", -0.1),
        ("importance", 1.1),
        ("memory_type", "long_memory"),
    ],
)
def test_short_memory_validation(field, value):
    with pytest.raises(ValueError):
        _memory(**{field: value})


def test_short_memory_policy_defaults_invalid_values_and_roundtrip():
    policy = NpcShortMemoryPolicy()

    assert policy.max_entries_per_npc == 10
    assert policy.minimum_importance == 0.10
    assert policy.decay_per_turn == 0.02
    assert NpcShortMemoryPolicy.from_dict(policy.to_dict()) == policy
    with pytest.raises(ValueError):
        NpcShortMemoryPolicy(max_entries_per_npc=-1)
    with pytest.raises(ValueError):
        NpcShortMemoryPolicy(minimum_importance=1.1)
    with pytest.raises(ValueError):
        NpcShortMemoryPolicy(decay_per_turn=-0.01)


def test_decay_zero_positive_retention_max_entries_and_stable_tiebreak():
    policy = NpcShortMemoryPolicy(max_entries_per_npc=2, minimum_importance=0.2, decay_per_turn=0.1)
    old = _memory(memory_id="mem_old", source_event_id="old", turn=1, importance=0.4)
    recent = _memory(memory_id="mem_recent", source_event_id="recent", turn=4, importance=0.5)
    retained = _memory(
        memory_id="mem_thread",
        source_event_id="thread",
        turn=1,
        memory_type="thread_update",
        importance=0.1,
    )
    tie_a = _memory(memory_id="mem_a", source_event_id="a", turn=5, importance=0.5)
    tie_b = _memory(memory_id="mem_b", source_event_id="b", turn=5, importance=0.5)

    assert effective_importance(old, 3, NpcShortMemoryPolicy(decay_per_turn=0.0)) == 0.4
    assert effective_importance(old, 3, policy) == pytest.approx(0.2)
    assert effective_importance(retained, 99, policy) == pytest.approx(0.2)
    assert prune_short_memories((old, recent, retained, tie_b, tie_a), current_turn=5, policy=policy) == (
        tie_a,
        tie_b,
    )


def test_dedupe_prefers_same_source_type_by_importance_then_turn():
    first = _memory(memory_id="mem_first", source_event_id="event_x", importance=0.4, turn=2)
    better = _memory(memory_id="mem_better", source_event_id="event_x", importance=0.8, turn=1)
    newer = _memory(memory_id="mem_newer", source_event_id="event_y", importance=0.6, turn=5)
    duplicate_newer = _memory(memory_id="mem_duplicate_newer", source_event_id="event_y", importance=0.6, turn=6)

    assert dedupe_short_memories((first, better, newer, duplicate_newer)) == (
        better,
        duplicate_newer,
    )


def test_build_memories_from_observed_event_filters_absent_and_preserves_inputs():
    _pack, state = _world()
    state.npcs["corren"].present = False
    event = MemoryEvent(
        summary="The stranger asked about the closed road.",
        witnesses=["maera", "corren"],
        source="observed",
        turn=3,
        emotional_impact=2,
        public=True,
    )
    before_state = state.to_dict()
    before_event = event.to_dict()

    memories = build_short_memories_from_event(
        event,
        tuple(event.witnesses),
        3,
        state,
        source_event_id="event_3_1",
        tags=("question", "question"),
    )

    assert tuple(memory.npc_id for memory in memories) == ("maera",)
    assert memories[0].summary == event.summary
    assert memories[0].source_event_id == "event_3_1"
    assert memories[0].importance == pytest.approx(0.7)
    assert memories[0].tags == ("question",)
    assert state.to_dict() == before_state
    assert event.to_dict() == before_event


def test_build_memories_for_multiple_observers_order_and_no_observers():
    _pack, state = _world()
    state.npcs["corren"].present = True
    event = MemoryEvent(
        summary="Both NPCs heard the warning.",
        witnesses=["corren", "maera"],
        source="observed",
        turn=4,
    )

    memories = build_short_memories_from_event(event, ("corren", "maera", "corren"), 4, state, source_event_id="event_4_1")

    assert tuple(memory.npc_id for memory in memories) == ("corren", "maera")
    assert build_short_memories_from_event(event, (), 4, state, source_event_id="event_4_1") == ()


def test_memory_ids_are_deterministic_without_llm_or_fuzzy_matching():
    first = deterministic_memory_id("maera", "event_1", "observed_action", 1, "Saw a thing.")
    second = deterministic_memory_id("maera", "event_1", "observed_action", 1, "Saw a thing.")
    different = deterministic_memory_id("maera", "event_2", "observed_action", 1, "Saw a thing.")

    assert first == second
    assert first != different


def test_registry_memory_update_isolated_deduped_removable_and_phase6_compatible():
    maera = NpcAgentState(npc_id="maera")
    corren = NpcAgentState(npc_id="corren")
    registry = NpcAgentRegistry((maera, corren))
    memory = _memory()
    duplicate = _memory(memory_id="mem_maera_2", importance=0.9)

    updated = registry.upsert_short_memory(memory, current_turn=2)
    updated = updated.upsert_short_memory(duplicate, current_turn=2)

    assert registry.get("maera").short_memories == ()
    assert updated.get("maera").short_memories == (duplicate,)
    assert updated.get("corren").short_memories == ()
    assert NpcAgentState.from_dict(updated.get("maera").to_dict()) == updated.get("maera")
    removed = updated.remove_short_memory("maera", duplicate.memory_id)
    assert removed.get("maera").short_memories == ()
    with pytest.raises(ValueError):
        updated.upsert_short_memory(_memory(npc_id="ghost"), current_turn=2)


def test_observed_false_and_inactive_memories_are_excluded_from_retention():
    policy = NpcShortMemoryPolicy(max_entries_per_npc=10, minimum_importance=0.1, decay_per_turn=0.0)
    observed_false = _memory(memory_id="mem_false", source_event_id="false", observed=False)
    inactive = _memory(memory_id="mem_inactive", source_event_id="inactive", active=False)
    valid = _memory(memory_id="mem_valid", source_event_id="valid")

    assert prune_short_memories((observed_false, inactive, valid), current_turn=2, policy=policy) == (valid,)


def test_companion_persistence_legacy_missing_roundtrip_and_invalid_data(tmp_path):
    registry = NpcAgentRegistry((NpcAgentState(npc_id="maera", short_memories=(_memory(),)),))

    assert load_npc_agent_registry(tmp_path, "legacy").all() == ()
    assert registry_payload_from_legacy({}).all() == ()
    path = save_npc_agent_registry(tmp_path, "session", registry)
    assert path.name == "npc_agents.json"
    assert load_npc_agent_registry(tmp_path, "session") == registry
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_npc_agent_registry(tmp_path, "session")
