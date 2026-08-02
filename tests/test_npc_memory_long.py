from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from epos.models import MemoryEvent
from epos.npc_agent_models import NpcAgentState
from epos.npc_agent_persistence import load_npc_agent_registry, save_npc_agent_registry
from epos.npc_agent_registry import NpcAgentRegistry
from epos.npc_memory_long import (
    NpcLongMemory,
    deactivate_long_memory,
    dedupe_long_memories,
    deterministic_long_memory_id,
    prune_long_memories,
    reinforce_long_memory,
)
from epos.npc_memory_long_policy import NpcLongMemoryPolicy
from epos.npc_memory_promotion import promote_short_memory
from epos.npc_memory_short import NpcShortMemory, build_short_memories_from_event
from epos.worldpack import load_pack

PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


def _short(**overrides):
    data = {
        "memory_id": "short_maera_1",
        "npc_id": "maera",
        "turn": 4,
        "memory_type": "relationship_change",
        "summary": "Maera saw the player keep a difficult promise.",
        "source_event_id": "event_4_1",
        "importance": 0.8,
        "observed": True,
        "tags": ("promise", "trust"),
        "active": True,
    }
    data.update(overrides)
    return NpcShortMemory(**data)


def _long(**overrides):
    data = {
        "memory_id": "long_maera_1",
        "npc_id": "maera",
        "memory_type": "promise",
        "summary": "Maera saw the player keep a difficult promise.",
        "source_event_id": "event_4_1",
        "source_short_memory_id": "short_maera_1",
        "created_turn": 4,
        "last_reinforced_turn": 4,
        "importance": 0.8,
        "tags": ("promise", "promise", "trust"),
        "status": "active",
        "active": True,
    }
    data.update(overrides)
    return NpcLongMemory(**data)


def test_long_memory_minimal_complete_roundtrip_and_immutability():
    minimal = _long(tags=())
    complete = _long()

    assert minimal.memory_type == "promise"
    assert complete.tags == ("promise", "trust")
    assert NpcLongMemory.from_dict(complete.to_dict()) == complete
    with pytest.raises(FrozenInstanceError):
        complete.summary = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("memory_id", ""),
        ("npc_id", "Maera Dolk"),
        ("created_turn", -1),
        ("last_reinforced_turn", 3),
        ("importance", -0.1),
        ("importance", 1.1),
        ("source_short_memory_id", ""),
        ("source_event_id", ""),
        ("status", "archived"),
        ("memory_type", "unsupported"),
    ],
)
def test_long_memory_validation(field, value):
    with pytest.raises(ValueError):
        _long(**{field: value})


def test_long_memory_policy_defaults_invalid_values_and_roundtrip():
    policy = NpcLongMemoryPolicy()

    assert policy.minimum_importance == 0.75
    assert policy.max_entries_per_npc == 30
    assert "promise" in policy.promote_types
    assert NpcLongMemoryPolicy.from_dict(policy.to_dict()) == policy
    with pytest.raises(ValueError):
        NpcLongMemoryPolicy(minimum_importance=1.1)
    with pytest.raises(ValueError):
        NpcLongMemoryPolicy(max_entries_per_npc=-1)
    with pytest.raises(ValueError):
        NpcLongMemoryPolicy(promote_types=("not_real",))


def test_promotion_accepts_observed_promotable_short_memory_deterministically():
    short = _short()
    policy = NpcLongMemoryPolicy()

    first = promote_short_memory(short, policy=policy, current_turn=5)
    second = promote_short_memory(short, policy=policy, current_turn=5)

    assert first == second
    assert first.rejected_reason == ""
    assert first.promoted is not None
    assert first.promoted.memory_id == deterministic_long_memory_id("maera", "event_4_1", "promise", "short_maera_1")
    assert first.promoted.source_event_id == short.source_event_id
    assert first.promoted.source_short_memory_id == short.memory_id
    assert first.promoted.summary == short.summary


@pytest.mark.parametrize(
    ("short_memory", "reason"),
    [
        (_short(observed=False), "short_memory_not_observed"),
        (_short(active=False), "short_memory_inactive"),
        (_short(source_event_id=""), "missing_source_event_id"),
        (_short(importance=0.2), "importance_below_threshold"),
        (_short(memory_type="dialogue", tags=()), "type_not_promotable"),
        (_short(tags=("promise",)), "type_disabled_by_policy"),
    ],
)
def test_promotion_rejections_are_deterministic(short_memory, reason):
    policy = NpcLongMemoryPolicy(promote_types=("trust_event",)) if reason == "type_disabled_by_policy" else NpcLongMemoryPolicy()

    result = promote_short_memory(short_memory, policy=policy, current_turn=5)

    assert result.promoted is None
    assert result.reinforced is None
    assert result.rejected_reason == reason


def test_promotion_maps_supported_tags_and_short_types_only():
    assert promote_short_memory(_short(tags=("betrayal",)), policy=NpcLongMemoryPolicy(), current_turn=5).promoted.memory_type == "betrayal"
    assert promote_short_memory(_short(tags=(), memory_type="mission_event"), policy=NpcLongMemoryPolicy(), current_turn=5).promoted.memory_type == "mission_event"
    assert promote_short_memory(_short(tags=(), memory_type="relationship_change"), policy=NpcLongMemoryPolicy(), current_turn=5).promoted.memory_type == "relationship_milestone"


def test_reinforcement_preserves_memory_id_provenance_and_unions_tags():
    existing = _long(memory_id="long_original", importance=0.7, tags=("promise",))
    incoming = _long(memory_id="long_incoming", importance=0.9, tags=("trust", "promise"), last_reinforced_turn=8)

    reinforced = reinforce_long_memory(existing, incoming, current_turn=9)

    assert reinforced.memory_id == "long_original"
    assert reinforced.source_event_id == existing.source_event_id
    assert reinforced.source_short_memory_id == existing.source_short_memory_id
    assert reinforced.last_reinforced_turn == 9
    assert reinforced.importance == 0.9
    assert reinforced.tags == ("promise", "trust")


def test_dedupe_by_memory_id_source_event_and_short_source_without_fuzzy_matching():
    first = _long(memory_id="same", source_event_id="event_a", source_short_memory_id="short_a", importance=0.7)
    better_same_id = _long(memory_id="same", source_event_id="event_b", source_short_memory_id="short_b", importance=0.9)
    same_source = _long(memory_id="other", source_event_id="event_a", source_short_memory_id="short_c", importance=0.8)
    different = _long(memory_id="different", source_event_id="event_z", source_short_memory_id="short_z")

    deduped = dedupe_long_memories((first, better_same_id, same_source, different), current_turn=10)

    assert deduped[0].memory_id == "same"
    assert deduped[0].source_event_id == "event_a"
    assert deduped[0].importance == 0.9
    assert deduped[0].last_reinforced_turn == 10
    assert len(deduped) == 2
    assert deduped[1] == different


def test_retention_excludes_inactive_preserves_promises_and_applies_limit():
    policy = NpcLongMemoryPolicy(max_entries_per_npc=2)
    inactive = _long(memory_id="inactive", source_event_id="inactive", source_short_memory_id="inactive", active=False)
    promise = _long(memory_id="promise", source_event_id="promise", source_short_memory_id="promise", importance=0.1, memory_type="promise")
    high = _long(memory_id="high", source_event_id="high", source_short_memory_id="high", importance=0.9, memory_type="mission_event")
    low = _long(memory_id="low", source_event_id="low", source_short_memory_id="low", importance=0.2, memory_type="mission_event")

    assert deactivate_long_memory(promise, status="resolved").active is False
    assert prune_long_memories((inactive, low, high, promise), policy=policy, current_turn=10) == (
        promise,
        high,
    )


def test_registry_long_memory_update_isolated_promote_remove_and_phase7_compatible():
    registry = NpcAgentRegistry((NpcAgentState(npc_id="maera", short_memories=(_short(),)), NpcAgentState(npc_id="corren")))

    updated, result = registry.promote_short_memory_for_npc("maera", _short(), current_turn=6)

    assert result.promoted is not None
    assert registry.get("maera").long_memories == ()
    assert updated.get("maera").long_memories == (result.promoted,)
    assert updated.get("corren").long_memories == ()
    assert updated.get_long_memory("maera", result.promoted.memory_id) == result.promoted
    removed = updated.remove_long_memory("maera", result.promoted.memory_id)
    assert removed.get("maera").long_memories == ()
    assert removed.get("maera").short_memories == (_short(),)
    with pytest.raises(ValueError):
        updated.promote_short_memory_for_npc("corren", _short(npc_id="maera"), current_turn=6)


def test_long_memory_isolation_and_world_state_not_mutated_from_observed_short_memory():
    pack = load_pack(PACK)
    state = pack.new_world("long-memory")
    state.npcs["corren"].present = True
    event = MemoryEvent(summary="A promise was witnessed.", witnesses=["maera", "corren"], source="observed", turn=2)
    before_state = state.to_dict()
    short_memories = build_short_memories_from_event(
        event,
        ("maera", "corren"),
        2,
        state,
        source_event_id="event_2_1",
        tags=("promise",),
        importance=0.9,
    )
    registry = NpcAgentRegistry((NpcAgentState(npc_id="maera"), NpcAgentState(npc_id="corren")))
    for short in short_memories:
        registry, _result = registry.promote_short_memory_for_npc(short.npc_id, short, current_turn=3)

    assert tuple(memory.npc_id for memory in registry.get("maera").long_memories) == ("maera",)
    assert tuple(memory.npc_id for memory in registry.get("corren").long_memories) == ("corren",)
    assert state.to_dict() == before_state
    assert short_memories[0].summary == "A promise was witnessed."


def test_companion_persistence_loads_phase7_payload_and_roundtrips_long_memories(tmp_path):
    phase7_registry = NpcAgentRegistry((NpcAgentState(npc_id="maera", short_memories=(_short(),)),))
    save_npc_agent_registry(tmp_path, "phase7", phase7_registry)
    assert load_npc_agent_registry(tmp_path, "phase7") == phase7_registry

    long_memory = _long()
    registry = NpcAgentRegistry((NpcAgentState(npc_id="maera", short_memories=(_short(),), long_memories=(long_memory,)),))
    path = save_npc_agent_registry(tmp_path, "phase8", registry)

    assert path.name == "npc_agents.json"
    assert load_npc_agent_registry(tmp_path, "phase8") == registry
    assert not (tmp_path / "phase8" / "state.json").exists()
    assert not (tmp_path / "phase8" / "checkpoint.json").exists()
    assert load_npc_agent_registry(tmp_path, "missing").all() == ()
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_npc_agent_registry(tmp_path, "phase8")
