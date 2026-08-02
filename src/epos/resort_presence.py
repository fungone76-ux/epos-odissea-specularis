"""Canonical Resort NPC presence and participation helpers."""

from __future__ import annotations

from typing import Any

from .entity_ids import normalize_entity_id


def _value(item: Any, field: str) -> str:
    if isinstance(item, dict):
        return str(item.get(field, "") or "")
    return str(getattr(item, field, "") or "")


def _same_location_npcs(state) -> list[str]:
    return [
        npc_id
        for npc_id, npc in state.npcs.items()
        if str(getattr(npc, "location_id", "")) == str(state.location_id)
    ]


def _mentioned_candidates(state, candidates: list[str], *texts: str) -> list[str]:
    haystack = " ".join(str(text or "") for text in texts).casefold()
    found: list[str] = []
    for npc_id in candidates:
        npc = state.npcs[npc_id]
        names = {str(npc_id).casefold(), str(getattr(npc, "name", "")).casefold()}
        full_name = str(getattr(npc, "name", "")).strip().casefold()
        if full_name:
            names.add(full_name.split()[0])
        if any(name and name in haystack for name in names):
            found.append(npc_id)
    return found


def reconcile_resort_presence(state, player_text: str = "") -> str | None:
    """Repair one stale presence flag without inventing a crowd."""

    if any(npc_id in state.npcs for npc_id in state.present_npc_ids()):
        return None

    candidates = _same_location_npcs(state)
    target: str | None = None
    if len(candidates) == 1:
        target = candidates[0]
    elif candidates:
        mentioned = _mentioned_candidates(
            state,
            candidates,
            getattr(state, "last_scene", ""),
            player_text,
        )
        if len(mentioned) == 1:
            target = mentioned[0]

    if target is None:
        return None

    state.npcs[target].present = True
    return target


def scene_participant_candidates(state, scene) -> list[str]:
    candidates: list[str] = []

    for line in getattr(scene, "dialogue", []):
        resolved = normalize_entity_id(_value(line, "speaker"), state, "resort_dialogue")
        if resolved in state.npcs:
            candidates.append(resolved)

    for action in getattr(scene, "npc_actions", []):
        resolved = normalize_entity_id(_value(action, "npc_id"), state, "resort_action")
        if resolved in state.npcs:
            candidates.append(resolved)

    for event in getattr(scene, "initiatives", []):
        resolved = normalize_entity_id(_value(event, "source"), state, "resort_initiative")
        if resolved in state.npcs:
            candidates.append(resolved)

    visual = getattr(scene, "visual", None)
    if visual is not None:
        for field in (
            "speaker_character",
            "actor_character",
            "reactor_character",
            "focus_character",
        ):
            resolved = normalize_entity_id(
                getattr(visual, field, ""), state, f"resort_visual_{field}"
            )
            if resolved in state.npcs:
                candidates.append(resolved)
        for raw in list(getattr(visual, "visible_characters", []) or []):
            resolved = normalize_entity_id(raw, state, "resort_visible")
            if resolved in state.npcs:
                candidates.append(resolved)

    unique: list[str] = []
    for npc_id in candidates:
        if npc_id not in unique:
            unique.append(npc_id)
    return unique


def scene_has_real_npc_participation(state, scene) -> bool:
    present = set(state.present_npc_ids())
    if not present:
        reconcile_resort_presence(state)
        present = set(state.present_npc_ids())

    return any(npc_id in present for npc_id in scene_participant_candidates(state, scene))
