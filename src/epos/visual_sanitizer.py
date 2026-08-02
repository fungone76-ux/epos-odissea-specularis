"""Pure sanitization helpers for visual prompt layers."""

from __future__ import annotations

import re
from typing import Any


_IDENTITY_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:her|his|their)\s+[^,.;]*\b(?:hair|hairstyle|braid(?:ed)?|ponytail)\b[^,.;]*",
        r"\b(?:bronze[- ]ringed|sea[- ]salt(?:ed)?|wind[- ]swept|loose|long|short|dark|black|brown|blonde|brunette)\s+(?:[\w-]+\s+){0,2}hair\b",
        r"\b(?:hair|hairstyle|haircut|hair\s+rings?|hair\s+ornaments?|braid(?:ed)?|ponytail)\b(?:\s+[\w-]+){0,3}",
        r"\b(?:green|blue|grey|gray|black|brown|amber|piercing|bloodshot)\s+eyes?\b",
        r"\beye\s+colou?r\b",
        r"\b(?:olive|pale|dark|fair|tanned|sun[- ]worn|glowing)\s+skin\b",
        r"\bskin\s+colou?r\b",
        r"\b(?:deep\s+)?scar(?:s|red)?(?:\s+across\s+[^,.;]*)?\b",
        r"\btattoos?(?:\s+[^,.;]*)?\b",
        r"\b(?:three|two|[0-9]+)\s+meters?\s+tall\b",
        r"\b(?:very\s+)?(?:tall|short)\s+(?:woman|man|figure|body)\b",
        r"\b(?:massive|muscular|athletic|curvy|skinny|lean|wiry|hourglass|shapely)\s+(?:body|build|figure|proportions)\b",
        r"\bbody\s+shape\b",
        r"\b(?:young|old|middle[- ]aged|mature|elderly)\s+(?:woman|man|female|male|girl|boy)\b",
        r"\bage\s+appearance\b",
        r"\b(?:male|female)\s+anatomy\b",
        r"\b(?:breasts?|hips?|waist)\b",
        r"\bsingle\s+(?:large\s+)?(?:bloodshot\s+)?eye(?:\s+in\s+[^,.;]*)?\b",
    )
)


def _sanitize_identity_text(text: str) -> tuple[str, list[str]]:
    """Remove physical identity traits from generated or mutable layers."""

    removed: list[str] = []
    kept: list[str] = []
    for raw_clause in text.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        clean = clause
        for pattern in _IDENTITY_TEXT_PATTERNS:
            matches = [m.group(0).strip() for m in pattern.finditer(clean)]
            if matches:
                removed.extend(m for m in matches if m)
                clean = pattern.sub("", clean)
        clean = re.sub(r"\s+", " ", clean)
        clean = re.sub(r"\s+([.;:])", r"\1", clean)
        clean = clean.strip(" ,;:-")
        if clean:
            kept.append(clean)
    return ", ".join(kept), removed


def _sanitize_identity_tags(tags: list[str]) -> tuple[list[str], list[str]]:
    sanitized: list[str] = []
    removed: list[str] = []
    for tag in tags:
        clean, tag_removed = _sanitize_identity_text(str(tag))
        if tag_removed:
            removed.extend(tag_removed)
        if clean:
            sanitized.append(clean)
    return sanitized, removed


_FACIAL_EXPRESSION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwith\s+(?:an?\s+)?[^,.;]*\bexpression\b",
        r"\b(?:with\s+)?(?:a\s+)?(?:facial\s+)?(?:subtle|weary|determined|angry|stern|sad|seductive|cold|focused)?\s*expression\b",
        r"\b(?:(?:subtle|weary|determined|angry|stern|sad|seductive|cold|focused)\s+)?(?:smile|smiling|smirk|frown|glaring)\b",
        r"\bnarrowed\s+eyes\b",
        r"\bclenched\s+jaw\b",
    )
)


def _sanitize_facial_text(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    kept: list[str] = []
    for raw_clause in text.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        clean = clause
        for pattern in _FACIAL_EXPRESSION_PATTERNS:
            matches = [m.group(0).strip() for m in pattern.finditer(clean)]
            if matches:
                removed.extend(m for m in matches if m)
                clean = pattern.sub("", clean)
        clean = re.sub(r"\s+", " ", clean)
        clean = re.sub(r"\bwith\s*$", "", clean, flags=re.IGNORECASE)
        clean = clean.strip(" ,;:-")
        if clean:
            kept.append(clean)
    return ", ".join(kept), removed


def _sanitize_facial_tags(tags: list[str]) -> tuple[list[str], list[str]]:
    sanitized: list[str] = []
    removed: list[str] = []
    for tag in tags:
        clean, tag_removed = _sanitize_facial_text(str(tag))
        if tag_removed:
            removed.extend(tag_removed)
        if clean:
            sanitized.append(clean)
    return sanitized, removed


_BROKEN_GENERATED_CHUNK_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^(?:one\s+|both\s+|her\s+|his\s+|their\s+)?hands?\s+on$",
        r"^looking\s+(?:at|toward|towards|into|down|up)$",
        r"^holding$",
        r"^(?:with|at|on|in|near|toward|towards|into|from|by|beside)$",
        r"^with\s+(?:an?\s+)?[\w-]+$",
        r"^standing\s+with$",
        r"^sitting\s+with$",
    )
)


def _sanitize_broken_generated_text(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    kept: list[str] = []
    for raw_clause in text.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        if any(pattern.match(clause) for pattern in _BROKEN_GENERATED_CHUNK_PATTERNS):
            removed.append(clause)
            continue
        kept.append(clause)
    return ", ".join(kept), removed


def _sanitize_broken_generated_tags(tags: list[str]) -> tuple[list[str], list[str]]:
    sanitized: list[str] = []
    removed: list[str] = []
    for tag in tags:
        clean, tag_removed = _sanitize_broken_generated_text(str(tag))
        if tag_removed:
            removed.extend(tag_removed)
        if clean:
            sanitized.append(clean)
    return sanitized, removed


_FULL_BODY_CAMERA = re.compile(r"\bfull\s+body(?:\s+shot)?\b", re.IGNORECASE)
_WIDE_CAMERA = re.compile(r"\bwide\s+shot\b", re.IGNORECASE)
_CLOSE_CAMERA = re.compile(r"\bclose[- ]?up(?:\s+shot)?\b", re.IGNORECASE)


def _remove_camera_conflicts_from_text(
    text: str, remove_close_up: bool
) -> tuple[str, list[str]]:
    if not remove_close_up:
        return text, []
    removed: list[str] = []
    kept: list[str] = []
    for raw_clause in text.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        matches = [m.group(0) for m in _CLOSE_CAMERA.finditer(clause)]
        if matches:
            removed.extend(matches)
            clause = _CLOSE_CAMERA.sub("", clause)
        clause = re.sub(r"\s+", " ", clause).strip(" ,;:-")
        if clause:
            kept.append(clause)
    return ", ".join(kept), removed


def _resolve_camera_conflicts(
    visual_en: str,
    tags_en: list[str],
) -> tuple[str, list[str], list[dict[str, Any]]]:
    all_text = " ".join([visual_en, *tags_en])
    has_close = bool(_CLOSE_CAMERA.search(all_text))
    has_full = bool(_FULL_BODY_CAMERA.search(all_text))
    has_wide = bool(_WIDE_CAMERA.search(all_text))
    conflicts: list[dict[str, Any]] = []
    if not has_close or not (has_full or has_wide):
        return visual_en, tags_en, conflicts

    if has_full:
        conflicts.append({"type": "full_body_close_up", "resolved_by": "removed_close_up"})
    if has_wide:
        conflicts.append({"type": "wide_shot_close_up", "resolved_by": "removed_close_up"})
    visual_en, _removed_visual = _remove_camera_conflicts_from_text(visual_en, True)
    resolved_tags: list[str] = []
    for tag in tags_en:
        if _CLOSE_CAMERA.search(str(tag)):
            continue
        resolved_tags.append(tag)
    return visual_en, resolved_tags, conflicts
