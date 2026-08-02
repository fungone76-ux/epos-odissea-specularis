"""LLM diagnostics and validation-report helpers."""

from __future__ import annotations

import re
from typing import Any


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip().lower())
    return safe or "provider"


def _sanitize_sensitive_text(text: str) -> str:
    sanitized = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+",
        r"\1[REDACTED]",
        text,
    )
    sanitized = re.sub(
        r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,\"']+",
        r"\1[REDACTED]",
        sanitized,
    )
    return sanitized


def _sanitize_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"authorization", "api_key", "apikey", "token"}:
                clean[key] = "[REDACTED]"
            else:
                clean[key] = _sanitize_sensitive_data(item)
        return clean
    if isinstance(value, list):
        return [_sanitize_sensitive_data(item) for item in value]
    if isinstance(value, str):
        return _sanitize_sensitive_text(value)
    return value


def _validation_error(
    code: str,
    path: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "path": path,
        "message": message,
        "details": details or {},
    }


def _validation_report(
    valid: bool,
    *,
    phase: str,
    stage: str = "semantic",
    errors: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    problems: list[str] | None = None,
) -> dict[str, Any]:
    errors = errors or []
    problems = problems if problems is not None else [str(e.get("message", "")) for e in errors]
    return {
        "valid": valid,
        "phase": phase,
        "validation_stage": stage,
        "validation_reason": "" if valid else (errors[0].get("code", "semantic_contract_rejected") if errors else "semantic_contract_rejected"),
        "errors": errors,
        "warnings": warnings or [],
        "problems": problems,
    }


def _normalize_validation_result(result: Any, *, phase: str) -> dict[str, Any]:
    if result is None:
        return _validation_report(True, phase=phase)
    if hasattr(result, "to_dict"):
        data = result.to_dict(stage="semantic", phase=phase)
        errors = list(data.get("errors", []))
        return _validation_report(
            bool(data.get("valid", not errors)),
            phase=phase,
            stage=str(data.get("validation_stage", "semantic")),
            errors=errors,
            warnings=list(data.get("warnings", [])),
            problems=list(data.get("problems", [])),
        )
    if isinstance(result, dict) and "valid" in result:
        errors = list(result.get("errors", []))
        return _validation_report(
            bool(result.get("valid")),
            phase=phase,
            stage=str(result.get("validation_stage", "semantic")),
            errors=errors,
            warnings=list(result.get("warnings", [])),
            problems=list(result.get("problems", [])),
        )
    problems = [str(problem) for problem in result] if isinstance(result, list) else [str(result)]
    if not problems:
        return _validation_report(True, phase=phase)
    errors = [
        _validation_error(_code_for_problem(problem), _path_for_problem(problem), problem)
        for problem in problems
    ]
    return _validation_report(False, phase=phase, errors=errors, problems=problems)


def _code_for_problem(problem: str) -> str:
    text = problem.lower()
    if "testimone assente" in text:
        return "invalid_memory_witness"
    if "personaggio visibile ma assente" in text:
        return "visible_character_not_present"
    if "target inesistente" in text or "npc inesistente" in text:
        return "unknown_npc_id"
    if "destinazione sconosciuta" in text:
        return "invalid_location_reference"
    if "visual obbligatorio" in text or "senza" in text or "mancant" in text:
        return "missing_required_field"
    return "semantic_contract_rejected"


def _path_for_problem(problem: str) -> str:
    text = problem.lower()
    if "memory_event" in text:
        return "memory_events"
    if "visual:" in text:
        return "visual.visible_characters"
    if "target" in text:
        return "target_ids"
    return ""
