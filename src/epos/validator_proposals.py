"""Phase-1 proposal validation."""

from __future__ import annotations

from .contract import CheckProposal, ConfrontProposal
from .models import WorldState
from .rules import MAX_DIFFICULTY, MIN_DIFFICULTY
from .validator_common import ValidationErrorDetail, ValidationReport, _add_problem
from .worldpack import WorldPack


def validate_check_proposal(
    state: WorldState,
    pack: WorldPack,
    proposal: CheckProposal,
) -> ValidationReport:
    """La proposta del GM non Ã¨ autorevole: Python la sottopone a giudizio."""

    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []

    if not MIN_DIFFICULTY <= proposal.difficulty <= MAX_DIFFICULTY:
        _add_problem(
            problems,
            errors,
            "semantic_contract_rejected",
            "check.difficulty",
            f"difficoltÃ  {proposal.difficulty} fuori range {MIN_DIFFICULTY}-{MAX_DIFFICULTY}",
            value=proposal.difficulty,
            min=MIN_DIFFICULTY,
            max=MAX_DIFFICULTY,
        )

    if not proposal.skill:
        _add_problem(problems, errors, "missing_required_field", "check.skill", "skill della prova non dichiarata")

    for index, target_id in enumerate(proposal.target_ids):
        if target_id not in ("player", *state.npcs.keys()):
            _add_problem(
                problems,
                errors,
                "unknown_npc_id",
                f"check.target_ids[{index}]",
                f"target inesistente: {target_id!r}",
                target_id=target_id,
            )
        elif not state.is_present(target_id):
            _add_problem(
                problems,
                errors,
                "invalid_mutation_target",
                f"check.target_ids[{index}]",
                f"target non presente nella scena: {target_id!r}",
                target_id=target_id,
            )

    if proposal.opposition == "npc_resistance" and not any(
        tid in state.npcs for tid in proposal.target_ids
    ):
        _add_problem(
            problems,
            errors,
            "semantic_contract_rejected",
            "check.opposition",
            "opposizione npc_resistance senza un NPC bersaglio",
        )

    return ValidationReport(problems, errors)


def validate_confront_proposal(
    state: WorldState,
    pack: WorldPack,
    proposal: ConfrontProposal,
) -> ValidationReport:
    """Il confronto richiede un NPC presente e una skill dichiarata."""

    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []
    if proposal.target_id not in state.npcs:
        _add_problem(
            problems,
            errors,
            "unknown_npc_id",
            "confront.target_id",
            f"confronto con NPC inesistente: {proposal.target_id!r}",
            target_id=proposal.target_id,
        )
    elif not state.npcs[proposal.target_id].present:
        _add_problem(
            problems,
            errors,
            "actor_character_not_present",
            "confront.target_id",
            f"confronto con NPC assente: {proposal.target_id!r}",
            target_id=proposal.target_id,
        )
    if not proposal.skill:
        _add_problem(problems, errors, "missing_required_field", "confront.skill", "skill del confronto non dichiarata")
    return ValidationReport(problems, errors)
