"""Diagnostics helpers for optional NPC LLM calls."""

from __future__ import annotations

from typing import Any

from epos.npc_agent_llm_contract import NpcDedicatedLlmRunResult


def build_npc_dedicated_llm_diagnostics(result: NpcDedicatedLlmRunResult) -> dict[str, Any]:
    """Return serializable diagnostics without prompt text or raw provider output."""

    diagnostics = dict(result.diagnostics)
    diagnostics.setdefault("status", result.status)
    diagnostics.setdefault("proposal_count", len(result.response.proposals))
    return diagnostics
