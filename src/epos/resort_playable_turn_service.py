"""Final Resort service: guided intro plus normal player navigation.

A valid player location change is a self-contained action and must not be
rejected merely because no NPC speaks. All other Resort turns keep the strict
NPC response policy.
"""

from __future__ import annotations

from .resort_intro_turn_service import ResortIntroTurnService
from .validators import ValidationReport


def _is_player_location_change(scene) -> bool:
    return any(
        str(getattr(mutation, "type", "")) == "location_change"
        and str(getattr(mutation, "target", "")) == "player"
        and bool(str(getattr(mutation, "payload", {}).get("location_id", "")).strip())
        for mutation in getattr(scene, "mutations", [])
    )


def _allow_solo_navigation(report: ValidationReport, scene) -> ValidationReport:
    if not _is_player_location_change(scene):
        return report
    blocked_codes = {"resort_npc_response_required"}
    return ValidationReport(
        problems=[
            error.message
            for error in report.errors
            if error.code not in blocked_codes
        ],
        errors=[error for error in report.errors if error.code not in blocked_codes],
        warnings=list(report.warnings),
    )


class ResortPlayableTurnService(ResortIntroTurnService):
    """Production Resort service used by the GUI and CLI launchers."""

    def _validate_phase1_response_after_outfit_normalization(
        self, response, state, player_text: str
    ):
        report = super()._validate_phase1_response_after_outfit_normalization(
            response, state, player_text
        )
        if response.mode != "no_check" or response.scene is None:
            return report
        return _allow_solo_navigation(report, response.scene)

    def _validate_scene_after_outfit_normalization(
        self, scene, state, player_text: str
    ):
        report = super()._validate_scene_after_outfit_normalization(
            scene, state, player_text
        )
        return _allow_solo_navigation(report, scene)
