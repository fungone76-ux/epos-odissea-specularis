"""Diagnostics for deterministic NPC memory retrieval."""

from __future__ import annotations

from typing import Any

from epos.npc_memory_retrieval import NpcMemoryRetrievalResult


def build_memory_retrieval_diagnostics(result: NpcMemoryRetrievalResult) -> dict[str, Any]:
    """Return a serializable diagnostic payload without prompt or provider data."""

    reasons = dict(result.reasons)
    score_map = {score.memory_id: score.to_dict() for score in result.scores}
    selected_short = [memory.memory_id for memory in result.selected_short_memories]
    selected_long = [memory.memory_id for memory in result.selected_long_memories]
    excluded_short = list(result.excluded_short_memory_ids)
    excluded_long = list(result.excluded_long_memory_ids)
    return {
        "npc_id": result.npc_id,
        "selected_short": selected_short,
        "selected_long": selected_long,
        "excluded": {
            memory_id: reasons.get(memory_id, "excluded")
            for memory_id in (*excluded_short, *excluded_long)
        },
        "scores": score_map,
        "counts": {
            "selected_short": len(selected_short),
            "selected_long": len(selected_long),
            "excluded_short": len(excluded_short),
            "excluded_long": len(excluded_long),
        },
    }
