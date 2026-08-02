"""Common validation report structures and diagnostics helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationErrorDetail:
    code: str
    path: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ValidationWarning:
    code: str
    path: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ValidationReport:
    problems: list[str] = field(default_factory=list)
    errors: list[ValidationErrorDetail] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and not self.errors

    def __post_init__(self) -> None:
        if self.problems and not self.errors:
            object.__setattr__(
                self,
                "errors",
                [
                    ValidationErrorDetail(
                        code=_code_for_problem(problem),
                        path=_path_for_problem(problem),
                        message=problem,
                    )
                    for problem in self.problems
                ],
            )
        if self.errors and not self.problems:
            object.__setattr__(self, "problems", [error.message for error in self.errors])

    def to_dict(self, *, stage: str = "semantic", phase: str = "") -> dict[str, Any]:
        return {
            "valid": self.ok,
            "validation_stage": stage,
            "phase": phase,
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "problems": list(self.problems),
        }


def _code_for_problem(problem: str) -> str:
    text = problem.lower()
    if "testimone assente" in text:
        return "invalid_memory_witness"
    if "memory_event richiede witnesses" in text:
        return "memory_without_witnesses"
    if "personaggio visibile ma assente" in text:
        return "visible_character_not_present"
    if "focus_character deve comparire" in text:
        return "focus_character_not_visible"
    if "target inesistente" in text:
        return "invalid_mutation_target"
    if "destinazione sconosciuta" in text:
        return "invalid_location_reference"
    if "marker" in text:
        return "invalid_story_marker"
    if "target non presente" in text or "target assente" in text:
        return "invalid_mutation_target"
    if "skill" in text:
        return "missing_required_field"
    if "difficolt" in text:
        return "semantic_contract_rejected"
    return "semantic_contract_rejected"


def _path_for_problem(problem: str) -> str:
    text = problem.lower()
    if "memory_event" in text:
        return "memory_events"
    if "visual:" in text:
        return "visual.visible_characters"
    if "dialogo" in text:
        return "dialogue"
    if "relationship_delta" in text:
        return "mutations.relationship_delta"
    if "location_change" in text:
        return "mutations.location_change"
    if "story_marker" in text or "marker" in text:
        return "mutations.story_marker_add"
    if "target" in text:
        return "target_ids"
    if "skill" in text:
        return "skill"
    if "difficolt" in text:
        return "difficulty"
    return ""


def _add_problem(
    problems: list[str],
    errors: list[ValidationErrorDetail],
    code: str,
    path: str,
    message: str,
    **details: Any,
) -> None:
    problems.append(message)
    errors.append(ValidationErrorDetail(code=code, path=path, message=message, details=details))
