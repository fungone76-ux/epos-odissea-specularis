"""Regia visuale deterministica per pack che dichiarano camera strutturata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .contract import VisualMoment
from .models import WorldState
from .worldpack import WorldPack


@dataclass(frozen=True)
class DirectedVisual:
    visual_en: str
    tags_en: list[str]
    diagnostics: dict[str, Any] = field(default_factory=dict)


_CAMERA_PATTERNS = (
    re.compile(r"\b(?:wide|medium|close(?:-?up)?)\s+shot\b", re.IGNORECASE),
    re.compile(r"\b(?:low|high|eye[- ]level)\s+(?:angle\s+)?(?:shot|camera)\b", re.IGNORECASE),
    re.compile(r"\b(?:low|high|eye[- ]level)\s+angle\b", re.IGNORECASE),
    re.compile(r"\b(?:rear|back|side|front)(?:\s+three[- ]quarter)?\s+(?:view|shot)\b", re.IGNORECASE),
    re.compile(r"\bthree[- ]quarter\s+(?:rear|front)\s+(?:view|shot)\b", re.IGNORECASE),
    re.compile(r"\bfull\s+body(?:\s+shot)?\b", re.IGNORECASE),
)


# Posa esplicita/esibizionistica dichiarata nella scena: l'intento del
# giocatore ha priorita' sulla varieta' di camera. I tag di posa sono
# configurabili dal pack (visual_policy.explicit_pose_tags_rear/front);
# questi sono i default Pony-friendly.
_DEFAULT_POSE_TAGS_REAR = (
    "ass focus",
    "bent over",
    "presenting",
    "spread legs",
    "hips raised",
    "from behind",
)
_DEFAULT_POSE_TAGS_FRONT = (
    "presenting",
    "spread legs",
    "legs apart",
    "offering herself",
    "on display",
)

_EXPLICIT_POSE_PATTERN = re.compile(
    r"\b(?:presenting|bent over|bend over|bending over|spread legs|legs spread|"
    r"legs apart|ass up|hips raised|raised hips|on display|spread cheeks|"
    r"offering herself|exposing herself|spread wide|spread open|"
    r"spreading her|rear presented|presented rear)\b"
)
_REAR_POSE_PATTERN = re.compile(
    r"\b(?:rear|ass|butt|hips|from behind|facing away|backside|cheeks)\b"
)


def _explicit_pose(visual: VisualMoment) -> str:
    """Posa esplicita dichiarata: "presenting_rear", "presenting" oppure ""."""

    text = _visual_text(visual)
    if not _EXPLICIT_POSE_PATTERN.search(text):
        return ""
    if _REAR_POSE_PATTERN.search(text):
        return "presenting_rear"
    return "presenting"


def _pose_tags(pack: WorldPack, explicit_pose: str) -> list[str]:
    if explicit_pose == "presenting_rear":
        configured = getattr(pack.visual_policy, "explicit_pose_tags_rear", ()) or ()
        return list(configured) or list(_DEFAULT_POSE_TAGS_REAR)
    configured = getattr(pack.visual_policy, "explicit_pose_tags_front", ()) or ()
    return list(configured) or list(_DEFAULT_POSE_TAGS_FRONT)


def direct_visual(
    pack: WorldPack,
    state: WorldState,
    visual: VisualMoment,
    focus_character: str,
) -> DirectedVisual:
    if not getattr(pack.visual_policy, "visual_director_enabled", False):
        return DirectedVisual(visual.visual_en, list(visual.tags_en), {})

    proposed = _detect_camera_side([visual.visual_en, *visual.tags_en])
    history = _camera_history(state)
    explicit_pose = _explicit_pose(visual)
    pose_tags: list[str] = []

    if explicit_pose == "presenting_rear":
        # Posa esplicita dichiarata dal giocatore: inquadratura dedicata,
        # la varieta' di camera cede (si varia solo tra le viste posteriori).
        selected = _first_non_repeated(["rear", "rear_three_quarter", "side"], history, pack)
        shot_type = "close_up"
        camera_angle = "low"
        orientation = "facing_away"
        pose_tags = _pose_tags(pack, explicit_pose)
        reason = f"explicit_pose_priority:{explicit_pose}"
    elif explicit_pose == "presenting":
        selected = _first_non_repeated(["front", "front_three_quarter", "side"], history, pack)
        shot_type = "close_up"
        camera_angle = "eye_level"
        orientation = "facing_camera"
        pose_tags = _pose_tags(pack, explicit_pose)
        reason = f"explicit_pose_priority:{explicit_pose}"
    else:
        selected = _select_camera_side(pack, visual, proposed, history)
        shot_type = _select_shot_type(visual)
        camera_angle = _select_camera_angle(visual)
        orientation = _select_subject_orientation(visual, selected)
        reason = _director_reason(visual, selected, proposed, history)

    visual_en = _strip_camera_text(visual.visual_en)
    tags = _strip_camera_tags(list(visual.tags_en))
    camera_tags = _camera_tags(selected, shot_type, camera_angle, orientation, visual.visual_en)
    head = camera_tags + pose_tags
    tags = head + [tag for tag in tags if tag not in head]

    diagnostic = {
        "proposed_camera": proposed,
        "selected_camera": selected,
        "camera_override_applied": bool(proposed and proposed != selected),
        "camera_override_reason": reason if proposed and proposed != selected else "",
        "shot_type": shot_type,
        "camera_angle": camera_angle,
        "camera_side": selected,
        "subject_orientation": orientation,
        "camera_history": list(history),
        "director_reason": reason,
        "explicit_pose": explicit_pose,
        "pose_tags_added": pose_tags,
    }
    _push_camera_history(state, pack, diagnostic, visual)
    return DirectedVisual(visual_en=visual_en, tags_en=tags, diagnostics=diagnostic)


def _camera_history(state: WorldState) -> list[dict[str, Any]]:
    history = state.flags.get("visual_camera_history", [])
    return [dict(item) for item in history if isinstance(item, dict)]


def _push_camera_history(
    state: WorldState,
    pack: WorldPack,
    diagnostic: dict[str, Any],
    visual: VisualMoment,
) -> None:
    if not getattr(pack.visual_policy, "camera_variety_enabled", False):
        return
    history = state.flags.setdefault("visual_camera_history", [])
    history.append(
        {
            "camera_side": diagnostic["camera_side"],
            "shot_type": diagnostic["shot_type"],
            "camera_angle": diagnostic["camera_angle"],
            "focus_character": visual.focus_character,
            "posture": _posture_key(visual),
        }
    )
    size = int(getattr(pack.visual_policy, "camera_history_size", 6) or 6)
    del history[:-size]


def _detect_camera_side(parts: list[str]) -> str:
    text = " ".join(parts).lower()
    if "rear three-quarter" in text or "three-quarter rear" in text:
        return "rear_three_quarter"
    if re.search(r"\b(?:rear|back)\s+(?:view|shot)\b", text):
        return "rear"
    if "front three-quarter" in text or "three-quarter front" in text:
        return "front_three_quarter"
    if re.search(r"\bside\s+(?:view|shot)\b", text):
        return "side"
    if re.search(r"\bfront\s+(?:view|shot)\b", text):
        return "front"
    return ""


def _select_camera_side(
    pack: WorldPack,
    visual: VisualMoment,
    proposed: str,
    history: list[dict[str, Any]],
) -> str:
    if _is_crawling_toward_destination(visual):
        candidates = list(getattr(pack.visual_policy, "crawling_preferred_views", ()) or ())
        if not candidates:
            candidates = ["rear_three_quarter", "rear", "side", "front_three_quarter"]
        return _first_non_repeated(candidates, history, pack)
    if _needs_front_read(visual):
        return _first_non_repeated(["front_three_quarter", "front", "side"], history, pack)
    if proposed:
        return _first_non_repeated([proposed, "front_three_quarter", "side"], history, pack)
    return _first_non_repeated(["front_three_quarter", "side", "rear_three_quarter"], history, pack)


def _first_non_repeated(
    candidates: list[str],
    history: list[dict[str, Any]],
    pack: WorldPack,
) -> str:
    if not candidates:
        return "front_three_quarter"
    if not getattr(pack.visual_policy, "avoid_repeating_camera", False) or not history:
        return candidates[0]
    last = history[-1]
    last_side = last.get("camera_side")
    last_shot = last.get("shot_type")
    for candidate in candidates:
        if candidate != last_side:
            return candidate
    if last_shot:
        return candidates[0]
    return candidates[0]


def _select_shot_type(visual: VisualMoment) -> str:
    text = _visual_text(visual)
    if _is_crawling_posture(text) or "full body" in text:
        return "full_body"
    if re.search(r"\b(?:hands?|object|bow|spear|face)\b", text):
        return "medium"
    return "full_body"


def _select_camera_angle(visual: VisualMoment) -> str:
    text = _visual_text(visual)
    if _is_crawling_posture(text) or "low camera" in text or "low angle" in text:
        return "low"
    if "high angle" in text:
        return "high"
    return "eye_level"


def _select_subject_orientation(visual: VisualMoment, camera_side: str) -> str:
    if camera_side in ("rear", "rear_three_quarter") and _movement_toward_destination(visual):
        return "facing_away"
    if camera_side in ("front", "front_three_quarter"):
        return "facing_camera_three_quarter"
    return "side_orientation"


def _director_reason(
    visual: VisualMoment,
    selected: str,
    proposed: str,
    history: list[dict[str, Any]],
) -> str:
    if _is_crawling_toward_destination(visual):
        if history and history[-1].get("camera_side") == selected:
            return "movement_toward_destination"
        return "movement_toward_destination_and_camera_variety"
    if _needs_front_read(visual):
        return "front_read_of_action"
    if proposed and proposed != selected:
        return "camera_variety"
    return "default_structured_camera"


def _camera_tags(
    camera_side: str,
    shot_type: str,
    camera_angle: str,
    orientation: str,
    visual_en: str,
) -> list[str]:
    tags = [
        shot_type.replace("_", " "),
        camera_angle.replace("_", "-") + " camera",
        camera_side.replace("_", " ") + " view",
        orientation.replace("_", " "),
    ]
    if _mentions_cavern_destination(visual_en):
        tags.append("cavern entrance ahead")
    return tags


def _strip_camera_text(text: str) -> str:
    kept: list[str] = []
    for clause in text.split(","):
        clean = clause.strip()
        if not clean:
            continue
        for pattern in _CAMERA_PATTERNS:
            clean = pattern.sub("", clean)
        clean = re.sub(r"\s+", " ", clean).strip(" ,;:-")
        clean = re.sub(r"^(?:of|shot of)\s+", "", clean, flags=re.IGNORECASE)
        if clean:
            kept.append(clean)
    return ", ".join(kept)


def _strip_camera_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags:
        stripped = _strip_camera_text(str(tag))
        if stripped:
            cleaned.append(stripped)
    return cleaned


def _visual_text(visual: VisualMoment) -> str:
    return " ".join([visual.visual_en, *visual.tags_en]).lower()


def _posture_key(visual: VisualMoment) -> str:
    text = _visual_text(visual)
    if _EXPLICIT_POSE_PATTERN.search(text):
        return "presenting"
    if _is_crawling_posture(text):
        return "crawling"
    if "kneel" in text:
        return "kneeling"
    if "seated" in text or "sitting" in text:
        return "seated"
    return ""


def _is_crawling_posture(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:on all fours|crawling|crawl|kneeling forward|moving low to the ground)\b",
            text,
        )
    )


def _movement_toward_destination(visual: VisualMoment) -> bool:
    text = _visual_text(visual)
    return bool(re.search(r"\b(?:toward|towards|approaching|advancing|moving|facing)\b", text))


def _mentions_cavern_destination(text: str) -> bool:
    return bool(re.search(r"\b(?:cavern|cave)\s+(?:entrance|mouth|opening)|entrance ahead\b", text.lower()))


def _is_crawling_toward_destination(visual: VisualMoment) -> bool:
    text = _visual_text(visual)
    return _is_crawling_posture(text) and (
        _movement_toward_destination(visual) or _mentions_cavern_destination(text)
    )


def _needs_front_read(visual: VisualMoment) -> bool:
    text = _visual_text(visual)
    return bool(
        re.search(
            r"\b(?:reaching|grasping|drawing|aiming|reading|examining|holding up|showing)\b",
            text,
        )
    )
