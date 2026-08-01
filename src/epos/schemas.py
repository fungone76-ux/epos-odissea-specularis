"""Explicit structural schemas for EPOS JSON/YAML contracts.

The project intentionally avoids a runtime dependency on jsonschema here: the
schema dictionaries are stable documentation for prompts and tooling, while the
small validators below enforce the subset needed by the Python runtime before
normal domain parsing happens.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = 1

GM_PHASE_RESPONSE_SCHEMA: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "type": "object",
    "required": ["mode"],
    "modes": {
        "no_check": {"required": ["scene"], "forbidden": ["check", "confront", "clarification"]},
        "check_proposal": {"required": ["check"], "forbidden": ["scene", "confront", "clarification"]},
        "confront_proposal": {"required": ["confront"], "forbidden": ["scene", "check", "clarification"]},
        "clarification": {"required": ["clarification"], "forbidden": ["scene", "check", "confront"]},
    },
}

CHECK_PROPOSAL_SCHEMA: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "type": "object",
    "required": ["action_kind", "skill", "difficulty", "stakes"],
    "properties": {
        "action_kind": "string",
        "skill": "string",
        "difficulty": "integer",
        "target_ids": "array:string",
        "opposition": "string",
        "reason": "string",
        "stakes": "object",
    },
}

FINAL_SCENE_SCHEMA: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "type": "object",
    "required": ["narration"],
    "properties": {
        "narration": "string",
        "dialogue": "array:object",
        "npc_actions": "array:object",
        "intentions": "array:object",
        "initiatives": "array:object",
        "disclosure_events": "array:object",
        "mutations": "array:object",
        "memory_events": "array:object",
        "visual": "object|null",
    },
}

VISUAL_MOMENT_SCHEMA: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "type": "object",
    "required": ["focus_character", "visible_characters", "visual_en"],
    "properties": {
        "summary": "string",
        "focus_character": "string",
        "visible_characters": "array:string",
        "shared_action": "boolean",
        "visual_en": "string",
        "tags_en": "array:string",
        "moment_type": "string",
        "speaker_character": "string",
        "actor_character": "string",
        "reactor_character": "string",
        "intimate_shared_moment": "boolean",
        "multi_character_reason": "string",
        "multi_character_participants": "array:string",
    },
}

VISUAL_CONTRACT_SCHEMA: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "type": "object",
    "required": [
        "turn",
        "location_id",
        "moment",
        "focus_character",
        "visible_characters",
        "shared_action",
        "characters",
        "time_phase",
        "visual_en",
        "tags_en",
        "prompt_package",
        "concrete_action",
        "place",
        "canonical_outfit",
        "pose",
        "shot_type",
        "camera_side",
        "camera_angle",
        "lighting",
        "positive_prompt",
        "negative_prompt",
        "visual_reason",
    ],
    "properties": {
        "turn": "integer",
        "location_id": "string",
        "moment": "string",
        "focus_character": "string",
        "visible_characters": "array:string",
        "shared_action": "boolean",
        "characters": "array:object",
        "time_phase": "string",
        "visual_en": "string",
        "tags_en": "array:string",
        "prompt_package": "object",
        "focus_reason": "string",
        "multi_character_reason": "string",
        "camera_director": "object",
        "concrete_action": "string",
        "place": "string",
        "canonical_outfit": "object",
        "pose": "string",
        "shot_type": "string",
        "camera_side": "string",
        "camera_angle": "string",
        "lighting": "string",
        "positive_prompt": "string",
        "negative_prompt": "string",
        "visual_reason": "string",
    },
    "prompt_package_required": ["positive", "negative"],
    "character_required": ["id", "outfit_worn", "outfit_removed", "wounds"],
    "camera_director_required_when_present": [
        "selected_camera",
        "shot_type",
        "camera_angle",
        "camera_side",
        "director_reason",
    ],
}

WORLDPACK_MISSION_SCHEMA: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "type": "object",
    "required": [
        "id",
        "location_id",
        "name",
        "description",
        "objectives",
        "success_conditions",
        "failure_conditions",
        "rewards",
        "consequences",
        "transitions",
    ],
    "properties": {
        "id": "string",
        "location_id": "string",
        "name": "string",
        "description": "string",
        "prerequisites": "array:string",
        "state": "string",
        "objectives": "array:object",
        "success_conditions": "array:object",
        "failure_conditions": "array:object",
        "rewards": "array:object",
        "consequences": "array:object",
        "transitions": "array:object",
        "alternative_solutions": "array:object",
    },
}


class SchemaError(ValueError):
    """Payload structurally incompatible with an explicit EPOS schema."""


def validate_gm_phase_response_shape(data: Any) -> None:
    obj = _mapping(data, "gm_phase_response")
    _required(obj, GM_PHASE_RESPONSE_SCHEMA["required"], "gm_phase_response")
    mode = obj.get("mode")
    if not isinstance(mode, str):
        raise SchemaError("gm_phase_response.mode must be a string")
    branch = GM_PHASE_RESPONSE_SCHEMA["modes"].get(mode)
    if branch is None:
        raise SchemaError(f"gm_phase_response.mode is not allowed: {mode!r}")
    _required(obj, branch["required"], f"gm_phase_response[{mode}]")
    _forbidden(obj, branch["forbidden"], f"gm_phase_response[{mode}]")
    if mode == "no_check":
        validate_final_scene_shape(obj["scene"], path="gm_phase_response.scene")
    elif mode == "check_proposal":
        validate_check_proposal_shape(obj["check"], path="gm_phase_response.check")
    elif mode == "clarification":
        text = obj.get("clarification")
        if not isinstance(text, str) or not text.strip():
            raise SchemaError("gm_phase_response.clarification must be a non-empty string")


def validate_check_proposal_shape(data: Any, *, path: str = "check") -> None:
    obj = _mapping(data, path)
    _required(obj, CHECK_PROPOSAL_SCHEMA["required"], path)
    _type(obj, "action_kind", str, path)
    _type(obj, "skill", str, path)
    _type(obj, "difficulty", int, path)
    _type(obj, "stakes", Mapping, path)
    _optional_array(obj, "target_ids", str, path)


def validate_final_scene_shape(data: Any, *, path: str = "scene") -> None:
    obj = _mapping(data, path)
    _required(obj, FINAL_SCENE_SCHEMA["required"], path)
    _type(obj, "narration", str, path)
    for field in ("dialogue", "npc_actions", "intentions", "initiatives", "disclosure_events", "mutations", "memory_events"):
        _optional_array(obj, field, Mapping, path)
    if "visual" in obj and obj["visual"] is not None:
        validate_visual_moment_shape(obj["visual"], path=f"{path}.visual")


def validate_visual_moment_shape(data: Any, *, path: str = "visual") -> None:
    obj = _mapping(data, path)
    _required(obj, VISUAL_MOMENT_SCHEMA["required"], path)
    _type(obj, "focus_character", str, path)
    _optional_array(obj, "visible_characters", str, path, required=True)
    _type(obj, "visual_en", str, path)
    _optional_array(obj, "tags_en", str, path)
    if not obj["focus_character"].strip():
        raise SchemaError(f"{path}.focus_character must be non-empty")
    if not obj["visual_en"].strip():
        raise SchemaError(f"{path}.visual_en must be non-empty")
    if obj["focus_character"] not in obj["visible_characters"]:
        raise SchemaError(f"{path}.focus_character must be listed in visible_characters")


def validate_visual_contract_shape(data: Any, *, path: str = "visual_contract") -> None:
    obj = _mapping(data, path)
    _required(obj, VISUAL_CONTRACT_SCHEMA["required"], path)
    _type(obj, "turn", int, path)
    for field in (
        "location_id",
        "moment",
        "focus_character",
        "time_phase",
        "visual_en",
        "concrete_action",
        "place",
        "pose",
        "shot_type",
        "camera_side",
        "camera_angle",
        "lighting",
        "positive_prompt",
        "negative_prompt",
        "visual_reason",
    ):
        _type(obj, field, str, path)
        if not obj[field].strip():
            raise SchemaError(f"{path}.{field} must be non-empty")
    _type(obj, "shared_action", bool, path)
    _optional_array(obj, "visible_characters", str, path, required=True)
    _optional_array(obj, "tags_en", str, path, required=True)
    _optional_array(obj, "characters", Mapping, path, required=True)
    _mapping(obj["canonical_outfit"], f"{path}.canonical_outfit")
    if obj["focus_character"] not in obj["visible_characters"]:
        raise SchemaError(f"{path}.focus_character must be listed in visible_characters")
    prompt = _mapping(obj["prompt_package"], f"{path}.prompt_package")
    _required(prompt, VISUAL_CONTRACT_SCHEMA["prompt_package_required"], f"{path}.prompt_package")
    for field in VISUAL_CONTRACT_SCHEMA["prompt_package_required"]:
        if not isinstance(prompt[field], str) or not prompt[field].strip():
            raise SchemaError(f"{path}.prompt_package.{field} must be a non-empty string")
    if obj["positive_prompt"] != prompt["positive"]:
        raise SchemaError(f"{path}.positive_prompt must mirror prompt_package.positive")
    if obj["negative_prompt"] != prompt["negative"]:
        raise SchemaError(f"{path}.negative_prompt must mirror prompt_package.negative")
    visible = set(obj["visible_characters"])
    for idx, character in enumerate(obj["characters"]):
        cpath = f"{path}.characters[{idx}]"
        _required(character, VISUAL_CONTRACT_SCHEMA["character_required"], cpath)
        cid = character.get("id")
        if not isinstance(cid, str) or not cid.strip():
            raise SchemaError(f"{cpath}.id must be non-empty")
        if cid not in visible:
            raise SchemaError(f"{cpath}.id must be listed in visible_characters")
        for field in ("outfit_worn", "outfit_removed", "wounds"):
            _optional_array(character, field, str, cpath, required=True)
    camera = obj.get("camera_director") or {}
    if camera:
        camera_obj = _mapping(camera, f"{path}.camera_director")
        _required(
            camera_obj,
            VISUAL_CONTRACT_SCHEMA["camera_director_required_when_present"],
            f"{path}.camera_director",
        )


def validate_worldpack_mission_shape(
    data: Any,
    *,
    location_ids: set[str],
    known_ids: set[str],
    path: str = "mission",
) -> None:
    obj = _mapping(data, path)
    _required(obj, WORLDPACK_MISSION_SCHEMA["required"], path)
    for field in ("id", "location_id", "name", "description"):
        _type(obj, field, str, path)
        if not obj[field].strip():
            raise SchemaError(f"{path}.{field} must be non-empty")
    if obj["location_id"] not in location_ids:
        raise SchemaError(f"{path}.location_id unknown: {obj['location_id']!r}")
    _optional_array(obj, "prerequisites", str, path)
    for field in ("objectives", "success_conditions", "failure_conditions", "rewards", "consequences", "transitions"):
        _optional_array(obj, field, Mapping, path, required=True)
        if not obj[field]:
            raise SchemaError(f"{path}.{field} must not be empty")
    _optional_array(obj, "alternative_solutions", Mapping, path)
    for idx, transition in enumerate(obj["transitions"]):
        target = transition.get("location_id") or transition.get("to_location_id")
        if target is not None and target not in location_ids:
            raise SchemaError(f"{path}.transitions[{idx}] unknown location: {target!r}")
    for idx, objective in enumerate(obj["objectives"]):
        target = objective.get("target") or objective.get("target_id")
        if target is not None and target not in known_ids and target not in location_ids:
            raise SchemaError(f"{path}.objectives[{idx}] unknown target: {target!r}")


def _mapping(data: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise SchemaError(f"{path} must be an object")
    return data


def _required(obj: Mapping[str, Any], fields: Sequence[str], path: str) -> None:
    missing = [field for field in fields if field not in obj]
    if missing:
        raise SchemaError(f"{path} missing required field(s): {', '.join(missing)}")


def _forbidden(obj: Mapping[str, Any], fields: Sequence[str], path: str) -> None:
    present = [field for field in fields if field in obj]
    if present:
        raise SchemaError(f"{path} contains forbidden field(s): {', '.join(present)}")


def _type(obj: Mapping[str, Any], field: str, expected: type | tuple[type, ...], path: str) -> None:
    if field in obj and not isinstance(obj[field], expected):
        raise SchemaError(f"{path}.{field} has invalid type")


def _optional_array(
    obj: Mapping[str, Any],
    field: str,
    item_type: type,
    path: str,
    *,
    required: bool = False,
) -> None:
    if field not in obj:
        if required:
            raise SchemaError(f"{path}.{field} is required")
        return
    value = obj[field]
    if not isinstance(value, list):
        raise SchemaError(f"{path}.{field} must be an array")
    for idx, item in enumerate(value):
        if not isinstance(item, item_type):
            raise SchemaError(f"{path}.{field}[{idx}] has invalid type")
