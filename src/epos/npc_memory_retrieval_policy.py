"""Deterministic NPC memory retrieval policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NpcMemoryRetrievalPolicy:
    """Limits and deterministic weights for NPC memory retrieval."""

    max_short_memories_per_npc: int = 4
    max_long_memories_per_npc: int = 3
    minimum_score: float = 0.0
    recency_window_turns: int = 12
    importance_weight: float = 1.0
    recency_weight: float = 0.4
    type_match_weight: float = 0.8
    tag_match_weight: float = 0.6
    thread_match_weight: float = 0.9
    mission_match_weight: float = 0.9
    location_match_weight: float = 0.5
    participant_match_weight: float = 0.7
    text_match_weight: float = 0.3

    def __post_init__(self) -> None:
        int_fields = {
            "max_short_memories_per_npc": self.max_short_memories_per_npc,
            "max_long_memories_per_npc": self.max_long_memories_per_npc,
            "recency_window_turns": self.recency_window_turns,
        }
        for name, value in int_fields.items():
            if not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if name == "recency_window_turns":
                if value <= 0:
                    raise ValueError(f"{name} must be positive")
            elif value < 0:
                raise ValueError(f"{name} must be non-negative")

        float_fields = {
            "minimum_score": self.minimum_score,
            "importance_weight": self.importance_weight,
            "recency_weight": self.recency_weight,
            "type_match_weight": self.type_match_weight,
            "tag_match_weight": self.tag_match_weight,
            "thread_match_weight": self.thread_match_weight,
            "mission_match_weight": self.mission_match_weight,
            "location_match_weight": self.location_match_weight,
            "participant_match_weight": self.participant_match_weight,
            "text_match_weight": self.text_match_weight,
        }
        for name, value in float_fields.items():
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            if float(value) < 0.0:
                raise ValueError(f"{name} must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_short_memories_per_npc": self.max_short_memories_per_npc,
            "max_long_memories_per_npc": self.max_long_memories_per_npc,
            "minimum_score": self.minimum_score,
            "recency_window_turns": self.recency_window_turns,
            "importance_weight": self.importance_weight,
            "recency_weight": self.recency_weight,
            "type_match_weight": self.type_match_weight,
            "tag_match_weight": self.tag_match_weight,
            "thread_match_weight": self.thread_match_weight,
            "mission_match_weight": self.mission_match_weight,
            "location_match_weight": self.location_match_weight,
            "participant_match_weight": self.participant_match_weight,
            "text_match_weight": self.text_match_weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NpcMemoryRetrievalPolicy":
        if not data:
            return cls()
        return cls(
            max_short_memories_per_npc=int(data.get("max_short_memories_per_npc", 4)),
            max_long_memories_per_npc=int(data.get("max_long_memories_per_npc", 3)),
            minimum_score=float(data.get("minimum_score", 0.0)),
            recency_window_turns=int(data.get("recency_window_turns", 12)),
            importance_weight=float(data.get("importance_weight", 1.0)),
            recency_weight=float(data.get("recency_weight", 0.4)),
            type_match_weight=float(data.get("type_match_weight", 0.8)),
            tag_match_weight=float(data.get("tag_match_weight", 0.6)),
            thread_match_weight=float(data.get("thread_match_weight", 0.9)),
            mission_match_weight=float(data.get("mission_match_weight", 0.9)),
            location_match_weight=float(data.get("location_match_weight", 0.5)),
            participant_match_weight=float(data.get("participant_match_weight", 0.7)),
            text_match_weight=float(data.get("text_match_weight", 0.3)),
        )
