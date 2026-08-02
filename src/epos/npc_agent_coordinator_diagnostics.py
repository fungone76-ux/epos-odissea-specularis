"""Diagnostics for passive NPC agent coordination."""

from __future__ import annotations

from typing import Any

from epos.npc_agent_coordinator import NpcCoordinatorResult


def build_npc_coordinator_diagnostics(result: NpcCoordinatorResult) -> dict[str, Any]:
    """Return a serializable coordination diagnostic without prompt/provider data."""

    contexts = {}
    for context in result.agent_contexts:
        contexts[context.npc_id] = {
            "selection_reasons": list(context.selection_reasons),
            "short_selected": [memory.memory_id for memory in context.selected_short_memories],
            "long_selected": [memory.memory_id for memory in context.selected_long_memories],
            "relationship_refs": list(context.relationship_refs),
            "knowledge_refs": list(context.knowledge_refs),
            "open_thread_ids": list(context.open_thread_ids),
            "mission_refs": list(context.mission_refs),
        }
    return {
        "selected_agents": list(result.selected_agent_ids),
        "excluded_agents": list(result.excluded_agent_ids),
        "agent_contexts": contexts,
        "counts": {
            "selected_agents": len(result.selected_agent_ids),
            "excluded_agents": len(result.excluded_agent_ids),
            "agent_contexts": len(result.agent_contexts),
        },
    }
