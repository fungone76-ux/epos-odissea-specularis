"""Conservative runtime repairs shared by the Resort production path.

The LLM occasionally copies the schema placeholder ``npc_id`` into structured
visual fields. This module resolves that placeholder only when the scene has
one unambiguous present NPC, speaker, actor or initiative source. It also
extends the generic outfit vocabulary with modern Resort garments so canonical
nudity state is not inferred from an incomplete ancient/fantasy vocabulary.

Dialogue ``speaker`` is display-facing text and must remain readable. Only
machine-facing fields such as ``to``, targets and visual entity references are
canonicalized to internal ids.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from . import entity_ids
from .entity_ids import EntityNormalizationEntry, EntityNormalizationResult
from .models import FOOTWEAR_TERMS, LOWER_CLOTHING_TERMS, TORSO_CLOTHING_TERMS

_INSTALLED = False
_ORIGINAL_NORMALIZE_SCENE = entity_ids.normalize_scene_entity_ids
_PLACEHOLDER = "npc_id"


def _is_placeholder(value: Any) -> bool:
    return str(value or "").strip().casefold() == _PLACEHOLDER


def _present_npc(state, value: Any) -> str | None:
    normalized = entity_ids.normalize_entity_id(value, state, "placeholder_candidate")
    return normalized if normalized in state.npcs and state.npcs[normalized].present else None


def _placeholder_target(state, scene) -> str | None:
    """Resolve the scene's concrete NPC using authoritative participation order."""

    for line in scene.dialogue:
        candidate = _present_npc(state, getattr(line, "speaker", ""))
        if candidate:
            return candidate

    for action in scene.npc_actions:
        candidate = _present_npc(state, action.get("npc_id", ""))
        if candidate:
            return candidate

    for event in scene.initiatives:
        candidate = _present_npc(state, getattr(event, "source", ""))
        if candidate:
            return candidate

    present = [npc_id for npc_id in state.present_npc_ids() if npc_id in state.npcs]
    return present[0] if len(present) == 1 else None


def _placeholder_entry(path: str, target: str, phase: str, attempt: int, source_payload: str):
    return EntityNormalizationEntry(
        field_path=path,
        original_value=_PLACEHOLDER,
        normalized_value=target,
        alias_rule="scene_placeholder_npc_id",
        phase=phase,
        attempt=attempt,
        source_payload=source_payload,
    )


def _repair_scene_placeholders(
    state,
    scene,
    *,
    phase: str,
    attempt: int,
    source_payload: str,
):
    target = _placeholder_target(state, scene)
    if target is None:
        return scene, []

    entries: list[EntityNormalizationEntry] = []

    intentions = []
    for index, item in enumerate(scene.intentions):
        mapped = dict(item)
        if _is_placeholder(mapped.get("npc_id")):
            mapped["npc_id"] = target
            entries.append(
                _placeholder_entry(
                    f"intentions[{index}].npc_id", target, phase, attempt, source_payload
                )
            )
        intentions.append(mapped)

    npc_actions = []
    for index, item in enumerate(scene.npc_actions):
        mapped = dict(item)
        if _is_placeholder(mapped.get("npc_id")):
            mapped["npc_id"] = target
            entries.append(
                _placeholder_entry(
                    f"npc_actions[{index}].npc_id", target, phase, attempt, source_payload
                )
            )
        npc_actions.append(mapped)

    visual = scene.visual
    if visual is not None:
        updates: dict[str, Any] = {}
        for field_name in (
            "focus_character",
            "speaker_character",
            "actor_character",
            "reactor_character",
        ):
            if _is_placeholder(getattr(visual, field_name)):
                updates[field_name] = target
                entries.append(
                    _placeholder_entry(
                        f"visual.{field_name}", target, phase, attempt, source_payload
                    )
                )

        for field_name in ("visible_characters", "multi_character_participants"):
            values = list(getattr(visual, field_name))
            changed = False
            for index, value in enumerate(values):
                if _is_placeholder(value):
                    values[index] = target
                    changed = True
                    entries.append(
                        _placeholder_entry(
                            f"visual.{field_name}[{index}]",
                            target,
                            phase,
                            attempt,
                            source_payload,
                        )
                    )
            if changed:
                updates[field_name] = values

        if updates:
            visual = replace(visual, **updates)

    if not entries:
        return scene, []
    return replace(scene, intentions=intentions, npc_actions=npc_actions, visual=visual), entries


def _restore_display_speakers(original_scene, normalized_scene):
    """Keep dialogue speaker labels display-facing while retaining normalized ``to`` ids."""

    if len(original_scene.dialogue) != len(normalized_scene.dialogue):
        return normalized_scene

    dialogue = [
        replace(normalized_line, speaker=original_line.speaker)
        for original_line, normalized_line in zip(
            original_scene.dialogue,
            normalized_scene.dialogue,
            strict=True,
        )
    ]
    return replace(normalized_scene, dialogue=dialogue)


def normalize_scene_entity_ids_with_placeholders(
    state,
    scene,
    *,
    phase: str,
    attempt: int = 0,
    source_payload: str = "scene",
):
    repaired, placeholder_entries = _repair_scene_placeholders(
        state,
        scene,
        phase=phase,
        attempt=attempt,
        source_payload=source_payload,
    )
    result = _ORIGINAL_NORMALIZE_SCENE(
        state,
        repaired,
        phase=phase,
        attempt=attempt,
        source_payload=source_payload,
    )

    restored_scene = _restore_display_speakers(repaired, result.value)
    filtered_entries = [
        entry
        for entry in result.entries
        if not entry.field_path.startswith("dialogue[")
        or not entry.field_path.endswith("].speaker")
    ]

    return EntityNormalizationResult(
        restored_scene,
        [*placeholder_entries, *filtered_entries],
    )


def install_resort_runtime_patches() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # Full-body / torso Resort garments.
    TORSO_CLOTHING_TERMS.update(
        {
            "bikini",
            "blazer",
            "bodysuit",
            "bra",
            "camisole",
            "corset",
            "lingerie",
            "one piece",
            "slip",
            "suit",
            "swimsuit",
            "swimwear",
            "uniform",
        }
    )
    # Full-body / lower-body Resort garments and coverings.
    LOWER_CLOTHING_TERMS.update(
        {
            "bikini",
            "bottoms",
            "briefs",
            "lingerie",
            "micro dress",
            "mini dress",
            "one piece",
            "panties",
            "sarong",
            "slip",
            "suit",
            "swimsuit",
            "swimwear",
            "uniform",
        }
    )
    FOOTWEAR_TERMS.update(
        {
            "heels",
            "loafers",
            "pumps",
            "stilettos",
            "wedges",
        }
    )

    entity_ids.normalize_scene_entity_ids = normalize_scene_entity_ids_with_placeholders
    _INSTALLED = True
