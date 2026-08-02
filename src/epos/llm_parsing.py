"""Parsing helpers for OpenAI-compatible provider responses."""

from __future__ import annotations

import json
from typing import Any

from .llm_diagnostics import _validation_error, _validation_report
from .llm_errors import LlmProviderError


def _parse_openai_compatible_response(
    response_text: str,
) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        report = _validation_report(
            False,
            phase="",
            stage="parsing",
            errors=[_validation_error("invalid_json", "", str(exc))],
        )
        raise LlmProviderError(
            "provider response is not valid JSON",
            status="invalid_json",
            diagnostics={"raw_content": response_text, "validation_report": report},
        ) from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        report = _validation_report(
            False,
            phase="",
            stage="extraction",
            errors=[_validation_error("missing_content", "choices[0].message.content", "response missing content")],
        )
        raise LlmProviderError(
            "response missing content",
            status="missing_content",
            diagnostics={"raw_content": response_text, "parsed_response": data, "validation_report": report},
        ) from exc
    if not str(content).strip():
        report = _validation_report(
            False,
            phase="",
            stage="extraction",
            errors=[_validation_error("empty_response", "choices[0].message.content", "empty response content")],
        )
        raise LlmProviderError(
            "empty response content",
            status="empty_response",
            diagnostics={"raw_content": "", "parsed_response": data, "validation_report": report},
        )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        report = _validation_report(
            False,
            phase="",
            stage="parsing",
            errors=[_validation_error("invalid_json", "", str(exc))],
        )
        raise LlmProviderError(
            "content is not valid JSON",
            status="invalid_json",
            diagnostics={"raw_content": content, "validation_report": report},
        ) from exc
    if not isinstance(parsed, dict):
        report = _validation_report(
            False,
            phase="",
            stage="schema",
            errors=[_validation_error("schema_validation_failed", "", "content is not a JSON object")],
        )
        raise LlmProviderError(
            "content is not a JSON object",
            status="contract_invalid",
            diagnostics={"raw_content": content, "parsed_response": parsed, "validation_report": report},
        )
    usage = data.get("usage")
    return parsed, str(content), dict(usage) if isinstance(usage, dict) else None
