"""Deterministic policy for NPC short memories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NpcShortMemoryPolicy:
    max_entries_per_npc: int = 10
    minimum_importance: float = 0.10
    decay_per_turn: float = 0.02
    retain_open_threads: bool = True
    retain_promises: bool = True

    def __post_init__(self) -> None:
        max_entries = int(self.max_entries_per_npc)
        if max_entries < 0:
            raise ValueError("max_entries_per_npc must be non-negative")
        object.__setattr__(self, "max_entries_per_npc", max_entries)
        minimum = float(self.minimum_importance)
        if minimum < 0.0 or minimum > 1.0:
            raise ValueError("minimum_importance must be between 0.0 and 1.0")
        object.__setattr__(self, "minimum_importance", minimum)
        decay = float(self.decay_per_turn)
        if decay < 0.0:
            raise ValueError("decay_per_turn must be non-negative")
        object.__setattr__(self, "decay_per_turn", decay)
        object.__setattr__(self, "retain_open_threads", bool(self.retain_open_threads))
        object.__setattr__(self, "retain_promises", bool(self.retain_promises))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_entries_per_npc": self.max_entries_per_npc,
            "minimum_importance": self.minimum_importance,
            "decay_per_turn": self.decay_per_turn,
            "retain_open_threads": self.retain_open_threads,
            "retain_promises": self.retain_promises,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NpcShortMemoryPolicy":
        if not data:
            return cls()
        return cls(
            max_entries_per_npc=int(data.get("max_entries_per_npc", 10)),
            minimum_importance=float(data.get("minimum_importance", 0.10)),
            decay_per_turn=float(data.get("decay_per_turn", 0.02)),
            retain_open_threads=bool(data.get("retain_open_threads", True)),
            retain_promises=bool(data.get("retain_promises", True)),
        )
