"""Deterministic player-agency guardrails.

The GM may describe consequences, sensory perception and NPC agency, but it
must not invent voluntary player speech, goals or new actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .contract import CheckProposal, ConfrontProposal, FinalScene
from .entity_ids import player_aliases_for_state
from .models import WorldState
from .validators import ValidationErrorDetail, ValidationReport
from .worldpack import WorldPack


PASSIVE_ACTIONS = {"waking", "observing", "listening", "waiting", "stillness"}
CHECK_ACTIONS = {"physical", "social", "stealth", "investigate", "intimate", "power"}

_WAKING = re.compile(r"\b(?:mi\s+)?(?:risveglio|sveglio|riprendo\s+i\s+sensi|apro\s+gli\s+occhi)\b")
_OBSERVE = re.compile(r"\b(?:guardo|osservo|scruto|vedo|mi\s+guardo)\b")
_LISTEN = re.compile(r"\b(?:ascolto|sento|origlio)\b")
_WAIT = re.compile(r"\b(?:aspetto|attendo|resto\s+in\s+attesa)\b")
_STILL = re.compile(r"\b(?:resto\s+ferma|rimango\s+ferma|non\s+mi\s+muovo)\b")
_SPEAK = re.compile(r"\b(?:dico|chiedo|domando|rispondo|sussurro|grido|urlo)\b")
_DECEIVE = re.compile(r"\b(?:inganno|mento|fingo|raggiro|dolos|bugia|tranello)\b")
_ATTACK = re.compile(r"\b(?:attacco|colpisco|pugnalo|uccido|ferisco|lotto|combatto)\b")
_MOVE = re.compile(r"\b(?:cammino|avanzo|entro|esco|mi\s+alzo|mi\s+avvicino|esploro|cerco)\b")
_SEDUCE = re.compile(r"\b(?:seduco|provoco|flirto|bacio|accarezzo|desidero|faccio\s+l.?amore)\b")
_IMMEDIATE_DANGER = re.compile(r"\b(?:mi\s+attacca|sta\s+per\s+colpire|pericolo\s+immediato|crolla|incendio|insegue)\b")

_VOLUNTARY_NARRATION = (
    re.compile(r"\b(?:decidi|scegli|vuoi|cerchi\s+di|provi\s+a)\b", re.IGNORECASE),
    re.compile(r"\b(?:chiedi|domandi|dici|rispondi|sussurri|parli)\b", re.IGNORECASE),
    re.compile(r"\b(?:inganni|menti|fingi|raggiri|tendi\s+un\s+tranello)\b", re.IGNORECASE),
    re.compile(r"\b(?:ti\s+alzi|avanzi|ti\s+avvicini|esplori|attacchi|colpisci|seduci)\b", re.IGNORECASE),
    re.compile(r"\b(?:ottenere\s+informazioni|scoprire\s+come|piano\s+di\s+fuga|strategia)\b", re.IGNORECASE),
)
_VISUAL_DRIFT = re.compile(
    r"\b(?:standing|stands|speaking|talking|deceiving|questioning|asking|"
    r"walking|advancing|attacking|seducing)\b",
    re.IGNORECASE,
)
_BED_TERMS_EN = re.compile(r"\b(?:straw\s+bed|straw\s+pallet|pallet|bedding|bed)\b", re.IGNORECASE)
_WAKING_TERMS_EN = re.compile(r"\b(?:waking|awakening|wakes|opening\s+her\s+eyes|lying|reclining)\b", re.IGNORECASE)


@dataclass(frozen=True)
class PlayerAgencyDiagnostics:
    player_input_action: str = "other"
    proposed_player_action: str = "other"
    player_agency_violation: bool = False
    invented_player_dialogue: bool = False
    invented_player_intention: bool = False
    action_semantic_drift: bool = False
    visual_moment_drift: bool = False
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_input_action": self.player_input_action,
            "proposed_player_action": self.proposed_player_action,
            "player_agency_violation": self.player_agency_violation,
            "invented_player_dialogue": self.invented_player_dialogue,
            "invented_player_intention": self.invented_player_intention,
            "action_semantic_drift": self.action_semantic_drift,
            "visual_moment_drift": self.visual_moment_drift,
            "problems": list(self.problems),
        }


def _norm(text: str) -> str:
    return (
        text.casefold()
        .replace("'", " ")
        .replace("’", " ")
        .replace("à", "a")
        .replace("è", "e")
        .replace("é", "e")
        .replace("ì", "i")
        .replace("ò", "o")
        .replace("ù", "u")
    )


def classify_player_input_action(player_text: str) -> str:
    text = _norm(player_text)
    for name, pattern in (
        ("speaking", _SPEAK),
        ("deception", _DECEIVE),
        ("attack", _ATTACK),
        ("seduction", _SEDUCE),
        ("movement", _MOVE),
        ("waking", _WAKING),
        ("observing", _OBSERVE),
        ("listening", _LISTEN),
        ("waiting", _WAIT),
        ("stillness", _STILL),
    ):
        if pattern.search(text):
            return name
    return "other"


def classify_proposed_player_action(proposal: CheckProposal | ConfrontProposal | None) -> str:
    if proposal is None:
        return "other"
    if isinstance(proposal, CheckProposal):
        text = _norm(" ".join([proposal.action_kind, proposal.skill, proposal.reason, *proposal.stakes.values()]))
        if proposal.action_kind in CHECK_ACTIONS:
            if proposal.action_kind == "social" or _DECEIVE.search(text):
                return "deception" if _DECEIVE.search(text) else "social"
            if proposal.action_kind == "intimate" or _SEDUCE.search(text):
                return "seduction"
            if proposal.action_kind == "physical" or _ATTACK.search(text):
                return "attack"
            if proposal.action_kind in ("stealth", "investigate") or _MOVE.search(text):
                return proposal.action_kind
            return proposal.action_kind
    return "confront"


def _quoted_player_texts(player_text: str) -> set[str]:
    quoted: set[str] = set()
    for pattern in (
        r'"([^"]+)"',
        r"“([^”]+)”",
        r"«([^»]+)»",
        r"'([^']+)'",
    ):
        quoted.update(m.strip() for m in re.findall(pattern, player_text) if m.strip())
    return quoted


_ALLOWED_NPC_ECHOES = {"si", "sì", "no", "grazie", "va bene", "ok", "okay"}
_SPEECH_VERB_TAIL = re.compile(
    r"\s+(?:lo|la|le|gli|ti|vi)?\s*(?:dico|chiedo|domando|rispondo|sussurro|grido|urlo)\b.*$",
    re.IGNORECASE,
)
_SPEECH_VERB_HEAD = re.compile(
    r"^(?:lo|la|le|gli|ti|vi)?\s*(?:dico|chiedo|domando|rispondo|sussurro|grido|urlo)\b\s*(?:a\s+\w+)?\s*",
    re.IGNORECASE,
)


def _speech_key(text: str) -> str:
    cleaned = _norm(text)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned, flags=re.UNICODE)
    return " ".join(cleaned.split())


def _player_spoken_text_key(player_text: str) -> str:
    text = _SPEECH_VERB_TAIL.sub("", player_text.strip())
    text = _SPEECH_VERB_HEAD.sub("", text.strip())
    return _speech_key(text)


def _npc_line_copies_player_utterance(line_text: str, player_text: str) -> bool:
    line_key = _speech_key(line_text)
    if line_key in _ALLOWED_NPC_ECHOES or len(line_key) < 8:
        return False
    player_key = _player_spoken_text_key(player_text)
    if not player_key:
        return False
    return line_key == player_key or (len(line_key.split()) >= 2 and line_key in player_key)


def _is_player_speaker(state: WorldState, speaker: str) -> bool:
    return speaker.strip().casefold() in player_aliases_for_state(state)


def _input_has_immediate_danger(player_text: str, state: WorldState) -> bool:
    text = _norm(" ".join([player_text, state.last_scene]))
    return bool(_IMMEDIATE_DANGER.search(text))


def _proposal_drift(player_action: str, proposed_action: str, player_text: str, state: WorldState) -> bool:
    if player_action in PASSIVE_ACTIONS and proposed_action in {
        "social",
        "deception",
        "seduction",
        "attack",
        "stealth",
        "investigate",
        "physical",
        "confront",
    }:
        return not _input_has_immediate_danger(player_text, state)
    if player_action == "waking" and proposed_action != "other":
        return not _input_has_immediate_danger(player_text, state)
    return False


def validate_check_proposal_player_agency(
    state: WorldState,
    pack: WorldPack,
    proposal: CheckProposal,
    player_text: str,
) -> ValidationReport:
    del pack
    player_action = classify_player_input_action(player_text)
    proposed_action = classify_proposed_player_action(proposal)
    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []
    if _proposal_drift(player_action, proposed_action, player_text, state):
        message = (
            "autonomia player: proposta di prova altera l'azione dichiarata "
            f"({player_action} -> {proposed_action})"
        )
        problems.append(message)
        errors.append(
            ValidationErrorDetail(
                "player_action_semantic_drift",
                "check.action_kind",
                message,
                {
                    "player_input_action": player_action,
                    "proposed_player_action": proposed_action,
                    "player_text": player_text,
                },
            )
        )
    return ValidationReport(problems, errors)


def validate_scene_player_agency(
    state: WorldState,
    pack: WorldPack,
    scene: FinalScene,
    player_text: str,
) -> ValidationReport:
    del pack
    player_action = classify_player_input_action(player_text)
    quoted = {_norm(q) for q in _quoted_player_texts(player_text)}
    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []

    for index, line in enumerate(scene.dialogue):
        if _is_player_speaker(state, line.speaker) and _norm(line.text) not in quoted:
            message = "autonomia player: dialogo del player inventato dal GM"
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    "invented_player_dialogue",
                    f"dialogue[{index}]",
                    message,
                    {"speaker": line.speaker, "text": line.text},
                )
            )
        elif (
            player_action == "speaking"
            and not _is_player_speaker(state, line.speaker)
            and str(line.to or "").strip().casefold() in player_aliases_for_state(state)
            and _npc_line_copies_player_utterance(line.text, player_text)
        ):
            message = "autonomia player: dialogo NPC copia l'input del player invertendo i ruoli"
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    "npc_dialogue_copies_player_input",
                    f"dialogue[{index}]",
                    message,
                    {"speaker": line.speaker, "text": line.text, "player_text": player_text},
                )
            )

    scene_text = _norm(" ".join([scene.narration, *[str(i) for i in scene.intentions]]))
    if player_action in PASSIVE_ACTIONS:
        intention_match = _VOLUNTARY_NARRATION[-1].search(scene_text)
        if intention_match:
            message = "autonomia player: la scena attribuisce al player un'azione o intenzione volontaria non dichiarata"
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    "invented_player_intention",
                    "scene.narration",
                    message,
                    {"matched": intention_match.group(0), "player_input_action": player_action},
                )
            )
        for pattern in _VOLUNTARY_NARRATION:
            if pattern is _VOLUNTARY_NARRATION[-1]:
                continue
            match = pattern.search(scene_text)
            if not match:
                continue
            message = "autonomia player: la scena attribuisce al player un'azione o intenzione volontaria non dichiarata"
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    "player_action_semantic_drift",
                    "scene.narration",
                    message,
                    {"matched": match.group(0), "player_input_action": player_action},
                )
            )
            break

    if scene.visual is not None and player_action == "waking":
        visual_text = " ".join([scene.visual.summary, scene.visual.visual_en, *scene.visual.tags_en])
        lower_visual = visual_text.lower()
        drift = bool(_VISUAL_DRIFT.search(visual_text))
        if "paglia" in _norm(player_text) and not _BED_TERMS_EN.search(visual_text):
            drift = True
        if not _WAKING_TERMS_EN.search(visual_text) and "risvegl" in _norm(player_text):
            drift = True
        if drift:
            message = "autonomia player: visual_moment_drift rispetto al risveglio dichiarato"
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    "visual_moment_drift",
                    "visual.visual_en",
                    message,
                    {"visual_text": lower_visual, "player_input_action": player_action},
                )
            )

    return ValidationReport(problems, errors)


def player_agency_diagnostics(
    state: WorldState,
    player_text: str,
    *,
    proposal: CheckProposal | ConfrontProposal | None = None,
    scene: FinalScene | None = None,
) -> PlayerAgencyDiagnostics:
    player_action = classify_player_input_action(player_text)
    proposed_action = classify_proposed_player_action(proposal)
    proposal_report = (
        validate_check_proposal_player_agency(state, None, proposal, player_text)
        if isinstance(proposal, CheckProposal)
        else ValidationReport()
    )
    scene_report = (
        validate_scene_player_agency(state, None, scene, player_text)
        if scene is not None
        else ValidationReport()
    )
    problems = [*proposal_report.problems, *scene_report.problems]
    codes = {error.code for error in [*proposal_report.errors, *scene_report.errors]}
    return PlayerAgencyDiagnostics(
        player_input_action=player_action,
        proposed_player_action=proposed_action,
        player_agency_violation=bool(problems),
        invented_player_dialogue="invented_player_dialogue" in codes
        or "npc_dialogue_copies_player_input" in codes,
        invented_player_intention="invented_player_intention" in codes,
        action_semantic_drift="player_action_semantic_drift" in codes
        or "player_action_semantic_drift" in codes,
        visual_moment_drift="visual_moment_drift" in codes,
        problems=problems,
    )
