"""Scene visual and outfit consistency validators."""

from __future__ import annotations

import re
from typing import Any

from .contract import FinalScene, Mutation
from .models import Outfit, WorldState, outfit_state
from .validator_common import ValidationErrorDetail, _add_problem


def _scene_implies_full_nudity(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "completely nude",
            "fully naked",
            "no clothing",
            "no clothes",
            "no armor",
            "no dress",
            "no chiton",
            "without clothing",
            "without clothes",
            "bare-skinned",
            "completamente nuda",
            "nuda completa",
        )
    )


def _scene_implies_topless(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in ("topless", "bare chest", "bare breasts", "no top", "no bra")
    )


def _scene_implies_bottomless(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in ("bottomless", "no lower clothing", "no skirt", "no panties")
    )


def _outfit_after_scene(state: WorldState, target: str, mutations: list[Mutation]) -> Outfit | None:
    character = state.player if target == "player" else state.npcs.get(target)
    if character is None:
        return None
    outfit = Outfit(
        worn=list(character.outfit.worn),
        removed=list(character.outfit.removed),
        revision=character.outfit.revision,
    )
    for mutation in mutations:
        if mutation.target != target:
            continue
        item = str(mutation.payload.get("item", ""))
        if mutation.type == "outfit_remove":
            outfit.remove_item(item)
        elif mutation.type == "outfit_wear":
            outfit.wear(item)
    return outfit


def _mentions_unworn_clothing(text: str, state_after: dict[str, Any]) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in ("no chiton", "no armor", "no dress", "no clothing")):
        return False
    worn_text = " ".join(state_after["worn_items"]).lower()
    clothing_words = ("chiton", "armor", "dress", "robe", "peplos", "himation", "skirt", "sandals")
    if not any(word in lowered for word in clothing_words):
        return False
    if any(word in worn_text and word in lowered for word in clothing_words):
        return False
    return any(
        phrase in lowered
        for phrase in ("wearing", "wears", "dressed in", "clad in", " in a ", " in her ")
    )


def _validate_player_outfit_visual_consistency(
    state: WorldState,
    scene: FinalScene,
    problems: list[str],
    errors: list[ValidationErrorDetail],
) -> None:
    if scene.visual is None or "player" not in scene.visual.visible_characters:
        return
    outfit_after = _outfit_after_scene(state, "player", scene.mutations)
    if outfit_after is None:
        return
    current = outfit_state(outfit_after)
    text = " ".join(
        [
            scene.narration,
            scene.visual.summary,
            scene.visual.visual_en,
            *scene.visual.tags_en,
        ]
    )
    if _scene_implies_full_nudity(text) and current["nudity_mode"] != "fully_nude":
        _add_problem(
            problems,
            errors,
            "visual_outfit_state_mismatch",
            "visual.visual_en",
            "visual descrive nudita completa ma lo stato outfit canonico conserva abiti torso/lower",
            outfit_state=current,
        )
    elif _scene_implies_topless(text) and current["torso_slot"]:
        _add_problem(
            problems,
            errors,
            "visual_outfit_state_mismatch",
            "visual.visual_en",
            "visual descrive topless ma lo stato outfit canonico conserva abiti torso",
            outfit_state=current,
        )
    elif _scene_implies_bottomless(text) and current["lower_body_slot"]:
        _add_problem(
            problems,
            errors,
            "visual_outfit_state_mismatch",
            "visual.visual_en",
            "visual descrive bottomless ma lo stato outfit canonico conserva abiti lower-body",
            outfit_state=current,
        )
    elif current["nudity_mode"] == "fully_nude" and _mentions_unworn_clothing(text, current):
        _add_problem(
            problems,
            errors,
            "visual_outfit_state_mismatch",
            "visual.visual_en",
            "visual reintroduce abiti non presenti nello stato outfit canonico",
            outfit_state=current,
        )


def _strip_place_owner_mentions(text: str) -> str:
    """Remove NPC-name mentions that identify a place/object, not a visible body."""
    patterns = [
        r"\bpolyphemus['\u2019]?\s+cave\b",
        r"\bcave\s+of\s+polyphemus\b",
        r"\bpolifemo['\u2019]?\s+cave\b",
        r"\bcave\s+of\s+polifemo\b",
        r"\bcaverna\s+di\s+polifemo\b",
        r"\bgrotta\s+di\s+polifemo\b",
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _validate_visible_character_text(
    state: WorldState,
    scene: FinalScene,
    problems: list[str],
    errors: list[ValidationErrorDetail],
) -> None:
    if scene.visual is None:
        return
    visible = set(scene.visual.visible_characters)
    text = " ".join([scene.visual.summary, scene.visual.visual_en, *scene.visual.tags_en])
    text = _strip_place_owner_mentions(text)
    lowered = text.casefold()
    conflicts: list[str] = []
    for npc_id, npc in state.npcs.items():
        if npc_id in visible:
            continue
        names = {npc_id.casefold(), str(npc.name).casefold()}
        if npc_id == "polifemo":
            names.update({"polyphemus", "cyclops", "giant", "gigante"})
        if any(re.search(rf"\b{re.escape(name)}\b", lowered) for name in names if name):
            conflicts.append(npc_id)
    if conflicts:
        _add_problem(
            problems,
            errors,
            "visible_character_text_conflict",
            "visual.visual_en",
            "visual descrive un secondo personaggio non autorizzato da visible_characters",
            visible_characters=list(scene.visual.visible_characters),
            conflicts=conflicts,
        )
