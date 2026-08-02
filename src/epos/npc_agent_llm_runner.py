"""Optional dedicated NPC LLM runner.

The runner is isolated from TurnService and disabled by default. It performs at
most one logical provider call and returns a safe fallback on provider or
validation failures.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from epos.npc_agent_coordinator import NpcCoordinatorResult
from epos.npc_agent_llm_contract import (
    NpcDedicatedLlmBudget,
    NpcDedicatedLlmRequest,
    NpcDedicatedLlmResponse,
    NpcDedicatedLlmRunResult,
)
from epos.npc_agent_llm_validator import validate_npc_llm_payload


EPOS_NPC_DEDICATED_LLM_ENABLED = "EPOS_NPC_DEDICATED_LLM_ENABLED"
TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
FALSE_VALUES = frozenset({"", "false", "0", "no", "off"})


class NpcLlmProvider(Protocol):
    def complete_json(self, payload: dict[str, object]) -> object:
        ...


def parse_npc_dedicated_llm_enabled(value: str | None = None) -> bool:
    text = "" if value is None else str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise ValueError(f"invalid {EPOS_NPC_DEDICATED_LLM_ENABLED} value: {value!r}")


def npc_dedicated_llm_enabled_from_env() -> bool:
    return parse_npc_dedicated_llm_enabled(os.environ.get(EPOS_NPC_DEDICATED_LLM_ENABLED))


def run_optional_npc_llm(
    *,
    enabled: bool,
    coordinator_result: NpcCoordinatorResult,
    turn: int,
    location_id: str,
    player_input: str,
    provider: NpcLlmProvider,
    budget: NpcDedicatedLlmBudget | None = None,
) -> NpcDedicatedLlmRunResult:
    budget = budget or NpcDedicatedLlmBudget()
    selected_agent_ids = tuple(coordinator_result.selected_agent_ids)
    diagnostics_base = {
        "enabled": bool(enabled),
        "attempted": False,
        "call_count": 0,
        "selected_agent_ids": list(selected_agent_ids),
        "included_agent_ids": [],
        "excluded_by_budget": [],
        "status": "skipped",
        "reason": "",
        "proposal_count": 0,
        "validation_errors": [],
    }

    if not enabled:
        return _fallback("skipped", "disabled", diagnostics_base)
    if not coordinator_result.agent_contexts:
        return _fallback("skipped", "no_agents", diagnostics_base)
    if budget.max_calls_per_turn <= 0 or budget.max_agents_per_call <= 0:
        return _fallback("skipped", "budget_exhausted", diagnostics_base)

    included_contexts = coordinator_result.agent_contexts[: budget.max_agents_per_call]
    included_ids = tuple(context.npc_id for context in included_contexts)
    excluded_by_budget = tuple(
        context.npc_id
        for context in coordinator_result.agent_contexts[budget.max_agents_per_call :]
    )
    diagnostics = {
        **diagnostics_base,
        "attempted": True,
        "included_agent_ids": list(included_ids),
        "excluded_by_budget": list(excluded_by_budget),
    }
    request = NpcDedicatedLlmRequest(
        turn=turn,
        location_id=location_id,
        player_input=player_input,
        agents=included_contexts,
    )
    constrained_result = NpcCoordinatorResult(
        selected_agent_ids=included_ids,
        excluded_agent_ids=tuple(coordinator_result.excluded_agent_ids) + excluded_by_budget,
        agent_contexts=included_contexts,
        selection_reasons=tuple(
            (npc_id, reasons)
            for npc_id, reasons in coordinator_result.selection_reasons
            if npc_id in included_ids
        ),
        diagnostics={},
    )

    try:
        raw = provider.complete_json(request.to_dict())
        diagnostics["call_count"] = 1
    except Exception:
        diagnostics["call_count"] = 1
        return _fallback("fallback", "provider_error", diagnostics)

    try:
        payload = _payload_from_provider(raw)
    except ValueError as exc:
        reason = str(exc)
        return _fallback("fallback", reason, diagnostics)

    validation = validate_npc_llm_payload(
        payload,
        constrained_result,
        max_proposals=len(included_contexts),
    )
    if not validation.valid:
        errors = [error.to_dict() for error in validation.errors]
        reason = errors[0]["code"] if errors else "invalid_schema"
        diagnostics["validation_errors"] = errors
        return _fallback("fallback", reason, diagnostics)

    diagnostics["status"] = "success"
    diagnostics["reason"] = "success"
    diagnostics["proposal_count"] = len(validation.response.proposals)
    return NpcDedicatedLlmRunResult(
        status="success",
        response=validation.response,
        diagnostics=diagnostics,
    )


def _payload_from_provider(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_json") from exc
        if not isinstance(parsed, dict):
            raise ValueError("invalid_schema")
        return parsed
    raise ValueError("invalid_schema")


def _fallback(
    status: str,
    reason: str,
    diagnostics: dict[str, Any],
) -> NpcDedicatedLlmRunResult:
    final_diagnostics = {
        **diagnostics,
        "status": status,
        "reason": reason,
        "proposal_count": 0,
    }
    return NpcDedicatedLlmRunResult(
        status=status,
        response=NpcDedicatedLlmResponse(),
        diagnostics=final_diagnostics,
    )
