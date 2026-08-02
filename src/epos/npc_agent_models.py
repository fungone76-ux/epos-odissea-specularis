"""Deterministic NPC agent state contracts.

These structures are data-only. They do not run agents, call providers, or
own canonical relationship, knowledge, thread, or mission content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_NPC_ID_RE = re.compile(r"[a-z0-9][a-z0-9_:-]*")
_MIN_PRIORITY = 0
_MAX_PRIORITY = 100


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_refs(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        iterable = (values,)
    else:
        iterable = values
    refs: list[str] = []
    seen: set[str] = set()
    for value in iterable:
        ref = _clean_text(value)
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return tuple(refs)


def validate_canonical_npc_id(npc_id: Any) -> str:
    """Validate the machine-facing NPC id shape used by world state keys."""

    cleaned = _clean_text(npc_id)
    if not cleaned:
        raise ValueError("npc_id must not be empty")
    if not _NPC_ID_RE.fullmatch(cleaned):
        raise ValueError(f"npc_id must be canonical machine-facing id: {cleaned!r}")
    return cleaned


@dataclass(frozen=True)
class NpcAgentState:
    npc_id: str
    persona_summary: str = ""
    current_goal: str = ""
    current_intention: str = ""
    emotion: str = ""
    relationship_refs: tuple[str, ...] = ()
    knowledge_refs: tuple[str, ...] = ()
    open_thread_ids: tuple[str, ...] = ()
    mission_refs: tuple[str, ...] = ()
    short_memories: tuple[Any, ...] = ()
    long_memories: tuple[Any, ...] = ()
    initiative_priority: int = 0
    next_evaluation_turn: int = 0
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "npc_id", validate_canonical_npc_id(self.npc_id))
        object.__setattr__(self, "persona_summary", _clean_text(self.persona_summary))
        object.__setattr__(self, "current_goal", _clean_text(self.current_goal))
        object.__setattr__(self, "current_intention", _clean_text(self.current_intention))
        object.__setattr__(self, "emotion", _clean_text(self.emotion))
        object.__setattr__(self, "relationship_refs", _unique_refs(self.relationship_refs))
        object.__setattr__(self, "knowledge_refs", _unique_refs(self.knowledge_refs))
        object.__setattr__(self, "open_thread_ids", _unique_refs(self.open_thread_ids))
        object.__setattr__(self, "mission_refs", _unique_refs(self.mission_refs))
        object.__setattr__(self, "short_memories", _short_memories(self.short_memories))
        object.__setattr__(self, "long_memories", _long_memories(self.long_memories))
        priority = int(self.initiative_priority)
        if priority < _MIN_PRIORITY or priority > _MAX_PRIORITY:
            raise ValueError("initiative_priority must be between 0 and 100")
        object.__setattr__(self, "initiative_priority", priority)
        next_turn = int(self.next_evaluation_turn)
        if next_turn < 0:
            raise ValueError("next_evaluation_turn must be non-negative")
        object.__setattr__(self, "next_evaluation_turn", next_turn)
        object.__setattr__(self, "enabled", bool(self.enabled))

    def to_dict(self) -> dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "persona_summary": self.persona_summary,
            "current_goal": self.current_goal,
            "current_intention": self.current_intention,
            "emotion": self.emotion,
            "relationship_refs": list(self.relationship_refs),
            "knowledge_refs": list(self.knowledge_refs),
            "open_thread_ids": list(self.open_thread_ids),
            "mission_refs": list(self.mission_refs),
            "short_memories": [
                memory.to_dict() if hasattr(memory, "to_dict") else dict(memory)
                for memory in self.short_memories
            ],
            "long_memories": [
                memory.to_dict() if hasattr(memory, "to_dict") else dict(memory)
                for memory in self.long_memories
            ],
            "initiative_priority": self.initiative_priority,
            "next_evaluation_turn": self.next_evaluation_turn,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NpcAgentState":
        return cls(
            npc_id=data.get("npc_id", ""),
            persona_summary=data.get("persona_summary", ""),
            current_goal=data.get("current_goal", ""),
            current_intention=data.get("current_intention", ""),
            emotion=data.get("emotion", ""),
            relationship_refs=tuple(data.get("relationship_refs", ())),
            knowledge_refs=tuple(data.get("knowledge_refs", ())),
            open_thread_ids=tuple(data.get("open_thread_ids", ())),
            mission_refs=tuple(data.get("mission_refs", ())),
            short_memories=tuple(data.get("short_memories", ())),
            long_memories=tuple(data.get("long_memories", ())),
            initiative_priority=int(data.get("initiative_priority", 0)),
            next_evaluation_turn=int(data.get("next_evaluation_turn", 0)),
            enabled=bool(data.get("enabled", True)),
        )


def _short_memories(values: Any) -> tuple[Any, ...]:
    if values is None:
        return ()
    result: list[Any] = []
    for value in values:
        if hasattr(value, "to_dict"):
            result.append(value)
        elif isinstance(value, dict):
            from .npc_memory_short import NpcShortMemory

            result.append(NpcShortMemory.from_dict(value))
        else:
            raise ValueError("short_memories must contain memory objects or dictionaries")
    return tuple(result)


def _long_memories(values: Any) -> tuple[Any, ...]:
    if values is None:
        return ()
    result: list[Any] = []
    for value in values:
        if hasattr(value, "to_dict"):
            result.append(value)
        elif isinstance(value, dict):
            from .npc_memory_long import NpcLongMemory

            result.append(NpcLongMemory.from_dict(value))
        else:
            raise ValueError("long_memories must contain memory objects or dictionaries")
    return tuple(result)
