"""Deterministic retrieval for NPC short and long memories."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from epos.npc_agent_registry import NpcAgentRegistry
from epos.npc_memory_long import NpcLongMemory
from epos.npc_memory_retrieval_policy import NpcMemoryRetrievalPolicy
from epos.npc_memory_short import NpcShortMemory


_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "che",
        "con",
        "da",
        "di",
        "e",
        "il",
        "in",
        "la",
        "lo",
        "of",
        "on",
        "per",
        "the",
        "to",
        "un",
        "una",
    }
)


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _tokens(text: str) -> tuple[str, ...]:
    raw = re.findall(r"[A-Za-z0-9_:-]+", text.lower())
    return tuple(token for token in raw if token and token not in _STOPWORDS)


def _tag_matches(tags: tuple[str, ...], prefix: str, values: tuple[str, ...]) -> bool:
    value_set = set(values)
    if not value_set:
        return False
    for tag in tags:
        if tag in value_set:
            return True
        if tag.startswith(prefix) and tag[len(prefix) :] in value_set:
            return True
    return False


def _lower_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(tag.lower() for tag in tags)


@dataclass(frozen=True)
class MemoryScore:
    memory_id: str
    total: float
    components: tuple[tuple[str, float], ...] = ()
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "components": dict(self.components),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class NpcMemoryRetrievalRequest:
    npc_id: str
    short_memories: tuple[NpcShortMemory, ...] = ()
    long_memories: tuple[NpcLongMemory, ...] = ()
    current_turn: int = 0
    location_id: str = ""
    player_input: str = ""
    speaker_id: str = ""
    actor_id: str = ""
    reactor_id: str = ""
    active_thread_ids: tuple[str, ...] = ()
    active_mission_ids: tuple[str, ...] = ()
    relevant_tags: tuple[str, ...] = ()
    relevant_memory_types: tuple[str, ...] = ()
    participant_ids: tuple[str, ...] = ()
    policy: NpcMemoryRetrievalPolicy = field(default_factory=NpcMemoryRetrievalPolicy)

    def __post_init__(self) -> None:
        npc_id = str(self.npc_id).strip()
        if not npc_id:
            raise ValueError("npc_id is required")
        if self.current_turn < 0:
            raise ValueError("current_turn must be non-negative")
        participants = (
            self.speaker_id,
            self.actor_id,
            self.reactor_id,
            *self.participant_ids,
            npc_id,
        )
        object.__setattr__(self, "npc_id", npc_id)
        object.__setattr__(self, "short_memories", tuple(self.short_memories))
        object.__setattr__(self, "long_memories", tuple(self.long_memories))
        object.__setattr__(self, "active_thread_ids", _dedupe(self.active_thread_ids))
        object.__setattr__(self, "active_mission_ids", _dedupe(self.active_mission_ids))
        object.__setattr__(self, "relevant_tags", _dedupe(self.relevant_tags))
        object.__setattr__(self, "relevant_memory_types", _dedupe(self.relevant_memory_types))
        object.__setattr__(self, "participant_ids", _dedupe(participants))


@dataclass(frozen=True)
class NpcMemoryRetrievalResult:
    npc_id: str
    selected_short_memories: tuple[NpcShortMemory, ...] = ()
    selected_long_memories: tuple[NpcLongMemory, ...] = ()
    excluded_short_memory_ids: tuple[str, ...] = ()
    excluded_long_memory_ids: tuple[str, ...] = ()
    scores: tuple[MemoryScore, ...] = ()
    reasons: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "selected_short_memories": [memory.to_dict() for memory in self.selected_short_memories],
            "selected_long_memories": [memory.to_dict() for memory in self.selected_long_memories],
            "excluded_short_memory_ids": list(self.excluded_short_memory_ids),
            "excluded_long_memory_ids": list(self.excluded_long_memory_ids),
            "scores": {score.memory_id: score.to_dict() for score in self.scores},
            "reasons": {memory_id: reason for memory_id, reason in self.reasons},
        }


def _component(name: str, value: float, reasons: list[str]) -> tuple[str, float] | None:
    if value <= 0.0:
        return None
    reasons.append(name)
    return (name, round(value, 6))


def _text_match(summary: str, tags: tuple[str, ...], request: NpcMemoryRetrievalRequest) -> bool:
    input_tokens = set(_tokens(request.player_input))
    if not input_tokens:
        return False
    memory_tokens = set(_tokens(summary))
    memory_tokens.update(token.lower() for token in tags)
    return bool(input_tokens & memory_tokens)


def _score_short(memory: NpcShortMemory, request: NpcMemoryRetrievalRequest) -> MemoryScore:
    policy = request.policy
    components: list[tuple[str, float]] = []
    reasons: list[str] = []
    tags = tuple(memory.tags)

    components.append(("importance", round(memory.importance * policy.importance_weight, 6)))
    turns_elapsed = max(0, request.current_turn - memory.turn)
    recency_ratio = max(0.0, 1.0 - turns_elapsed / policy.recency_window_turns)
    maybe = _component("recency", recency_ratio * policy.recency_weight, reasons)
    if maybe:
        components.append(maybe)
    if memory.memory_type in request.relevant_memory_types:
        components.append(("type_match", policy.type_match_weight))
        reasons.append("type_match")
    lower_tags = set(_lower_tags(tags))
    if lower_tags & set(_lower_tags(request.relevant_tags)) or lower_tags & set(_tokens(request.player_input)):
        components.append(("tag_match", policy.tag_match_weight))
        reasons.append("tag_match")
    if _tag_matches(tags, "thread:", request.active_thread_ids):
        components.append(("thread_match", policy.thread_match_weight))
        reasons.append("thread_match")
    if _tag_matches(tags, "mission:", request.active_mission_ids):
        components.append(("mission_match", policy.mission_match_weight))
        reasons.append("mission_match")
    if request.location_id and _tag_matches(tags, "location:", (request.location_id,)):
        components.append(("location_match", policy.location_match_weight))
        reasons.append("location_match")
    if _tag_matches(tags, "participant:", request.participant_ids):
        components.append(("participant_match", policy.participant_match_weight))
        reasons.append("participant_match")
    if _text_match(memory.summary, tags, request):
        components.append(("text_match", policy.text_match_weight))
        reasons.append("text_match")

    total = round(sum(value for _, value in components), 6)
    return MemoryScore(memory.memory_id, total, tuple(components), _dedupe(reasons))


def _score_long(memory: NpcLongMemory, request: NpcMemoryRetrievalRequest) -> MemoryScore:
    policy = request.policy
    components: list[tuple[str, float]] = []
    reasons: list[str] = []
    tags = tuple(memory.tags)

    components.append(("importance", round(memory.importance * policy.importance_weight, 6)))
    if memory.memory_type in request.relevant_memory_types:
        components.append(("type_match", policy.type_match_weight))
        reasons.append("type_match")
    lower_tags = set(_lower_tags(tags))
    if lower_tags & set(_lower_tags(request.relevant_tags)) or lower_tags & set(_tokens(request.player_input)):
        components.append(("tag_match", policy.tag_match_weight))
        reasons.append("tag_match")
    if _tag_matches(tags, "thread:", request.active_thread_ids):
        components.append(("thread_match", policy.thread_match_weight))
        reasons.append("thread_match")
    if _tag_matches(tags, "mission:", request.active_mission_ids):
        components.append(("mission_match", policy.mission_match_weight))
        reasons.append("mission_match")
    if request.location_id and _tag_matches(tags, "location:", (request.location_id,)):
        components.append(("location_match", policy.location_match_weight))
        reasons.append("location_match")
    if _tag_matches(tags, "participant:", request.participant_ids):
        components.append(("participant_match", policy.participant_match_weight))
        reasons.append("participant_match")
    if _text_match(memory.summary, tags, request):
        components.append(("text_match", policy.text_match_weight))
        reasons.append("text_match")

    total = round(sum(value for _, value in components), 6)
    return MemoryScore(memory.memory_id, total, tuple(components), _dedupe(reasons))


def _filter_short(memory: object, request: NpcMemoryRetrievalRequest) -> str | None:
    if not isinstance(memory, NpcShortMemory):
        return "invalid_memory"
    if memory.npc_id != request.npc_id:
        return "wrong_npc"
    if not memory.observed:
        return "not_observed"
    if not memory.active:
        return "inactive"
    if not memory.source_event_id:
        return "missing_provenance"
    return None


def _filter_long(memory: object, request: NpcMemoryRetrievalRequest) -> str | None:
    if not isinstance(memory, NpcLongMemory):
        return "invalid_memory"
    if memory.npc_id != request.npc_id:
        return "wrong_npc"
    if not memory.active:
        return "inactive"
    if memory.status != "active":
        return "resolved"
    if not memory.source_event_id or not memory.source_short_memory_id:
        return "missing_provenance"
    return None


def _memory_turn(memory: NpcShortMemory | NpcLongMemory) -> int:
    if isinstance(memory, NpcShortMemory):
        return memory.turn
    return memory.last_reinforced_turn


def _ranked(
    scored: list[tuple[NpcShortMemory | NpcLongMemory, MemoryScore]],
) -> list[tuple[NpcShortMemory | NpcLongMemory, MemoryScore]]:
    return sorted(
        scored,
        key=lambda item: (
            -item[1].total,
            -item[0].importance,
            -_memory_turn(item[0]),
            item[0].memory_id,
        ),
    )


def retrieve_memories(request: NpcMemoryRetrievalRequest) -> NpcMemoryRetrievalResult:
    short_scored: list[tuple[NpcShortMemory, MemoryScore]] = []
    long_scored: list[tuple[NpcLongMemory, MemoryScore]] = []
    scores: list[MemoryScore] = []
    reasons: list[tuple[str, str]] = []
    excluded_short: list[str] = []
    excluded_long: list[str] = []

    for memory in request.short_memories:
        reason = _filter_short(memory, request)
        memory_id = getattr(memory, "memory_id", "<invalid>")
        if reason:
            excluded_short.append(memory_id)
            reasons.append((memory_id, reason))
            continue
        score = _score_short(memory, request)
        scores.append(score)
        if score.total < request.policy.minimum_score:
            excluded_short.append(memory.memory_id)
            reasons.append((memory.memory_id, "below_minimum_score"))
            continue
        short_scored.append((memory, score))

    for memory in request.long_memories:
        reason = _filter_long(memory, request)
        memory_id = getattr(memory, "memory_id", "<invalid>")
        if reason:
            excluded_long.append(memory_id)
            reasons.append((memory_id, reason))
            continue
        score = _score_long(memory, request)
        scores.append(score)
        if score.total < request.policy.minimum_score:
            excluded_long.append(memory.memory_id)
            reasons.append((memory.memory_id, "below_minimum_score"))
            continue
        long_scored.append((memory, score))

    ranked_short = _ranked(short_scored)
    ranked_long = _ranked(long_scored)
    selected_short = tuple(memory for memory, _ in ranked_short[: request.policy.max_short_memories_per_npc])
    selected_long = tuple(memory for memory, _ in ranked_long[: request.policy.max_long_memories_per_npc])

    for memory, _ in ranked_short[request.policy.max_short_memories_per_npc :]:
        excluded_short.append(memory.memory_id)
        reasons.append((memory.memory_id, "over_budget"))
    for memory, _ in ranked_long[request.policy.max_long_memories_per_npc :]:
        excluded_long.append(memory.memory_id)
        reasons.append((memory.memory_id, "over_budget"))

    return NpcMemoryRetrievalResult(
        npc_id=request.npc_id,
        selected_short_memories=selected_short,
        selected_long_memories=selected_long,
        excluded_short_memory_ids=tuple(excluded_short),
        excluded_long_memory_ids=tuple(excluded_long),
        scores=tuple(sorted(scores, key=lambda score: score.memory_id)),
        reasons=tuple(reasons),
    )


def retrieve_memories_for_npc(
    registry: NpcAgentRegistry,
    npc_id: str,
    *,
    current_turn: int = 0,
    location_id: str = "",
    player_input: str = "",
    speaker_id: str = "",
    actor_id: str = "",
    reactor_id: str = "",
    active_thread_ids: tuple[str, ...] = (),
    active_mission_ids: tuple[str, ...] = (),
    relevant_tags: tuple[str, ...] = (),
    relevant_memory_types: tuple[str, ...] = (),
    participant_ids: tuple[str, ...] = (),
    policy: NpcMemoryRetrievalPolicy | None = None,
) -> NpcMemoryRetrievalResult:
    state = registry.get(npc_id)
    if state is None:
        request = NpcMemoryRetrievalRequest(
            npc_id=npc_id,
            current_turn=current_turn,
            location_id=location_id,
            player_input=player_input,
            speaker_id=speaker_id,
            actor_id=actor_id,
            reactor_id=reactor_id,
            active_thread_ids=active_thread_ids,
            active_mission_ids=active_mission_ids,
            relevant_tags=relevant_tags,
            relevant_memory_types=relevant_memory_types,
            participant_ids=participant_ids,
            policy=policy or NpcMemoryRetrievalPolicy(),
        )
        return NpcMemoryRetrievalResult(npc_id=request.npc_id)
    request = NpcMemoryRetrievalRequest(
        npc_id=npc_id,
        short_memories=state.short_memories,
        long_memories=state.long_memories,
        current_turn=current_turn,
        location_id=location_id,
        player_input=player_input,
        speaker_id=speaker_id,
        actor_id=actor_id,
        reactor_id=reactor_id,
        active_thread_ids=active_thread_ids,
        active_mission_ids=active_mission_ids,
        relevant_tags=relevant_tags,
        relevant_memory_types=relevant_memory_types,
        participant_ids=participant_ids,
        policy=policy or NpcMemoryRetrievalPolicy(),
    )
    return retrieve_memories(request)


