"""Relationship helpers for Seven Nights at Azure Crown.

The generic engine remains authoritative for persisted Relationship domains.
Resort-only concepts such as jealousy and perceived favouritism are stored in
WorldState.flags so existing saves and Odyssey code remain untouched.
"""

from __future__ import annotations

from typing import Any

from .models import WorldState

RESORT_NPC_IDS = ("victoria", "stella", "maria", "luna")
RELATION_FIELDS = ("trust", "attraction", "respect", "resentment", "suspicion")


def _clamp(value: int, low: int = -100, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def initialise_resort_relationships(state: WorldState) -> None:
    """Create deterministic relationship and jealousy state for a new game."""

    for npc_id in RESORT_NPC_IDS:
        npc = state.npcs.get(npc_id)
        if npc is None:
            continue
        npc.relationship_towards("player")
        state.flags.setdefault(f"resort_jealousy_{npc_id}", 0)
        state.flags.setdefault(f"resort_favour_{npc_id}", 0)
    state.flags.setdefault("resort_last_preferred_npc", "")


def apply_player_relationship_delta(
    state: WorldState,
    npc_id: str,
    *,
    trust: int = 0,
    attraction: int = 0,
    respect: int = 0,
    resentment: int = 0,
    suspicion: int = 0,
) -> dict[str, int]:
    """Apply validated deltas from one NPC towards the player."""

    if npc_id not in RESORT_NPC_IDS or npc_id not in state.npcs:
        raise ValueError(f"NPC resort sconosciuto: {npc_id!r}")
    deltas = {
        "trust": trust,
        "attraction": attraction,
        "respect": respect,
        "resentment": resentment,
        "suspicion": suspicion,
    }
    filtered = {key: int(value) for key, value in deltas.items() if int(value)}
    relationship = state.npcs[npc_id].relationship_towards("player")
    relationship.apply_delta(filtered)
    return {key: getattr(relationship, key) for key in RELATION_FIELDS}


def record_preference(state: WorldState, chosen_npc_id: str) -> dict[str, int]:
    """Record a visible player preference without turning it into consent."""

    if chosen_npc_id not in RESORT_NPC_IDS:
        raise ValueError(f"Preferenza NPC sconosciuta: {chosen_npc_id!r}")
    initialise_resort_relationships(state)
    state.flags["resort_last_preferred_npc"] = chosen_npc_id
    state.flags[f"resort_favour_{chosen_npc_id}"] = _clamp(
        int(state.flags.get(f"resort_favour_{chosen_npc_id}", 0)) + 1,
        0,
        100,
    )
    jealousy: dict[str, int] = {}
    for npc_id in RESORT_NPC_IDS:
        key = f"resort_jealousy_{npc_id}"
        current = int(state.flags.get(key, 0))
        if npc_id == chosen_npc_id:
            current = max(0, current - 1)
        elif npc_id != "victoria":
            current += 1
        state.flags[key] = _clamp(current, 0, 100)
        jealousy[npc_id] = state.flags[key]
    return jealousy


def relationship_snapshot(state: WorldState, npc_id: str) -> dict[str, Any]:
    """Return the concise, safe relationship context intended for an LLM."""

    if npc_id not in state.npcs:
        raise ValueError(f"NPC sconosciuto: {npc_id!r}")
    relationship = state.npcs[npc_id].relationship_towards("player")
    return {
        "trust": relationship.trust,
        "attraction": relationship.attraction,
        "respect": relationship.respect,
        "resentment": relationship.resentment,
        "suspicion": relationship.suspicion,
        "jealousy": int(state.flags.get(f"resort_jealousy_{npc_id}", 0)),
        "perceived_favour": int(state.flags.get(f"resort_favour_{npc_id}", 0)),
        "consent_is_never_implied": True,
    }
