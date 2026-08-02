"""Pure helpers for deterministic visual composition."""

from __future__ import annotations

import re


def _character_gender(base_prompt: str) -> str | None:
    match = re.search(r"\b(1girl|1boy|1man|1woman)\b", base_prompt, re.IGNORECASE)
    if not match:
        return None
    return "girl" if match.group(1).lower() in ("1girl", "1woman") else "boy"


def _count_anchor_tag(
    visible_characters: list[str], base_prompt_by_character: dict[str, str]
) -> str:
    """Return the strongest subject-count anchor for multi-character prompts."""

    girls = sum(
        1
        for c in visible_characters
        if _character_gender(base_prompt_by_character.get(c, "")) == "girl"
    )
    boys = sum(
        1
        for c in visible_characters
        if _character_gender(base_prompt_by_character.get(c, "")) == "boy"
    )
    total = len(visible_characters)
    if girls + boys != total:
        return f"{total}people"
    if girls == 1 and boys == 1:
        return "1girl and 1boy"
    parts: list[str] = []
    if girls:
        parts.append(f"{girls}girl{'s' if girls > 1 else ''}")
    if boys:
        parts.append(f"{boys}boy{'s' if boys > 1 else ''}")
    if len(parts) == 1:
        return parts[0]
    return f"{total}people, " + ", ".join(parts)


def _position_tags(count: int) -> list[str]:
    if count == 2:
        return ["on the left", "on the right"]
    if count == 3:
        return ["on the left", "in the center", "on the right"]
    if count == 4:
        return ["on the far left", "on the left", "on the right", "on the far right"]
    return [f"position {index + 1}" for index in range(count)]
