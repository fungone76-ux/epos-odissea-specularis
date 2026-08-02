"""Deterministic context size and selection diagnostics."""

from __future__ import annotations

import json
import math
from typing import Any


def estimate_context_size(value: Any) -> dict[str, int]:
    text = json.dumps(value, ensure_ascii=False, indent=1)
    characters = len(text)
    return {
        "characters": characters,
        "bytes": len(text.encode("utf-8")),
        "estimated_tokens": math.ceil(characters / 4),
    }


def snapshot_element_counts(snapshot: dict[str, Any]) -> dict[str, int]:
    missions = snapshot.get("missions", {})
    current_missions = missions.get("current", []) if isinstance(missions, dict) else []
    upcoming_missions = missions.get("upcoming", []) if isinstance(missions, dict) else []
    player = snapshot.get("player", {})
    return {
        "world_facts": len(snapshot.get("world_facts", [])),
        "npc_relationships": len(snapshot.get("npc_relationships", [])),
        "present_npcs": len(snapshot.get("present_npcs", [])),
        "active_threads": len(snapshot.get("active_threads", [])),
        "missions": len(current_missions) + len(upcoming_missions),
        "player_inventory": len(player.get("inventory", [])) if isinstance(player, dict) else 0,
        "player_knowledge": len(snapshot.get("player_knowledge", [])),
        "player_knowledge_provenance": len(snapshot.get("player_knowledge_provenance", [])),
    }


def compare_context_size(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_size = estimate_context_size(before)
    after_size = estimate_context_size(after)
    before_chars = before_size["characters"]
    after_chars = after_size["characters"]
    reduction = 0.0
    if before_chars:
        reduction = round(((before_chars - after_chars) / before_chars) * 100, 2)
    return {
        "characters_before": before_size["characters"],
        "characters_after": after_size["characters"],
        "bytes_before": before_size["bytes"],
        "bytes_after": after_size["bytes"],
        "estimated_tokens_before": before_size["estimated_tokens"],
        "estimated_tokens_after": after_size["estimated_tokens"],
        "reduction_percent": reduction,
        "elements_before": snapshot_element_counts(before),
        "elements_after": snapshot_element_counts(after),
    }
