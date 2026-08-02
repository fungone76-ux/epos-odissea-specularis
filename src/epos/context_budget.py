"""Deterministic context selection limits."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    max_active_npcs: int = 3
    max_missions: int = 2
    max_open_threads: int = 4
    max_recent_events: int = 6
    max_relationships: int = 6
    max_knowledge_entries: int = 8
    max_inventory_items: int = 20

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if int(value) < 0:
                raise ValueError(f"{field_name} must be non-negative")
