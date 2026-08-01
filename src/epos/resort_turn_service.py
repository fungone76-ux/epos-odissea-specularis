"""Turn service specializzato per Seven Nights at Azure Crown.

Il giocatore e il miliardario e agisce in prima persona, ma resta sempre
fuori campo. Ogni turno con NPC presenti deve contenere una loro risposta,
reazione o iniziativa; le immagini mostrano esclusivamente la NPC che parla,
reagisce o agisce.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from .contract import FinalScene
from .turn_service import TurnService
from .validators import ValidationErrorDetail, ValidationReport

RESORT_WORLD_ID = "resort_world"
_PLAYER_VISUAL_TERMS = re.compile(
    r"\b(player|protagonist|the billionaire|billionaire man|male guest|adult man)\b",
    re.IGNORECASE,
)


def _speaker_id(state, speaker: str) -> str | None:
    value = str(speaker or "").strip().casefold()
    if not value:
        return None
    for npc_id, npc in state.npcs.items():
        if value in {npc_id.casefold(), str(npc.name).casefold()}:
            return npc_id
    return None


def _npc_from_scene(state, scene: FinalScene) -> str | None:
    """Sceglie la NPC protagonista con priorita speaker > reazione > azione."""

    present = [npc_id for npc_id in state.present_npc_ids() if npc_id in state.npcs]
    if not present:
        return None

    for line in scene.dialogue:
        npc_id = _speaker_id(state, getattr(line, "speaker", ""))
        if npc_id in present:
            return npc_id

    visual = scene.visual
    if visual is not None:
        for candidate in (
            visual.speaker_character,
            visual.reactor_character,
            visual.actor_character,
            visual.focus_character,
            *visual.visible_characters,
        ):
            if candidate in present:
                return candidate

    for action in scene.npc_actions:
        npc_id = str(getattr(action, "npc_id", ""))
        if npc_id in present:
            return npc_id

    for initiative in scene.initiatives:
        npc_id = str(getattr(initiative, "npc_id", ""))
        if npc_id in present:
            return npc_id

    return present[0]


def enforce_resort_player_pov(state, pack, scene: FinalScene) -> FinalScene:
    """Rende autorevole il POV: il player non entra mai nel frame Resort."""

    if getattr(pack, "id", "") != RESORT_WORLD_ID or scene.visual is None:
        return scene

    npc_id = _npc_from_scene(state, scene)
    if npc_id is None:
        return scene

    npc = state.npcs[npc_id]
    location = pack.locations.get(state.location_id)
    location_name = location.name if location is not None else state.location_id
    visual = scene.visual

    visual_text = str(visual.visual_en or "").strip()
    summary = str(visual.summary or "").strip()
    player_leaked = (
        "player" in visual.visible_characters
        or visual.focus_character == "player"
        or bool(_PLAYER_VISUAL_TERMS.search(visual_text))
        or bool(_PLAYER_VISUAL_TERMS.search(summary))
    )
    if player_leaked:
        visual_text = (
            f"{npc.name} reacts to the unseen VIP guest in {location_name}, "
            "adult woman, expressive body language, elegant cinematic composition"
        )
        summary = f"{npc.name} reagisce al miliardario fuori campo."
        tags = ["NPC reaction", "unseen guest POV", "luxury resort"]
    else:
        tags = list(visual.tags_en)

    corrected_visual = replace(
        visual,
        summary=summary,
        focus_character=npc_id,
        visible_characters=[npc_id],
        shared_action=False,
        visual_en=visual_text,
        tags_en=tags,
        speaker_character=(npc_id if visual.moment_type == "speech" else visual.speaker_character),
        actor_character=(npc_id if visual.actor_character == "player" else visual.actor_character),
        reactor_character=(npc_id if visual.reactor_character in ("", "player") else visual.reactor_character),
        multi_character_reason="",
        multi_character_participants=[npc_id],
    )
    return replace(scene, visual=corrected_visual)


def validate_resort_scene_policy(state, pack, scene: FinalScene) -> ValidationReport:
    if getattr(pack, "id", "") != RESORT_WORLD_ID:
        return ValidationReport()

    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []
    present_npcs = set(state.present_npc_ids())

    npc_dialogue = any(
        _speaker_id(state, getattr(line, "speaker", "")) in present_npcs
        for line in scene.dialogue
    )
    npc_action = any(
        str(getattr(action, "npc_id", "")) in present_npcs
        for action in scene.npc_actions
    )
    npc_initiative = any(
        str(getattr(event, "npc_id", "")) in present_npcs
        for event in scene.initiatives
    )
    if present_npcs and not (npc_dialogue or npc_action or npc_initiative):
        message = (
            "Resort: il turno deve contenere una risposta, reazione o iniziativa "
            "di almeno una NPC presente"
        )
        problems.append(message)
        errors.append(
            ValidationErrorDetail(
                code="resort_npc_response_required",
                path="dialogue|npc_actions|initiatives",
                message=message,
                details={"present_npcs": sorted(present_npcs)},
            )
        )

    if scene.visual is not None:
        if scene.visual.focus_character == "player" or "player" in scene.visual.visible_characters:
            message = "Resort: il giocatore non puo comparire ne essere il focus dell'immagine"
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    code="resort_player_visual_forbidden",
                    path="visual.focus_character|visual.visible_characters",
                    message=message,
                    details={
                        "focus_character": scene.visual.focus_character,
                        "visible_characters": list(scene.visual.visible_characters),
                    },
                )
            )
        visual_text = " ".join(
            [scene.visual.summary, scene.visual.visual_en, *scene.visual.tags_en]
        )
        if _PLAYER_VISUAL_TERMS.search(visual_text):
            message = "Resort: la descrizione visuale deve inquadrare la NPC, non il miliardario"
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    code="resort_player_visual_text_forbidden",
                    path="visual.visual_en",
                    message=message,
                    details={},
                )
            )

    return ValidationReport(problems=problems, errors=errors)


def _merge_reports(*reports: ValidationReport) -> ValidationReport:
    return ValidationReport(
        problems=[problem for report in reports for problem in report.problems],
        errors=[error for report in reports for error in report.errors],
        warnings=[warning for report in reports for warning in report.warnings],
    )


class ResortTurnService(TurnService):
    """TurnService con contratto narrativo e visivo specifico del Resort."""

    def _normalize_phase1_pipeline(
        self,
        state,
        turn: int,
        player_text: str,
        response,
        *,
        phase: str,
    ):
        response = super()._normalize_phase1_pipeline(
            state, turn, player_text, response, phase=phase
        )
        if response.mode == "no_check" and response.scene is not None:
            response = replace(
                response,
                scene=enforce_resort_player_pov(state, self.pack, response.scene),
            )
        return response

    def _normalize_scene_pipeline(
        self,
        state,
        turn: int,
        player_text: str,
        scene: FinalScene,
        *,
        phase: str,
    ) -> FinalScene:
        scene = super()._normalize_scene_pipeline(
            state, turn, player_text, scene, phase=phase
        )
        return enforce_resort_player_pov(state, self.pack, scene)

    def _validate_phase1_response_after_outfit_normalization(
        self,
        response,
        state,
        player_text: str,
    ):
        base = super()._validate_phase1_response_after_outfit_normalization(
            response, state, player_text
        )
        if response.mode != "no_check" or response.scene is None:
            return base
        return _merge_reports(
            base,
            validate_resort_scene_policy(state, self.pack, response.scene),
        )

    def _validate_scene_after_outfit_normalization(
        self,
        scene: FinalScene,
        state,
        player_text: str,
    ):
        base = super()._validate_scene_after_outfit_normalization(
            scene, state, player_text
        )
        return _merge_reports(
            base,
            validate_resort_scene_policy(state, self.pack, scene),
        )
