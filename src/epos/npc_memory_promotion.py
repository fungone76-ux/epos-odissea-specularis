"""Deterministic promotion from observed short memory to long memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .npc_memory_long import NpcLongMemory, deterministic_long_memory_id, reinforce_long_memory
from .npc_memory_long_policy import NpcLongMemoryPolicy
from .npc_memory_short import NpcShortMemory

_TAG_TO_LONG_TYPE = {
    "promise": "promise",
    "betrayal": "betrayal",
    "trust": "trust_event",
    "fear": "fear_event",
    "secret": "secret",
    "debt": "debt",
    "trauma": "trauma",
    "major_decision": "major_decision",
    "preference": "preference",
    "threat": "long_term_threat",
    "unresolved_request": "unresolved_request",
    "request": "unresolved_request",
}

_SHORT_TYPE_TO_LONG_TYPE = {
    "relationship_change": "relationship_milestone",
    "mission_event": "mission_event",
}


@dataclass(frozen=True)
class LongMemoryPromotionResult:
    promoted: NpcLongMemory | None = None
    reinforced: NpcLongMemory | None = None
    rejected_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "promoted": self.promoted.to_dict() if self.promoted else None,
            "reinforced": self.reinforced.to_dict() if self.reinforced else None,
            "rejected_reason": self.rejected_reason,
        }


def promote_short_memory(
    short_memory: NpcShortMemory,
    *,
    policy: NpcLongMemoryPolicy,
    existing_long_memories: tuple[NpcLongMemory, ...] = (),
    current_turn: int,
) -> LongMemoryPromotionResult:
    reason = _rejection_reason(short_memory, policy)
    if reason:
        return LongMemoryPromotionResult(rejected_reason=reason)
    long_type = _long_type_for(short_memory)
    if long_type is None:
        return LongMemoryPromotionResult(rejected_reason="type_not_promotable")
    if long_type not in policy.promote_types:
        return LongMemoryPromotionResult(rejected_reason="type_disabled_by_policy")

    candidate = NpcLongMemory(
        memory_id=deterministic_long_memory_id(
            short_memory.npc_id,
            short_memory.source_event_id,
            long_type,
            short_memory.memory_id,
        ),
        npc_id=short_memory.npc_id,
        memory_type=long_type,
        summary=short_memory.summary,
        source_event_id=short_memory.source_event_id,
        source_short_memory_id=short_memory.memory_id,
        created_turn=short_memory.turn,
        last_reinforced_turn=max(short_memory.turn, int(current_turn)),
        importance=short_memory.importance,
        tags=short_memory.tags,
        status="active",
        active=True,
    )
    existing = _matching_existing(candidate, existing_long_memories)
    if existing is not None and policy.reinforce_existing:
        return LongMemoryPromotionResult(
            reinforced=reinforce_long_memory(existing, candidate, current_turn)
        )
    if existing is not None:
        return LongMemoryPromotionResult(rejected_reason="duplicate_existing")
    return LongMemoryPromotionResult(promoted=candidate)


def _rejection_reason(short_memory: NpcShortMemory, policy: NpcLongMemoryPolicy) -> str:
    if not short_memory.observed:
        return "short_memory_not_observed"
    if not short_memory.active:
        return "short_memory_inactive"
    if not short_memory.source_event_id:
        return "missing_source_event_id"
    if short_memory.importance < policy.minimum_importance:
        return "importance_below_threshold"
    return ""


def _long_type_for(short_memory: NpcShortMemory) -> str | None:
    for tag in short_memory.tags:
        long_type = _TAG_TO_LONG_TYPE.get(tag)
        if long_type is not None:
            return long_type
    return _SHORT_TYPE_TO_LONG_TYPE.get(short_memory.memory_type)


def _matching_existing(candidate: NpcLongMemory, existing: tuple[NpcLongMemory, ...]) -> NpcLongMemory | None:
    for memory in existing:
        same_event = (
            memory.npc_id == candidate.npc_id
            and memory.source_event_id == candidate.source_event_id
            and memory.memory_type == candidate.memory_type
        )
        same_short = memory.source_short_memory_id == candidate.source_short_memory_id
        same_id = memory.memory_id == candidate.memory_id
        if same_id or same_event or same_short:
            return memory
    return None
