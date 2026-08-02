"""Deterministic policy for NPC long memories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LONG_MEMORY_TYPES = (
    "promise",
    "betrayal",
    "trust_event",
    "fear_event",
    "relationship_milestone",
    "secret",
    "debt",
    "trauma",
    "mission_event",
    "major_decision",
    "preference",
    "long_term_threat",
    "unresolved_request",
)


@dataclass(frozen=True)
class NpcLongMemoryPolicy:
    minimum_importance: float = 0.75
    max_entries_per_npc: int = 30
    promote_types: tuple[str, ...] = LONG_MEMORY_TYPES
    reinforce_existing: bool = True
    preserve_open_promises: bool = True

    def __post_init__(self) -> None:
        minimum = float(self.minimum_importance)
        if minimum < 0.0 or minimum > 1.0:
            raise ValueError("minimum_importance must be between 0.0 and 1.0")
        object.__setattr__(self, "minimum_importance", minimum)
        max_entries = int(self.max_entries_per_npc)
        if max_entries < 0:
            raise ValueError("max_entries_per_npc must be non-negative")
        object.__setattr__(self, "max_entries_per_npc", max_entries)
        types = _unique_types(self.promote_types)
        unknown = [memory_type for memory_type in types if memory_type not in LONG_MEMORY_TYPES]
        if unknown:
            raise ValueError(f"unsupported long memory types: {unknown}")
        object.__setattr__(self, "promote_types", types)
        object.__setattr__(self, "reinforce_existing", bool(self.reinforce_existing))
        object.__setattr__(self, "preserve_open_promises", bool(self.preserve_open_promises))

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_importance": self.minimum_importance,
            "max_entries_per_npc": self.max_entries_per_npc,
            "promote_types": list(self.promote_types),
            "reinforce_existing": self.reinforce_existing,
            "preserve_open_promises": self.preserve_open_promises,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NpcLongMemoryPolicy":
        if not data:
            return cls()
        return cls(
            minimum_importance=float(data.get("minimum_importance", 0.75)),
            max_entries_per_npc=int(data.get("max_entries_per_npc", 30)),
            promote_types=tuple(data.get("promote_types", LONG_MEMORY_TYPES)),
            reinforce_existing=bool(data.get("reinforce_existing", True)),
            preserve_open_promises=bool(data.get("preserve_open_promises", True)),
        )


def _unique_types(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        memory_type = str(value or "").strip()
        if memory_type and memory_type not in seen:
            seen.add(memory_type)
            result.append(memory_type)
    return tuple(result)
