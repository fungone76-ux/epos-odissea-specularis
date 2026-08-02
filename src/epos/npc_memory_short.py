"""Canonical short-memory structures for deterministic NPC agents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .models import MemoryEvent, WorldState
from .npc_agent_models import validate_canonical_npc_id
from .npc_memory_policy import NpcShortMemoryPolicy

SHORT_MEMORY_TYPES = (
    "observed_action",
    "dialogue",
    "relationship_change",
    "outfit_change",
    "presence_change",
    "mission_event",
    "thread_update",
    "emotional_reaction",
)
_MIN_IMPORTANCE = 0.0
_MAX_IMPORTANCE = 1.0


@dataclass(frozen=True)
class NpcShortMemory:
    memory_id: str
    npc_id: str
    turn: int
    memory_type: str
    summary: str
    source_event_id: str = ""
    importance: float = 0.5
    observed: bool = True
    tags: tuple[str, ...] = ()
    active: bool = True

    def __post_init__(self) -> None:
        memory_id = str(self.memory_id or "").strip()
        if not memory_id:
            raise ValueError("memory_id must not be empty")
        object.__setattr__(self, "memory_id", memory_id)
        object.__setattr__(self, "npc_id", validate_canonical_npc_id(self.npc_id))
        turn = int(self.turn)
        if turn < 0:
            raise ValueError("turn must be non-negative")
        object.__setattr__(self, "turn", turn)
        memory_type = str(self.memory_type or "").strip()
        if memory_type not in SHORT_MEMORY_TYPES:
            raise ValueError(f"unsupported short memory type: {memory_type!r}")
        object.__setattr__(self, "memory_type", memory_type)
        summary = str(self.summary or "").strip()
        if not summary:
            raise ValueError("summary must not be empty")
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "source_event_id", str(self.source_event_id or "").strip())
        importance = float(self.importance)
        if importance < _MIN_IMPORTANCE or importance > _MAX_IMPORTANCE:
            raise ValueError("importance must be between 0.0 and 1.0")
        object.__setattr__(self, "importance", importance)
        object.__setattr__(self, "observed", bool(self.observed))
        object.__setattr__(self, "tags", _unique_tags(self.tags))
        object.__setattr__(self, "active", bool(self.active))

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "npc_id": self.npc_id,
            "turn": self.turn,
            "memory_type": self.memory_type,
            "summary": self.summary,
            "source_event_id": self.source_event_id,
            "importance": self.importance,
            "observed": self.observed,
            "tags": list(self.tags),
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NpcShortMemory":
        return cls(
            memory_id=data.get("memory_id", ""),
            npc_id=data.get("npc_id", ""),
            turn=int(data.get("turn", 0)),
            memory_type=data.get("memory_type", "observed_action"),
            summary=data.get("summary", ""),
            source_event_id=data.get("source_event_id", ""),
            importance=float(data.get("importance", 0.5)),
            observed=bool(data.get("observed", True)),
            tags=tuple(data.get("tags", ())),
            active=bool(data.get("active", True)),
        )


def deterministic_memory_id(npc_id: str, source_event_id: str, memory_type: str, turn: int, summary: str) -> str:
    canonical = validate_canonical_npc_id(npc_id)
    source = str(source_event_id or "").strip()
    base = f"{canonical}|{source}|{memory_type}|{int(turn)}|{str(summary or '').strip()}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"short_{canonical}_{digest}"


def build_short_memories_from_event(
    event: MemoryEvent,
    observer_npc_ids: tuple[str, ...],
    turn: int,
    world_state: WorldState,
    *,
    source_event_id: str = "",
    memory_type: str = "observed_action",
    importance: float | None = None,
    tags: tuple[str, ...] = (),
) -> tuple[NpcShortMemory, ...]:
    summary = str(event.summary or "").strip()
    if not summary:
        return ()
    source_id = str(source_event_id or event.source or "").strip()
    observer_ids = _stable_observers(observer_npc_ids, world_state)
    if importance is None:
        importance = _importance_from_event(event)
    memories: list[NpcShortMemory] = []
    for npc_id in observer_ids:
        memory_id = deterministic_memory_id(npc_id, source_id, memory_type, int(turn), summary)
        memories.append(
            NpcShortMemory(
                memory_id=memory_id,
                npc_id=npc_id,
                turn=int(turn),
                memory_type=memory_type,
                summary=summary,
                source_event_id=source_id,
                importance=importance,
                observed=True,
                tags=tags,
            )
        )
    return tuple(memories)


def effective_importance(memory: NpcShortMemory, current_turn: int, policy: NpcShortMemoryPolicy) -> float:
    elapsed = max(0, int(current_turn) - memory.turn)
    retained_floor = policy.minimum_importance if _retained_by_type(memory, policy) else 0.0
    return max(retained_floor, max(0.0, memory.importance - policy.decay_per_turn * elapsed))


def dedupe_short_memories(memories: tuple[NpcShortMemory, ...]) -> tuple[NpcShortMemory, ...]:
    by_key: dict[tuple[str, str, str] | tuple[str, str], NpcShortMemory] = {}
    order: list[tuple[str, str, str] | tuple[str, str]] = []
    for memory in memories:
        key = _dedupe_key(memory)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = memory
            order.append(key)
            continue
        if _prefer_memory(memory, existing):
            by_key[key] = memory
    return tuple(by_key[key] for key in order)


def prune_short_memories(
    memories: tuple[NpcShortMemory, ...],
    *,
    current_turn: int,
    policy: NpcShortMemoryPolicy,
) -> tuple[NpcShortMemory, ...]:
    deduped = dedupe_short_memories(memories)
    active = [
        memory
        for memory in deduped
        if memory.active
        and memory.observed
        and effective_importance(memory, current_turn, policy) >= policy.minimum_importance
    ]
    ranked = sorted(
        active,
        key=lambda memory: (
            -effective_importance(memory, current_turn, policy),
            -memory.turn,
            memory.memory_id,
        ),
    )
    kept = ranked[: policy.max_entries_per_npc]
    return tuple(sorted(kept, key=lambda memory: (memory.turn, memory.memory_id)))


def _unique_tags(values: tuple[str, ...]) -> tuple[str, ...]:
    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value or "").strip()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tuple(tags)


def _stable_observers(observer_npc_ids: tuple[str, ...], world_state: WorldState) -> tuple[str, ...]:
    requested = []
    seen: set[str] = set()
    for observer in observer_npc_ids:
        npc_id = str(observer or "").strip()
        if npc_id and npc_id not in seen:
            seen.add(npc_id)
            requested.append(npc_id)
    present = set(world_state.present_npc_ids())
    return tuple(npc_id for npc_id in requested if npc_id in world_state.npcs and npc_id in present)


def _importance_from_event(event: MemoryEvent) -> float:
    return min(1.0, max(0.1, 0.5 + abs(int(event.emotional_impact)) * 0.1))


def _dedupe_key(memory: NpcShortMemory) -> tuple[str, str, str] | tuple[str, str]:
    if memory.source_event_id:
        return memory.npc_id, memory.source_event_id, memory.memory_type
    return memory.npc_id, memory.memory_id


def _prefer_memory(candidate: NpcShortMemory, existing: NpcShortMemory) -> bool:
    return (
        candidate.importance,
        candidate.turn,
        candidate.memory_id,
    ) > (
        existing.importance,
        existing.turn,
        existing.memory_id,
    )


def _retained_by_type(memory: NpcShortMemory, policy: NpcShortMemoryPolicy) -> bool:
    return (
        policy.retain_open_threads and memory.memory_type == "thread_update"
    ) or (
        policy.retain_promises and "promise" in memory.tags
    )
