"""Pure prompt-layer helpers for visual prompt assembly."""

from __future__ import annotations

import re
from typing import Any


_LAYER_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "her",
    "his",
    "in",
    "near",
    "of",
    "on",
    "the",
    "to",
    "with",
}

_OUTFIT_LAYER_WORDS = {
    "aegis",
    "armor",
    "arm",
    "barefoot",
    "belt",
    "bow",
    "bracelets",
    "braziers",
    "chiton",
    "cloak",
    "club",
    "corselet",
    "cups",
    "greaves",
    "helmet",
    "himation",
    "jewelry",
    "leather",
    "loom",
    "pelt",
    "pelts",
    "peplos",
    "quiver",
    "rings",
    "robe",
    "sandals",
    "spear",
    "staff",
    "straps",
    "threads",
    "thighs",
}

_POSE_OR_SCENE_WORDS = {
    "action",
    "angle",
    "background",
    "body",
    "camera",
    "cinematic",
    "cliffs",
    "composition",
    "crossed",
    "distant",
    "full",
    "hands",
    "knees",
    "against",
    "beside",
    "leg",
    "legs",
    "light",
    "looking",
    "pose",
    "resting",
    "rock",
    "seated",
    "shoreline",
    "side",
    "three",
    "view",
    "volcanic",
}

_CLOTHING_OUTFIT_WORDS = {
    "aegis",
    "armor",
    "bracelets",
    "chiton",
    "cloak",
    "corselet",
    "greaves",
    "helmet",
    "himation",
    "jewelry",
    "leather",
    "pelts",
    "peplos",
    "sandals",
}


def _dedupe_chunks(text: str) -> str:
    """Remove duplicate comma-separated prompt chunks while preserving order."""

    seen: set[str] = set()
    kept: list[str] = []
    for chunk in text.split(","):
        norm = " ".join(chunk.lower().split())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        kept.append(chunk.strip())
    return ", ".join(kept)


def _dedupe_layer(text: str) -> str:
    return _dedupe_chunks(text)


def _join_nonempty(parts: list[str]) -> str:
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _LAYER_STOPWORDS and len(token) > 2
    }


def _dedupe_scene_tags_for_pack(
    tags: list[str],
    outfit_blocks: list[str],
    visual_en: str,
    pack: Any,
) -> tuple[list[str], list[str]]:
    if not getattr(pack.visual_policy, "dedupe_across_layers", False):
        return tags, []
    outfit_tokens = _tokens(" ".join(outfit_blocks))
    visual_tokens = _tokens(visual_en)
    max_tags = int(getattr(pack.visual_policy, "max_scene_tags", 0) or 0)
    kept: list[str] = []
    counted_scene_tags = 0
    removed: list[str] = []
    director_tags = {
        "full body",
        "medium",
        "close up",
        "low camera",
        "eye-level camera",
        "high camera",
        "rear three quarter view",
        "rear view",
        "side view",
        "front three quarter view",
        "front view",
        "facing away",
        "facing camera three quarter",
        "side orientation",
        "cavern entrance ahead",
    }
    for idx, tag in enumerate(tags):
        tag_tokens = _tokens(tag)
        if not tag_tokens:
            continue
        if tag in director_tags:
            kept.append(tag)
            continue
        if tag_tokens & _OUTFIT_LAYER_WORDS and (tag_tokens & outfit_tokens):
            removed.append(tag)
            continue
        if tag_tokens and tag_tokens <= visual_tokens:
            removed.append(tag)
            continue
        if len(tag_tokens & visual_tokens) >= max(2, len(tag_tokens) - 1):
            removed.append(tag)
            continue
        kept.append(tag)
        counted_scene_tags += 1
        if max_tags and counted_scene_tags >= max_tags:
            removed.extend(tags[idx + 1 :])
            break
    return kept, removed


def _dedupe_visual_against_outfit_for_pack(
    visual_en: str,
    outfit_blocks: list[str],
    pack: Any,
) -> tuple[str, list[str]]:
    if not getattr(pack.visual_policy, "dedupe_across_layers", False):
        return visual_en, []
    outfit_tokens = _tokens(" ".join(outfit_blocks))
    removed: list[str] = []
    kept: list[str] = []
    for raw_clause in visual_en.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        clause_tokens = _tokens(clause)
        outfit_overlap = clause_tokens & outfit_tokens & _OUTFIT_LAYER_WORDS
        scene_overlap = clause_tokens & _POSE_OR_SCENE_WORDS
        if outfit_overlap and re.search(r"\b(?:wears?|wearing|dressed in)\b", clause, re.IGNORECASE):
            removed.append(clause)
            continue
        if outfit_overlap & _CLOTHING_OUTFIT_WORDS and not scene_overlap:
            removed.append(clause)
            continue
        if outfit_overlap and len(outfit_overlap) >= 2 and not scene_overlap:
            removed.append(clause)
            continue
        kept.append(clause)
    return ", ".join(kept), removed
