"""Contextual narrative intensity policy.

The renderer and validators do not decide prose tone. This module derives a
small, inspectable policy for the GM prompt and turn diagnostics from runtime
state, player intent, relationships, outcome, and scene metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .contract import CheckProposal, ConfrontProposal, FinalScene
from .models import WorldState, outfit_state
from .rules import Roll
from .worldpack import WorldPack

NARRATIVE_INTENSITIES = (
    "neutral",
    "suggestive",
    "sensual",
    "erotic",
    "explicit_adult",
)

CONSENT_STATES = ("consented", "not_consented", "unknown", "not_applicable")

_RANK = {level: index for index, level in enumerate(NARRATIVE_INTENSITIES)}

_FLIRT_TERMS = (
    "flirt",
    "ammicco",
    "provoco",
    "provocazione",
    "seduco",
    "sussurro",
    "complimento",
    "desiderio",
    "desidero",
)
_ROMANCE_TERMS = (
    "bacio",
    "baciare",
    "abbraccio",
    "carezza",
    "carezzo",
    "tensione romantica",
    "tenerezza",
    "letto d'ulivo",
)
_NUDITY_TERMS = (
    "nuda",
    "nudo",
    "nude",
    "naked",
    "topless",
    "bottomless",
    "senza vestiti",
    "senza abiti",
    "mi spoglio",
    "mi svesto",
)
_INTIMATE_TERMS = (
    "intimo",
    "intimita",
    "intimità",
    "tocca",
    "tocco",
    "accarezzo",
    "pelle",
    "corpo contro",
)
_EXPLICIT_REQUEST_TERMS = (
    "sesso",
    "scopare",
    "fare l'amore",
    "fare l amore",
    "amplesso",
    "rapporto sessuale",
    "possiedo",
    "mi possiede",
)
_CONSENT_TERMS = (
    "consensuale",
    "consenso",
    "acconsento",
    "acconsente",
    "lo invito",
    "la invito",
    "mi invita",
    "vuole anche",
    "ricambia",
    "desidera anche",
    "di comune accordo",
    "entrambi vogliamo",
    "entrambi desideriamo",
)
_DENIAL_TERMS = (
    "senza consenso",
    "non vuole",
    "rifiuta",
    "rifiuto",
    "costringo",
    "forzo",
    "obbligo",
    "contro la sua volonta",
    "contro la sua volontà",
)
_COMBAT_TERMS = (
    "combatto",
    "attacco",
    "colpisco",
    "uccido",
    "ferisco",
    "lotta",
    "duello",
    "sangue",
)
_FEAR_OR_PAIN_TERMS = (
    "paura",
    "terrorizz",
    "dolore",
    "ferita",
    "soffre",
    "piange dal dolore",
)
_INCAPABLE_TERMS = (
    "incosciente",
    "svenut",
    "dorme",
    "addormentat",
    "stordit",
    "ubriac",
    "drogat",
    "paralizzat",
    "incapace",
)
_RESTRAINT_TERMS = (
    "immobilizz",
    "legat",
    "prigion",
    "catene",
    "vincolat",
)


@dataclass(frozen=True)
class NarrativePolicy:
    narrative_intensity: str
    intimacy_detected: bool
    consent_state: str
    adult_participants_verified: bool
    intensity_reasons: list[str] = field(default_factory=list)
    intensity_blockers: list[str] = field(default_factory=list)
    requested_tone: str = "neutral"
    applied_tone: str = "neutral"
    tone_changed_during_retry: bool = False
    participant_ids: list[str] = field(default_factory=list)
    base_prompt_athletic_body_present: bool = False
    base_prompt_athletic_body_count: int = 0
    nudity_only_signal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "narrative_intensity": self.narrative_intensity,
            "narrative_intensity_before": self.requested_tone,
            "narrative_intensity_after": self.applied_tone,
            "intimacy_detected": self.intimacy_detected,
            "consent_state": self.consent_state,
            "adult_participants_verified": self.adult_participants_verified,
            "intensity_reasons": list(self.intensity_reasons),
            "intensity_blockers": list(self.intensity_blockers),
            "requested_tone": self.requested_tone,
            "applied_tone": self.applied_tone,
            "tone_changed_during_retry": self.tone_changed_during_retry,
            "participant_ids": list(self.participant_ids),
            "base_prompt_athletic_body_present": self.base_prompt_athletic_body_present,
            "base_prompt_athletic_body_count": self.base_prompt_athletic_body_count,
            "nudity_only_signal": self.nudity_only_signal,
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


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _max_level(*levels: str) -> str:
    return max(levels, key=lambda level: _RANK[level])


def _clamp(level: str, maximum: str) -> str:
    return level if _RANK[level] <= _RANK[maximum] else maximum


def _scene_text(scene: FinalScene | None) -> str:
    if scene is None:
        return ""
    parts = [scene.narration]
    parts.extend(line.text for line in scene.dialogue)
    parts.extend(line.speaker for line in scene.dialogue)
    parts.extend(str(line.to or "") for line in scene.dialogue)
    if scene.visual is not None:
        parts.extend(
            [
                scene.visual.summary,
                scene.visual.moment_type,
                scene.visual.visual_en,
                scene.visual.multi_character_reason,
                *scene.visual.tags_en,
            ]
        )
    return " ".join(parts)


def _participants(
    state: WorldState,
    scene: FinalScene | None,
    proposal: CheckProposal | ConfrontProposal | None,
    text: str = "",
) -> list[str]:
    ids: list[str] = ["player"]
    if proposal is not None:
        if isinstance(proposal, CheckProposal):
            ids.extend(proposal.target_ids)
        else:
            ids.append(proposal.target_id)
    if scene is not None:
        if scene.visual is not None:
            ids.extend(scene.visual.visible_characters)
            ids.extend(scene.visual.multi_character_participants)
            for value in (
                scene.visual.focus_character,
                scene.visual.speaker_character,
                scene.visual.actor_character,
                scene.visual.reactor_character,
            ):
                if value:
                    ids.append(value)
        for line in scene.dialogue:
            if line.speaker == "player":
                ids.append("player")
            if line.to:
                ids.append(line.to)
        for mutation in scene.mutations:
            if mutation.target != "world":
                ids.append(mutation.target)
    lowered = _norm(text)
    for npc_id, npc in state.npcs.items():
        if npc_id.casefold() in lowered or (npc.name and _norm(npc.name) in lowered):
            ids.append(npc_id)
    return [cid for cid in dict.fromkeys(ids) if cid == "player" or cid in state.npcs]


def _all_adults(state: WorldState, pack: WorldPack, participant_ids: list[str]) -> bool:
    for cid in participant_ids:
        if cid == "player":
            if not state.player.adult_age:
                return False
            continue
        canon = pack.npc_canon.get(cid)
        if canon is None or canon.age < 18:
            return False
    return True


def _relationship_reasons(state: WorldState, participant_ids: list[str]) -> list[str]:
    reasons: list[str] = []
    for cid in participant_ids:
        if cid == "player":
            continue
        rel = state.npcs.get(cid) and state.npcs[cid].relationships.get("player")
        if rel is None:
            continue
        if rel.attraction >= 50:
            reasons.append(f"{cid}:high_attraction")
        elif rel.attraction >= 20:
            reasons.append(f"{cid}:mutual_tension_signal")
        if rel.trust >= 20:
            reasons.append(f"{cid}:trust_signal")
        if rel.fear > 20 or rel.resentment > 30:
            reasons.append(f"{cid}:relationship_blocker")
    return reasons


def _outfit_nudity_reason(state: WorldState) -> str:
    current = outfit_state(state.player.outfit)
    if current["nudity_mode"] == "fully_nude":
        return "player_fully_nude_state"
    if current["nudity_mode"] in ("topless", "bottomless"):
        return f"player_{current['nudity_mode']}_state"
    return ""


def _base_prompt_athletic_count(pack: WorldPack) -> int:
    sheet = pack.visual_sheets.get("player")
    if sheet is None:
        return 0
    return len(re.findall(r"\bathletic body\b", sheet.base_prompt, re.IGNORECASE))


def derive_narrative_policy(
    state: WorldState,
    pack: WorldPack,
    player_text: str,
    *,
    scene: FinalScene | None = None,
    proposal: CheckProposal | ConfrontProposal | None = None,
    roll: Roll | None = None,
    phase: str = "turn",
    previous: NarrativePolicy | None = None,
) -> NarrativePolicy:
    text = _norm(" ".join([player_text, _scene_text(scene)]))
    participants = _participants(state, scene, proposal, player_text)
    reasons: list[str] = []
    blockers: list[str] = []

    requested = "neutral"
    if _has_any(text, _FLIRT_TERMS):
        requested = _max_level(requested, "suggestive")
        reasons.append("flirt_or_provocation")
    if _has_any(text, _ROMANCE_TERMS):
        requested = _max_level(requested, "sensual")
        reasons.append("romantic_or_physical_tenderness")
    nudity_signal = _has_any(text, _NUDITY_TERMS)
    if _has_any(text, _INTIMATE_TERMS):
        requested = _max_level(requested, "erotic")
        reasons.append("intimate_contact_signal")
    if _has_any(text, _EXPLICIT_REQUEST_TERMS):
        requested = _max_level(requested, "explicit_adult")
        reasons.append("explicit_adult_request")
    if proposal is not None and getattr(proposal, "skill", "") == "eros":
        requested = _max_level(requested, "sensual")
        reasons.append("eros_skill")
    if isinstance(proposal, CheckProposal) and proposal.action_kind == "intimate":
        requested = _max_level(requested, "erotic")
        reasons.append("intimate_action_kind")
    if scene and scene.visual and scene.visual.moment_type == "intimate":
        requested = _max_level(requested, "erotic")
        reasons.append("visual_moment_type_intimate")
    if scene and scene.visual and scene.visual.intimate_shared_moment:
        requested = _max_level(requested, "erotic")
        reasons.append("intimate_shared_moment")

    nudity_reason = _outfit_nudity_reason(state)
    nudity_only_signal = bool(nudity_signal or nudity_reason)

    relationship_reasons = _relationship_reasons(state, participants)
    reasons.extend(r for r in relationship_reasons if not r.endswith("relationship_blocker"))
    blockers.extend(r for r in relationship_reasons if r.endswith("relationship_blocker"))
    if (
        any("mutual_tension_signal" in r for r in relationship_reasons)
        and _has_any(text, _ROMANCE_TERMS + _FLIRT_TERMS)
    ):
        requested = _max_level(requested, "sensual")
        reasons.append("reciprocal_romantic_tension")

    positive_intimacy_signal = any(
        reason in reasons
        for reason in (
            "flirt_or_provocation",
            "romantic_or_physical_tenderness",
            "intimate_contact_signal",
            "explicit_adult_request",
            "eros_skill",
            "intimate_action_kind",
            "visual_moment_type_intimate",
            "intimate_shared_moment",
            "reciprocal_romantic_tension",
        )
    )
    if nudity_only_signal and not positive_intimacy_signal:
        blockers.extend(["no_intimate_action", "nudity_alone_is_not_intimacy"])

    intimacy_detected = _RANK[requested] >= _RANK["sensual"] and positive_intimacy_signal
    adult_participants_verified = _all_adults(state, pack, participants)
    if not adult_participants_verified:
        blockers.append("non_adult_or_unverified_participant")

    if _has_any(text, _DENIAL_TERMS):
        consent_state = "not_consented"
        blockers.append("consent_denied_or_coercive_intent")
    elif not intimacy_detected:
        consent_state = "not_applicable"
    elif _has_any(text, _CONSENT_TERMS):
        consent_state = "consented"
        reasons.append("explicit_or_reciprocal_consent_signal")
    else:
        consent_state = "unknown"
        blockers.append("consent_unknown")

    if _has_any(text, _COMBAT_TERMS):
        blockers.append("combat_context")
    if _has_any(text, _FEAR_OR_PAIN_TERMS):
        blockers.append("fear_or_pain_context")
    if _has_any(text, _RESTRAINT_TERMS):
        blockers.append("restraint_or_prison_context")
    if _has_any(text, _INCAPABLE_TERMS):
        blockers.append("incapable_to_choose")

    applied = requested
    if "combat_context" in blockers:
        applied = "neutral"
    if any(b in blockers for b in ("fear_or_pain_context", "restraint_or_prison_context", "incapable_to_choose")):
        applied = _clamp(applied, "suggestive")
    if consent_state == "unknown":
        applied = _clamp(applied, "sensual")
    if consent_state == "not_consented":
        applied = _clamp(applied, "suggestive")
    if not adult_participants_verified:
        applied = "neutral"
    if roll is not None:
        outcome = roll.outcome.value
        if outcome == "failure":
            applied = _clamp(applied, "sensual")
            blockers.append("failure_cannot_be_rewritten_as_erotic_success")
        elif outcome == "critical_failure":
            applied = _clamp(applied, "suggestive")
            blockers.append("critical_failure_no_automatic_sexual_violence")
        elif outcome == "partial_success":
            applied = _clamp(applied, "erotic")
            blockers.append("partial_success_preserves_limits")
        elif outcome == "full_success":
            reasons.append("full_success_may_intensify_within_limits")

    if applied == "explicit_adult" and consent_state != "consented":
        applied = "sensual"
    if applied == "explicit_adult" and not adult_participants_verified:
        applied = "neutral"

    count = _base_prompt_athletic_count(pack)
    return NarrativePolicy(
        narrative_intensity=applied,
        intimacy_detected=intimacy_detected,
        consent_state=consent_state,
        adult_participants_verified=adult_participants_verified,
        intensity_reasons=list(dict.fromkeys(reasons)),
        intensity_blockers=list(dict.fromkeys(blockers)),
        requested_tone=requested,
        applied_tone=applied,
        tone_changed_during_retry=(
            previous is not None and previous.applied_tone != applied
        ),
        participant_ids=participants,
        base_prompt_athletic_body_present=count > 0,
        base_prompt_athletic_body_count=count,
        nudity_only_signal=nudity_only_signal and not positive_intimacy_signal,
    )


def narrative_policy_prompt(policy: NarrativePolicy) -> str:
    data = policy.to_dict()
    return (
        "POLICY NARRATIVA CONTESTUALE:\n"
        f"- narrative_intensity applicabile: {data['narrative_intensity']}\n"
        f"- consent_state: {data['consent_state']}\n"
        f"- adult_participants_verified: {data['adult_participants_verified']}\n"
        f"- ragioni: {data['intensity_reasons']}\n"
        f"- limiti/blocker: {data['intensity_blockers']}\n"
        "- Usa questo livello come massimo contestuale, non come obbligo di "
        "erotizzare la scena. Non cambiare visual, outfit, speaker-focus o "
        "multi-character policy in base al tono.\n"
    )
