"""Strict intro orchestration for Seven Nights at Azure Crown.

During the guided introduction only the target NPC is exposed to the LLM.
All other NPC presence is restored immediately after the turn. This makes the
sequence authoritative instead of relying on prompt wording alone.
"""

from __future__ import annotations

from .resort_intro import current_intro_step, initialise_resort_intro
from .resort_turn_service import ResortTurnService, _merge_reports, _speaker_id
from .validators import ValidationErrorDetail, ValidationReport


class ResortIntroTurnService(ResortTurnService):
    """Resort service with hard, single-NPC intro isolation."""

    def play(self, state, player_text: str):
        initialise_resort_intro(state)
        step = current_intro_step(state)
        if step is None:
            return super().play(state, player_text)

        presence = {
            npc_id: (npc.present, npc.location_id)
            for npc_id, npc in state.npcs.items()
        }
        try:
            for npc_id, npc in state.npcs.items():
                npc.present = npc_id == step.npc_id
                if npc_id == step.npc_id:
                    npc.location_id = state.location_id
            return super().play(state, player_text)
        finally:
            for npc_id, (present, location_id) in presence.items():
                npc = state.npcs[npc_id]
                npc.present = present
                npc.location_id = location_id
            self.store.save_state(state)

    def _strict_intro_report(self, state, scene) -> ValidationReport:
        step = current_intro_step(state)
        if step is None:
            return ValidationReport()

        target = step.npc_id
        other_ids = set(state.npcs) - {target}
        problems: list[str] = []
        errors: list[ValidationErrorDetail] = []

        wrong_speakers = []
        for line in scene.dialogue:
            speaker_id = _speaker_id(state, getattr(line, "speaker", ""))
            if speaker_id in other_ids:
                wrong_speakers.append(speaker_id)
        wrong_actions = [
            str(getattr(action, "npc_id", ""))
            for action in scene.npc_actions
            if str(getattr(action, "npc_id", "")) in other_ids
        ]
        wrong_intentions = [
            str(item.get("npc_id", ""))
            for item in scene.intentions
            if str(item.get("npc_id", "")) in other_ids
        ]

        forbidden = sorted(set(wrong_speakers + wrong_actions + wrong_intentions))
        if forbidden:
            message = (
                f"Intro Resort: nello step {target} nessun'altra NPC può parlare, "
                f"agire o ricevere intenzioni: {', '.join(forbidden)}"
            )
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    code="resort_intro_other_npc_forbidden",
                    path="dialogue|npc_actions|intentions",
                    message=message,
                    details={"target_npc_id": target, "forbidden_npcs": forbidden},
                )
            )

        if scene.visual is not None:
            if scene.visual.focus_character != target or scene.visual.visible_characters != [target]:
                message = f"Intro Resort: il visual deve contenere soltanto {target}"
                problems.append(message)
                errors.append(
                    ValidationErrorDetail(
                        code="resort_intro_single_visual_required",
                        path="visual.focus_character|visual.visible_characters",
                        message=message,
                        details={
                            "target_npc_id": target,
                            "focus_character": scene.visual.focus_character,
                            "visible_characters": list(scene.visual.visible_characters),
                        },
                    )
                )

        return ValidationReport(problems=problems, errors=errors)

    def _validate_phase1_response_after_outfit_normalization(
        self, response, state, player_text: str
    ):
        base = super()._validate_phase1_response_after_outfit_normalization(
            response, state, player_text
        )
        if response.mode != "no_check" or response.scene is None:
            return base
        return _merge_reports(base, self._strict_intro_report(state, response.scene))

    def _validate_scene_after_outfit_normalization(
        self, scene, state, player_text: str
    ):
        base = super()._validate_scene_after_outfit_normalization(
            scene, state, player_text
        )
        return _merge_reports(base, self._strict_intro_report(state, scene))
