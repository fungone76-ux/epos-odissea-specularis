"""Canonical long-memory structures for deterministic NPC agents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any

from .npc_agent_models import validate_canonical_npc_id
from .npc_memory_long_policy import LONG_MEMORY_TYPES, NpcLongMemoryPolicy

LONG_MEMORY_STATUSES = ("active", "resolved", "inactive")


@dataclass(frozen=True)
class NpcLongMemory:
    memory_id: str
    npc_id: str
    memory_type: str
    summary: str
    source_event_id: str
    source_short_memory_id: str
    created_turn: int
    last_reinforced_turn: int
    importance: float
    tags: tuple[str, ...] = ()
    status: str = "active"
    active: bool = True

    def __post_init__(self) -> None:
        memory_id = str(self.memory_id or "").strip()
        if not memory_id:
            raise ValueError("memory_id must not be empty")
        object.__setattr__(self, "memory_id", memory_id)
        object.__setattr__(self, "npc_id", validate_canonical_npc_id(self.npc_id))
        memory_type = str(self.memory_type or "").strip()
        if memory_type not in LONG_MEMORY_TYPES:
            raise ValueError(f"unsupported long memory type: {memory_type!r}")
        object.__setattr__(self, "memory_type", memory_type)
        summary = str(self.summary or "").strip()
        if not summary:
            raise ValueError("summary must not be empty")
        object.__setattr__(self, "summary", summary)
        source_event_id = str(self.source_event_id or "").strip()
        if not source_event_id:
            raise ValueError("source_event_id must not be empty")
        object.__setattr__(self, "source_event_id", source_event_id)
        source_short_memory_id = str(self.source_short_memory_id or "").strip()
        if not source_short_memory_id:
            raise ValueError("source_short_memory_id must not be empty")
        object.__setattr__(self, "source_short_memory_id", source_short_memory_id)
        created_turn = int(self.created_turn)
        if created_turn < 0:
            raise ValueError("created_turn must be non-negative")
        object.__setattr__(self, "created_turn", created_turn)
        reinforced_turn = int(self.last_reinforced_turn)
        if reinforced_turn < created_turn:
            raise ValueError("last_reinforced_turn must be >= created_turn")
        object.__setattr__(self, "last_reinforced_turn", reinforced_turn)
        importance = float(self.importance)
        if importance < 0.0 or importance > 1.0:
            raise ValueError("importance must be between 0.0 and 1.0")
        object.__setattr__(self, "importance", importance)
        object.__setattr__(self, "tags", _unique_tags(self.tags))
        status = str(self.status or "").strip()
        if status not in LONG_MEMORY_STATUSES:
            raise ValueError(f"unsupported long memory status: {status!r}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "active", bool(self.active))

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "npc_id": self.npc_id,
            "memory_type": self.memory_type,
            "summary": self.summary,
            "source_event_id": self.source_event_id,
            "source_short_memory_id": self.source_short_memory_id,
            "created_turn": self.created_turn,
            "last_reinforced_turn": self.last_reinforced_turn,
            "importance": self.importance,
            "tags": list(self.tags),
            "status": self.status,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NpcLongMemory":
        return cls(
            memory_id=data.get("memory_id", ""),
            npc_id=data.get("npc_id", ""),
            memory_type=data.get("memory_type", ""),
            summary=data.get("summary", ""),
            source_event_id=data.get("source_event_id", ""),
            source_short_memory_id=data.get("source_short_memory_id", ""),
            created_turn=int(data.get("created_turn", 0)),
            last_reinforced_turn=int(data.get("last_reinforced_turn", data.get("created_turn", 0))),
            importance=float(data.get("importance", 0.0)),
            tags=tuple(data.get("tags", ())),
            status=data.get("status", "active"),
            active=bool(data.get("active", True)),
        )


def deterministic_long_memory_id(npc_id: str, source_event_id: str, memory_type: str, source_short_memory_id: str) -> str:
    canonical = validate_canonical_npc_id(npc_id)
    base = f"{canonical}|{str(source_event_id or '').strip()}|{memory_type}|{str(source_short_memory_id or '').strip()}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"long_{canonical}_{digest}"


def reinforce_long_memory(existing: NpcLongMemory, incoming: NpcLongMemory, current_turn: int) -> NpcLongMemory:
    if existing.npc_id != incoming.npc_id:
        raise ValueError("cannot reinforce memory across different NPCs")
    return replace(
        existing,
        last_reinforced_turn=max(existing.last_reinforced_turn, incoming.last_reinforced_turn, int(current_turn)),
        importance=max(existing.importance, incoming.importance),
        tags=_merge_tags(existing.tags, incoming.tags),
        active=existing.active or incoming.active,
        status="active" if existing.status == "active" or incoming.status == "active" else existing.status,
    )


def dedupe_long_memories(
    memories: tuple[NpcLongMemory, ...],
    *,
    current_turn: int,
    reinforce_existing: bool = True,
) -> tuple[NpcLongMemory, ...]:
    result: list[NpcLongMemory] = []
    for memory in memories:
        duplicate_index = _duplicate_index(result, memory)
        if duplicate_index is None:
            result.append(memory)
            continue
        existing = result[duplicate_index]
        if reinforce_existing:
            result[duplicate_index] = reinforce_long_memory(existing, memory, current_turn)
        elif _prefer_long_memory(memory, existing):
            result[duplicate_index] = memory
    return tuple(result)


def prune_long_memories(
    memories: tuple[NpcLongMemory, ...],
    *,
    policy: NpcLongMemoryPolicy,
    current_turn: int,
) -> tuple[NpcLongMemory, ...]:
    deduped = dedupe_long_memories(
        memories,
        current_turn=current_turn,
        reinforce_existing=policy.reinforce_existing,
    )
    active = [memory for memory in deduped if memory.active]
    protected = [memory for memory in active if _protected(memory, policy)]
    ordinary = [memory for memory in active if memory not in protected]
    ranked = sorted(
        ordinary,
        key=lambda memory: (
            -memory.importance,
            -memory.last_reinforced_turn,
            memory.memory_id,
        ),
    )
    slots = max(0, policy.max_entries_per_npc - len(protected))
    return tuple(protected + ranked[:slots])


def deactivate_long_memory(memory: NpcLongMemory, *, status: str = "inactive") -> NpcLongMemory:
    return replace(memory, status=status, active=False)



def _duplicate_index(memories: list[NpcLongMemory], candidate: NpcLongMemory) -> int | None:
    for index, memory in enumerate(memories):
        if memory.memory_id == candidate.memory_id:
            return index
    for index, memory in enumerate(memories):
        if (
            memory.npc_id == candidate.npc_id
            and memory.source_event_id == candidate.source_event_id
            and memory.memory_type == candidate.memory_type
        ):
            return index
    for index, memory in enumerate(memories):
        if memory.source_short_memory_id == candidate.source_short_memory_id:
            return index
    return None

def _unique_tags(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value or "").strip()
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return tuple(result)


def _merge_tags(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    return _unique_tags(tuple(first) + tuple(second))


def _dedupe_key(memory: NpcLongMemory) -> tuple[str, str, str] | tuple[str, str]:
    if memory.source_event_id:
        return memory.npc_id, memory.source_event_id, memory.memory_type
    return memory.npc_id, memory.source_short_memory_id


def _prefer_long_memory(candidate: NpcLongMemory, existing: NpcLongMemory) -> bool:
    return (
        candidate.importance,
        candidate.last_reinforced_turn,
        candidate.memory_id,
    ) > (
        existing.importance,
        existing.last_reinforced_turn,
        existing.memory_id,
    )


def _protected(memory: NpcLongMemory, policy: NpcLongMemoryPolicy) -> bool:
    return policy.preserve_open_promises and memory.memory_type in {"promise", "betrayal", "secret"}
