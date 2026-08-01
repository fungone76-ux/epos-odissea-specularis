"""Repairs derived from the complete Resort save audit.

The patch is deliberately conservative.  It repairs only unambiguous state
and scene inconsistencies found in the recorded turns:

* a single NPC located with the player but carrying a stale ``present`` flag;
* schema placeholder ``npc_id`` surviving in visual/scene fields;
* genuine NPC reactions expressed only by the visual actor/focus;
* modern Resort garments misclassified as nudity.
"""

from __future__ import annotations

from typing import Any

from . import resort_runtime_patches
from .models import FOOTWEAR_TERMS, LOWER_CLOTHING_TERMS, TORSO_CLOTHING_TERMS

_INSTALLED = False


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
    """Repair one stale presence flag without inventing a crowd.

    Presence is changed only when no NPC is currently present and exactly one
    same-location NPC is unambiguous, either because it is the sole candidate
    or because it is the sole NPC named by the last scene/current input.
    """

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


def _scene_participant_candidates(state, scene) -> list[str]:
    candidates: list[str] = []

    for line in getattr(scene, "dialogue", []):
        raw = _value(line, "speaker")
        resolved = resort_runtime_patches.entity_ids.normalize_entity_id(
            raw, state, "save_audit_dialogue"
        )
        if resolved in state.npcs:
            candidates.append(resolved)

    for action in getattr(scene, "npc_actions", []):
        raw = _value(action, "npc_id")
        resolved = resort_runtime_patches.entity_ids.normalize_entity_id(
            raw, state, "save_audit_action"
        )
        if resolved in state.npcs:
            candidates.append(resolved)

    for event in getattr(scene, "initiatives", []):
        raw = _value(event, "source")
        resolved = resort_runtime_patches.entity_ids.normalize_entity_id(
            raw, state, "save_audit_initiative"
        )
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
            raw = str(getattr(visual, field, "") or "")
            resolved = resort_runtime_patches.entity_ids.normalize_entity_id(
                raw, state, f"save_audit_visual_{field}"
            )
            if resolved in state.npcs:
                candidates.append(resolved)
        for raw in list(getattr(visual, "visible_characters", []) or []):
            resolved = resort_runtime_patches.entity_ids.normalize_entity_id(
                raw, state, "save_audit_visible"
            )
            if resolved in state.npcs:
                candidates.append(resolved)

    unique: list[str] = []
    for npc_id in candidates:
        if npc_id not in unique:
            unique.append(npc_id)
    return unique


def _placeholder_target_with_stale_presence(state, scene) -> str | None:
    """Resolve ``npc_id`` even when the persisted present flag is stale."""

    original = _ORIGINAL_PLACEHOLDER_TARGET(state, scene)
    if original is not None:
        return original

    participants = _scene_participant_candidates(state, scene)
    if len(participants) == 1:
        return participants[0]

    same_location = _same_location_npcs(state)
    visual = getattr(scene, "visual", None)
    visual_text = ""
    if visual is not None:
        visual_text = " ".join(
            [
                str(getattr(visual, "summary", "") or ""),
                str(getattr(visual, "visual_en", "") or ""),
                *[str(tag) for tag in list(getattr(visual, "tags_en", []) or [])],
            ]
        )
    mentioned = _mentioned_candidates(
        state,
        same_location,
        getattr(scene, "narration", ""),
        visual_text,
        getattr(state, "last_scene", ""),
    )
    if len(mentioned) == 1:
        state.npcs[mentioned[0]].present = True
        return mentioned[0]
    if len(same_location) == 1:
        state.npcs[same_location[0]].present = True
        return same_location[0]
    return None


def _scene_has_real_npc_participation(state, scene) -> bool:
    present = set(state.present_npc_ids())
    if not present:
        reconcile_resort_presence(state)
        present = set(state.present_npc_ids())

    for npc_id in _scene_participant_candidates(state, scene):
        if npc_id in present:
            return True
    return False


def install_resort_save_audit_patch() -> None:
    global _INSTALLED, _ORIGINAL_PLACEHOLDER_TARGET
    if _INSTALLED:
        return

    # Explicit compound/full-body garments found in the recorded saves.
    TORSO_CLOTHING_TERMS.update(
        {
            "travel suit",
            "luxury travel suit",
            "bodycon blazer mini dress",
            "attendant mini dress",
            "hostess micro dress",
            "maid mini dress",
            "beach sarong",
        }
    )
    LOWER_CLOTHING_TERMS.update(
        {
            "travel suit",
            "luxury travel suit",
            "bodycon blazer mini dress",
            "attendant mini dress",
            "hostess micro dress",
            "maid mini dress",
            "beach sarong",
        }
    )
    FOOTWEAR_TERMS.update({"high heels", "delicate high heels", "black stilettos"})

    _ORIGINAL_PLACEHOLDER_TARGET = resort_runtime_patches._placeholder_target
    resort_runtime_patches._placeholder_target = _placeholder_target_with_stale_presence

    from . import resort_playable_turn_service as playable

    original_has_action = playable._scene_has_present_npc_action

    def patched_has_action(state, scene) -> bool:
        return original_has_action(state, scene) or _scene_has_real_npc_participation(
            state, scene
        )

    playable._scene_has_present_npc_action = patched_has_action

    original_play = playable.ResortPlayableTurnService.play

    def patched_play(self, state, player_text: str):
        reconcile_resort_presence(state, player_text)
        return original_play(self, state, player_text)

    playable.ResortPlayableTurnService.play = patched_play
    _INSTALLED = True
