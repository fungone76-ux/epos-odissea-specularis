"""Deterministic Resort runtime fidelity checks.

These helpers keep Resort-specific narrative, visual and initiative fidelity in
Python without adding LLM calls or renderer coupling.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .contract import FinalScene
from .initiative import counts_as_autonomous
from .resort_intent import ResortIntentHint, VisualRequirement, interpret_resort_intent
from .resort_intro import current_intro_step, intro_active
from .validator_common import ValidationErrorDetail, ValidationReport, ValidationWarning

_EXPLANATION_REQUEST = re.compile(
    r"\b(?:come|perche|perch?|cosa\s+intendi|dimmi\s+di\s+piu|dimmi\s+di\s+pi?|"
    r"spiegami|cosa\s+proponi|che\s+proponi)\b",
    re.IGNORECASE,
)
_PROGRESSION_REQUEST = re.compile(
    r"\b(?:continua|comincia|procedi|fallo|dimmi\s+come|vai\s+avanti|iniziamo|"
    r"prosegui|avanti)\b",
    re.IGNORECASE,
)
_EVASIVE_DIALOGUE = re.compile(
    r"^(?:certo|si|s?|ok|okay|va\s+bene|posso\s+aiutarti|certo,?\s+posso\s+aiutarti(?:\s+a\s+\w+)?)\.?$",
    re.IGNORECASE,
)
_ALLOWED_SHORT_ECHOES = {"si", "s?", "no", "grazie", "va bene", "ok", "okay", "aspetta"}

_SUBSTANTIAL_TERMS = re.compile(
    r"\b(?:perche|perch?|prima|poi|inizio|inizia|propongo|preparo|porto|"
    r"massaggio|olio|lettino|sdrai|respira|procedo|faremo|ti\s+mostro|"
    r"comincio|spiego|rilass)\w*\b",
    re.IGNORECASE,
)
_SCENE_STOPWORDS = {
    "alla", "allo", "della", "dello", "delle", "degli", "mentre", "nella",
    "nello", "sulla", "sullo", "con", "che", "per", "una", "uno", "del",
    "dei", "gli", "lei", "lui", "suo", "sua", "tuo", "tua", "the", "and",
    "with", "into", "from", "that", "this", "your", "you", "her", "his",
}
_SIMILARITY_ERROR_THRESHOLD = 0.72
_SIMILARITY_WARNING_THRESHOLD = 0.88

_REQUIREMENT_MATCHERS: dict[tuple[str, str], tuple[str, ...]] = {
    ("pose", "lying"): (
        "lying down", "reclined", "stretched out", "lying on", "sdraiata", "stesa",
        "on the massage table", "distesa",
    ),
    ("pose", "sitting"): ("sitting", "seated", "seduta", "siede"),
    ("pose", "standing"): ("standing", "in piedi"),
    ("pose", "kneeling"): ("kneeling", "in ginocchio", "inginocchiata"),
    ("body_part", "feet"): (
        "feet", "bare feet", "feet clearly visible", "feet presented", "soles visible",
        "showing her feet", "piedi", "piedi nudi", "piante dei piedi",
    ),
    ("body_part", "hands"): ("hands", "mani"),
    ("body_part", "back"): ("back", "schiena"),
    ("body_part", "legs"): ("legs", "gambe"),
    ("body_part", "chest"): ("chest", "cleavage", "seno", "petto"),
    ("visibility", "clear_and_unobstructed"): (
        "clearly visible", "presented", "toward camera", "visible", "showing",
        "reveal", "revealing", "mostra", "mostrando",
    ),
    ("framing", "must_include_all_requested_elements"): (
        "clearly visible", "presented", "toward camera", "visible", "showing",
        "include", "including", "revealing",
    ),
    ("action", "quiet_relaxation"): ("relax", "rilass", "massage table", "lettino"),
}


@dataclass(frozen=True)
class ResortFidelityDiagnostics:
    turn: int
    intro_active: bool
    intro_step: int | None
    expected_intro_npc: str
    focus_character_before: str
    visible_characters_before: tuple[str, ...]
    player_leaked: bool
    wrong_intro_focus: bool
    original_visual_valid: bool
    fallback_applied: bool
    fallback_reason: str
    visual_preserved: bool
    required_visuals: tuple[str, ...] = ()
    matched_requirements: tuple[str, ...] = ()
    missing_requirements: tuple[str, ...] = ()
    validation_stage: str = "semantic"
    retry_triggered: bool = False
    similarity_score: float = 0.0
    similarity_threshold: float = _SIMILARITY_ERROR_THRESHOLD
    progression_requested: bool = False
    warning_or_error: str = "none"
    compared_fields: tuple[str, ...] = ("last_scene", "scene.narration", "scene.dialogue")

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "intro_active": self.intro_active,
            "intro_step": self.intro_step,
            "expected_intro_npc": self.expected_intro_npc,
            "focus_character_before": self.focus_character_before,
            "visible_characters_before": list(self.visible_characters_before),
            "player_leaked": self.player_leaked,
            "wrong_intro_focus": self.wrong_intro_focus,
            "original_visual_valid": self.original_visual_valid,
            "fallback_applied": self.fallback_applied,
            "fallback_reason": self.fallback_reason,
            "visual_preserved": self.visual_preserved,
            "required_visuals": list(self.required_visuals),
            "matched_requirements": list(self.matched_requirements),
            "missing_requirements": list(self.missing_requirements),
            "validation_stage": self.validation_stage,
            "retry_triggered": self.retry_triggered,
            "similarity_score": self.similarity_score,
            "threshold": self.similarity_threshold,
            "progression_requested": self.progression_requested,
            "warning_or_error": self.warning_or_error,
            "compared_fields": list(self.compared_fields),
        }


def plain_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


def progression_requested(player_text: str) -> bool:
    return bool(_PROGRESSION_REQUEST.search(plain_text(player_text)))


def explanation_requested(player_text: str) -> bool:
    return bool(_EXPLANATION_REQUEST.search(plain_text(player_text)))


def _scene_dialogue_text(scene: FinalScene) -> str:
    return " ".join(f"{line.speaker}: {line.text}" for line in scene.dialogue)


def _scene_compare_text(scene: FinalScene) -> str:
    return " ".join([scene.narration, _scene_dialogue_text(scene)]).strip()


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", plain_text(text))
        if len(token) > 2 and token not in _SCENE_STOPWORDS
    }


def scene_similarity(previous: str, current: str) -> float:
    prev = " ".join(plain_text(previous).split())
    curr = " ".join(plain_text(current).split())
    if not prev or not curr:
        return 0.0
    sequence = SequenceMatcher(None, prev, curr).ratio()
    prev_tokens = _tokens(prev)
    curr_tokens = _tokens(curr)
    jaccard = len(prev_tokens & curr_tokens) / len(prev_tokens | curr_tokens) if prev_tokens and curr_tokens else 0.0
    return round(max(sequence, jaccard), 4)


def _requirement_key(req: VisualRequirement) -> str:
    return f"{req.kind}:{req.value}"


def _visual_text(scene: FinalScene) -> str:
    if scene.visual is None:
        return ""
    return " ".join([scene.visual.summary, scene.visual.visual_en, *scene.visual.tags_en])


def _requirement_matches(req: VisualRequirement, text: str) -> bool:
    if req.kind in {"subject", "composition", "environment", "outfit_state", "state_mutation", "prompt_constraint"}:
        return True
    haystack = plain_text(text)
    if req.value.startswith("remove_outfit_item:") or req.value.startswith("wear_outfit_item:"):
        item = req.value.split(":", 1)[1]
        return item in haystack or "remove" in haystack or "wear" in haystack
    aliases = _REQUIREMENT_MATCHERS.get((req.kind, req.value), (req.value,))
    return any(plain_text(alias) in haystack for alias in aliases)


def evaluate_visual_requirements(hint: ResortIntentHint, scene: FinalScene) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    required: list[str] = []
    matched: list[str] = []
    missing: list[str] = []
    text = _visual_text(scene)
    for req in hint.visual_requirements:
        if not req.mandatory:
            continue
        key = _requirement_key(req)
        required.append(key)
        if _requirement_matches(req, text):
            matched.append(key)
        else:
            missing.append(key)
    return tuple(required), tuple(matched), tuple(missing)


def _dialogue_line_is_substantial(text: str) -> bool:
    normalized = plain_text(text).strip(" .!?;:\"'")
    if len(normalized.split()) >= 7:
        return True
    return bool(_SUBSTANTIAL_TERMS.search(normalized))


def _dialogue_line_is_evasive(text: str) -> bool:
    normalized = plain_text(text).strip(" .!?;:\"'")
    return bool(_EVASIVE_DIALOGUE.match(normalized)) or not _dialogue_line_is_substantial(normalized)


def validate_dialogue_substance(state, scene: FinalScene, player_text: str) -> ValidationReport:
    needs_substance = explanation_requested(player_text)
    player_plain = plain_text(player_text).strip(" .!?;:\"'")
    player_echo_forbidden = progression_requested(player_text) or needs_substance
    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []
    for index, line in enumerate(scene.dialogue):
        speaker = str(getattr(line, "speaker", "") or "").strip().casefold()
        if speaker in {"player", "giocatore", "tu"}:
            continue
        line_plain = plain_text(line.text).strip(" .!?;:\"'")
        if (
            player_echo_forbidden
            and line_plain == player_plain
            and line_plain not in _ALLOWED_SHORT_ECHOES
        ):
            message = "autonomia player: dialogo NPC copia l'input del player invertendo i ruoli"
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    code="npc_dialogue_copies_player_input",
                    path=f"dialogue[{index}]",
                    message=message,
                    details={"player_text": player_text, "speaker": line.speaker, "text": line.text},
                )
            )
        if needs_substance and _dialogue_line_is_evasive(line.text):
            message = "Resort: la risposta NPC non chiarisce ne avanza la richiesta del player"
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    code="resort_npc_dialogue_evasive",
                    path=f"dialogue[{index}]",
                    message=message,
                    details={"player_text": player_text, "speaker": line.speaker, "text": line.text},
                )
            )
    return ValidationReport(problems=problems, errors=errors)


def validate_scene_progression(state, scene: FinalScene, player_text: str) -> ValidationReport:
    current = _scene_compare_text(scene)
    score = scene_similarity(getattr(state, "last_scene", ""), current)
    requested = progression_requested(player_text)
    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []
    warnings: list[ValidationWarning] = []
    details = {
        "similarity_score": score,
        "threshold": _SIMILARITY_ERROR_THRESHOLD,
        "progression_requested": requested,
        "compared_fields": ["last_scene", "scene.narration", "scene.dialogue"],
    }
    if requested and score >= _SIMILARITY_ERROR_THRESHOLD:
        message = "Resort: il player chiede avanzamento ma la scena ripete il turno precedente"
        problems.append(message)
        errors.append(
            ValidationErrorDetail(
                code="resort_scene_did_not_progress",
                path="scene.narration|dialogue",
                message=message,
                details=details,
            )
        )
    elif score >= _SIMILARITY_WARNING_THRESHOLD:
        warnings.append(
            ValidationWarning(
                code="resort_scene_repetition_warning",
                path="scene.narration|dialogue",
                message="Resort: scena molto simile al turno precedente",
                details=details,
            )
        )
    return ValidationReport(problems=problems, errors=errors, warnings=warnings)


def _has_initiative_exception(state, scene: FinalScene, player_text: str) -> bool:
    if not list(state.present_npc_ids()):
        return True
    if current_intro_step(state) is not None:
        return True
    if progression_requested(player_text) and scene.npc_actions:
        return True
    return False


def validate_initiative_obligation(state, scene: FinalScene, player_text: str) -> ValidationReport:
    reactive_turns = int(getattr(state.initiative, "consecutive_reactive_turns", 0))
    if reactive_turns < 5 or _has_initiative_exception(state, scene, player_text):
        return ValidationReport()
    if any(counts_as_autonomous(event) for event in scene.initiatives):
        return ValidationReport()
    message = "Resort: dopo 5 turni reattivi serve una iniziativa autonoma concreta di una NPC presente"
    return ValidationReport(
        problems=[message],
        errors=[
            ValidationErrorDetail(
                code="resort_autonomous_initiative_required",
                path="initiatives",
                message=message,
                details={"consecutive_reactive_turns": reactive_turns},
            )
        ],
    )


def validate_resort_visual_requirements(pack, state, scene: FinalScene, player_text: str) -> ValidationReport:
    hint = interpret_resort_intent(pack, state, player_text)
    required, matched, missing = evaluate_visual_requirements(hint, scene)
    if not missing:
        return ValidationReport()
    message = "Resort: requisiti visuali obbligatori assenti dalla scena finale"
    return ValidationReport(
        problems=[message],
        errors=[
            ValidationErrorDetail(
                code="resort_mandatory_visual_requirement_missing",
                path="visual.summary|visual.visual_en|visual.tags_en",
                message=message,
                details={
                    "required_visuals": list(required),
                    "matched_requirements": list(matched),
                    "missing_requirements": list(missing),
                    "validation_stage": "semantic",
                    "retry_triggered": True,
                },
            )
        ],
    )


def resort_fidelity_diagnostics(
    *,
    pack,
    state,
    turn: int,
    player_text: str,
    original_scene: FinalScene,
    normalized_scene: FinalScene,
    player_leaked: bool,
    wrong_intro_focus: bool,
    fallback_applied: bool,
    fallback_reason: str,
) -> ResortFidelityDiagnostics:
    step = current_intro_step(state)
    visual = original_scene.visual
    hint = interpret_resort_intent(pack, state, player_text)
    required, matched, missing = evaluate_visual_requirements(hint, normalized_scene)
    sim = scene_similarity(getattr(state, "last_scene", ""), _scene_compare_text(normalized_scene))
    warning_or_error = "none"
    if progression_requested(player_text) and sim >= _SIMILARITY_ERROR_THRESHOLD:
        warning_or_error = "error"
    elif sim >= _SIMILARITY_WARNING_THRESHOLD:
        warning_or_error = "warning"
    return ResortFidelityDiagnostics(
        turn=turn,
        intro_active=intro_active(state),
        intro_step=(step.index + 1 if step is not None else None),
        expected_intro_npc=(step.npc_id if step is not None else ""),
        focus_character_before=(visual.focus_character if visual is not None else ""),
        visible_characters_before=tuple(visual.visible_characters if visual is not None else ()),
        player_leaked=player_leaked,
        wrong_intro_focus=wrong_intro_focus,
        original_visual_valid=bool(visual and visual.focus_character and visual.visible_characters and visual.visual_en),
        fallback_applied=fallback_applied,
        fallback_reason=fallback_reason,
        visual_preserved=not fallback_applied,
        required_visuals=required,
        matched_requirements=matched,
        missing_requirements=missing,
        retry_triggered=bool(missing or warning_or_error == "error"),
        similarity_score=sim,
        progression_requested=progression_requested(player_text),
        warning_or_error=warning_or_error,
    )
