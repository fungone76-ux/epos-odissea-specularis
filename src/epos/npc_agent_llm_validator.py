"""Validation for optional NPC LLM proposals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from epos.npc_agent_coordinator import NpcCoordinatorResult
from epos.npc_agent_llm_contract import NpcDedicatedLlmResponse, NpcLlmProposal
from epos.npc_agent_models import validate_canonical_npc_id


ALLOWED_RESPONSE_FIELDS = frozenset({"proposals"})
ALLOWED_PROPOSAL_FIELDS = frozenset(
    {
        "npc_id",
        "stance",
        "intention_hint",
        "emotional_reaction",
        "response_priority",
        "referenced_memory_ids",
        "dialogue_hint",
    }
)
FORBIDDEN_AUTHORITATIVE_FIELDS = frozenset(
    {
        "mutations",
        "state_changes",
        "outcome",
        "dice",
        "roll",
        "damage",
        "inventory_changes",
        "relationship_changes",
        "mission_completion",
        "thread_creation",
        "new_facts",
        "new_memories",
        "scene_changes",
        "persistence_commands",
        "tool_calls",
    }
)


@dataclass(frozen=True)
class NpcLlmValidationError:
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class NpcLlmValidationResult:
    valid: bool
    response: NpcDedicatedLlmResponse = NpcDedicatedLlmResponse()
    errors: tuple[NpcLlmValidationError, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "response": self.response.to_dict(),
            "errors": [error.to_dict() for error in self.errors],
        }


def validate_npc_llm_payload(
    payload: object,
    coordinator_result: NpcCoordinatorResult,
    *,
    max_proposals: int,
) -> NpcLlmValidationResult:
    errors: list[NpcLlmValidationError] = []
    if not isinstance(payload, dict):
        return _invalid("invalid_schema", "", "payload must be a JSON object")

    _check_unknown_fields(payload, ALLOWED_RESPONSE_FIELDS, "", errors)
    proposals_data = payload.get("proposals", ())
    if not isinstance(proposals_data, list):
        errors.append(NpcLlmValidationError("invalid_schema", "proposals", "proposals must be a list"))
        return NpcLlmValidationResult(False, errors=tuple(errors))
    if len(proposals_data) > max(0, int(max_proposals)):
        errors.append(
            NpcLlmValidationError(
                "proposal_limit_exceeded",
                "proposals",
                "proposal count exceeds budget",
            )
        )

    allowed_ids = set(coordinator_result.selected_agent_ids)
    memory_ids_by_npc = _memory_ids_by_npc(coordinator_result)
    seen_npcs: set[str] = set()
    proposals: list[NpcLlmProposal] = []

    for index, item in enumerate(proposals_data):
        path = f"proposals[{index}]"
        if not isinstance(item, dict):
            errors.append(NpcLlmValidationError("invalid_schema", path, "proposal must be an object"))
            continue
        _check_unknown_fields(item, ALLOWED_PROPOSAL_FIELDS, path, errors)
        try:
            npc_id = validate_canonical_npc_id(item.get("npc_id", ""))
        except ValueError as exc:
            errors.append(NpcLlmValidationError("invalid_npc_id", f"{path}.npc_id", str(exc)))
            continue
        if npc_id not in allowed_ids:
            errors.append(NpcLlmValidationError("unknown_npc", f"{path}.npc_id", "npc_id was not selected"))
        if npc_id in seen_npcs:
            errors.append(NpcLlmValidationError("duplicate_npc", f"{path}.npc_id", "duplicate npc proposal"))
        seen_npcs.add(npc_id)
        refs = item.get("referenced_memory_ids", ())
        if not isinstance(refs, list):
            errors.append(
                NpcLlmValidationError(
                    "invalid_schema",
                    f"{path}.referenced_memory_ids",
                    "referenced_memory_ids must be a list",
                )
            )
            continue
        allowed_memory_ids = memory_ids_by_npc.get(npc_id, set())
        for ref_index, memory_id in enumerate(refs):
            if str(memory_id) not in allowed_memory_ids:
                errors.append(
                    NpcLlmValidationError(
                        "invalid_memory_reference",
                        f"{path}.referenced_memory_ids[{ref_index}]",
                        "memory reference is not selected for this NPC",
                    )
                )
        try:
            proposals.append(NpcLlmProposal.from_dict(item))
        except ValueError as exc:
            errors.append(NpcLlmValidationError("invalid_schema", path, str(exc)))

    if errors:
        return NpcLlmValidationResult(False, errors=tuple(errors))
    return NpcLlmValidationResult(True, response=NpcDedicatedLlmResponse(tuple(proposals)))


def _invalid(code: str, path: str, message: str) -> NpcLlmValidationResult:
    return NpcLlmValidationResult(False, errors=(NpcLlmValidationError(code, path, message),))


def _check_unknown_fields(
    data: dict[str, Any],
    allowed: frozenset[str],
    path: str,
    errors: list[NpcLlmValidationError],
) -> None:
    for key in data:
        field_path = f"{path}.{key}" if path else key
        if key in FORBIDDEN_AUTHORITATIVE_FIELDS:
            errors.append(NpcLlmValidationError("forbidden_field", field_path, "authoritative field is forbidden"))
        elif key not in allowed:
            errors.append(NpcLlmValidationError("forbidden_field", field_path, "field is not allowed"))


def _memory_ids_by_npc(coordinator_result: NpcCoordinatorResult) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for context in coordinator_result.agent_contexts:
        memory_ids = {
            memory.memory_id
            for memory in (*context.selected_short_memories, *context.selected_long_memories)
        }
        result[context.npc_id] = memory_ids
    return result
