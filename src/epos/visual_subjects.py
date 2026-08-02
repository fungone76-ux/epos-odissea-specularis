"""Deterministic subject selection helpers for visual contracts."""

from __future__ import annotations

from .contract import VisualMoment


def _first_present(candidates: list[str], present: set[str]) -> str | None:
    for candidate in candidates:
        if candidate and candidate in present:
            return candidate
    return None


def _focus_for_policy(
    visual: VisualMoment, present: set[str]
) -> tuple[str, str]:
    moment_type = visual.moment_type.strip().lower()
    if moment_type == "speech":
        speaker = _first_present([visual.speaker_character], present)
        if speaker:
            return speaker, "speaker"
    if moment_type == "action":
        actor = _first_present([visual.actor_character], present)
        if actor:
            return actor, "actor"
    if moment_type == "reaction":
        reactor = _first_present([visual.reactor_character], present)
        if reactor:
            return reactor, "reactor"

    explicit = _first_present(
        [
            visual.actor_character,
            visual.speaker_character,
            visual.reactor_character,
            visual.focus_character,
        ],
        present,
    )
    if explicit:
        return explicit, "explicit_visual_focus"
    return "player", "fallback_player"


def _validated_intimate_participants(
    visual: VisualMoment, present: set[str]
) -> tuple[list[str], str]:
    participants = [
        c for c in visual.multi_character_participants if c in present
    ]
    if not participants:
        participants = [c for c in visual.visible_characters if c in present]
    participants = list(dict.fromkeys(participants))
    if (
        visual.intimate_shared_moment
        and visual.moment_type.strip().lower() == "intimate"
        and len(participants) >= 2
    ):
        return participants, visual.multi_character_reason or "intimate_shared_moment"
    return [], "not_validated_intimate_shared_moment"
