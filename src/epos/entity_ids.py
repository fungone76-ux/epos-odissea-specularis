"""Canonical entity-id normalization for LLM structured fields.

The LLM may use display names such as "Ulisse" where the runtime contract
requires the internal id "player". This module centralizes the conservative
alias rules and records every structural-field normalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .contract import CheckProposal, ConfrontProposal, FinalScene, GmPhaseResponse
from .models import WorldState

PLAYER_ALIASES = {
    "player",
    "ulisse",
    "odysseus",
    "odisseo",
}
_PLACEHOLDER_NPC_ID = "npc_id"


def _key(value: Any) -> str:
    return str(value or "").strip().casefold()


def player_aliases_for_state(state: WorldState) -> set[str]:
    aliases = set(PLAYER_ALIASES)
    if state.player.name:
        aliases.add(_key(state.player.name))
    return {alias for alias in aliases if alias}


def normalize_entity_id(value: Any, world_state: WorldState, context_field: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    folded = text.casefold()
    if folded in player_aliases_for_state(world_state):
        return "player"
    for npc_id in world_state.npcs:
        if _key(npc_id) == folded:
            return npc_id
    exact_names = [npc_id for npc_id, npc in world_state.npcs.items() if npc.name and _key(npc.name) == folded]
    if len(exact_names) == 1:
        return exact_names[0]
    first_names = [npc_id for npc_id, npc in world_state.npcs.items() if npc.name and _key(str(npc.name).split()[0]) == folded]
    if len(first_names) == 1:
        return first_names[0]
    return text


@dataclass(frozen=True)
class EntityNormalizationEntry:
    field_path: str
    original_value: str
    normalized_value: str
    alias_rule: str
    phase: str
    attempt: int
    source_payload: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "original_value": self.original_value,
            "normalized_value": self.normalized_value,
            "alias_rule": self.alias_rule,
            "phase": self.phase,
            "attempt": self.attempt,
            "source_payload": self.source_payload,
        }


@dataclass(frozen=True)
class EntityNormalizationResult:
    value: Any
    entries: list[EntityNormalizationEntry] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {"normalizations": [entry.to_dict() for entry in self.entries]}


def _alias_rule(original: str, normalized: str, state: WorldState) -> str:
    if normalized == "player" and _key(original) in player_aliases_for_state(state):
        return "player_alias"
    if normalized in state.npcs:
        full_name = str(state.npcs[normalized].name or "").strip()
        if full_name and _key(original) == _key(full_name.split()[0]) and _key(original) != _key(full_name):
            return "unique_npc_first_name"
        return "npc_id_or_display_name"
    return "entity_id"


def _normalize_one(value: Any, state: WorldState, field_path: str, phase: str, attempt: int, source_payload: str) -> tuple[str, list[EntityNormalizationEntry]]:
    original = str(value or "").strip()
    normalized = normalize_entity_id(original, state, field_path)
    if normalized == original:
        return normalized, []
    return normalized, [EntityNormalizationEntry(field_path, original, normalized, _alias_rule(original, normalized, state), phase, attempt, source_payload)]


def _normalize_list(values: list[Any], state: WorldState, field_path: str, phase: str, attempt: int, source_payload: str) -> tuple[list[str], list[EntityNormalizationEntry]]:
    normalized_values: list[str] = []
    entries: list[EntityNormalizationEntry] = []
    for index, value in enumerate(values):
        normalized, item_entries = _normalize_one(value, state, f"{field_path}[{index}]", phase, attempt, source_payload)
        normalized_values.append(normalized)
        entries.extend(item_entries)
    return normalized_values, entries


def _present_npc(state: WorldState, value: Any) -> str | None:
    normalized = normalize_entity_id(value, state, "placeholder_candidate")
    npc = state.npcs.get(normalized)
    return normalized if npc is not None and npc.present else None


def _scene_placeholder_target(state: WorldState, scene: FinalScene) -> str | None:
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


def _repair_scene_placeholders(state: WorldState, scene: FinalScene, *, phase: str, attempt: int, source_payload: str) -> tuple[FinalScene, list[EntityNormalizationEntry]]:
    target = _scene_placeholder_target(state, scene)
    if target is None:
        return scene, []
    entries: list[EntityNormalizationEntry] = []

    def entry(path: str) -> EntityNormalizationEntry:
        return EntityNormalizationEntry(path, _PLACEHOLDER_NPC_ID, target, "scene_placeholder_npc_id", phase, attempt, source_payload)

    intentions = []
    for index, item in enumerate(scene.intentions):
        mapped = dict(item)
        if _key(mapped.get("npc_id")) == _PLACEHOLDER_NPC_ID:
            mapped["npc_id"] = target
            entries.append(entry(f"intentions[{index}].npc_id"))
        intentions.append(mapped)
    npc_actions = []
    for index, item in enumerate(scene.npc_actions):
        mapped = dict(item)
        if _key(mapped.get("npc_id")) == _PLACEHOLDER_NPC_ID:
            mapped["npc_id"] = target
            entries.append(entry(f"npc_actions[{index}].npc_id"))
        npc_actions.append(mapped)
    visual = scene.visual
    if visual is not None:
        updates: dict[str, Any] = {}
        for field_name in ("focus_character", "speaker_character", "actor_character", "reactor_character"):
            if _key(getattr(visual, field_name)) == _PLACEHOLDER_NPC_ID:
                updates[field_name] = target
                entries.append(entry(f"visual.{field_name}"))
        for field_name in ("visible_characters", "multi_character_participants"):
            values = list(getattr(visual, field_name))
            changed = False
            for index, value in enumerate(values):
                if _key(value) == _PLACEHOLDER_NPC_ID:
                    values[index] = target
                    entries.append(entry(f"visual.{field_name}[{index}]"))
                    changed = True
            if changed:
                updates[field_name] = values
        if updates:
            visual = replace(visual, **updates)
    if not entries:
        return scene, []
    return replace(scene, intentions=intentions, npc_actions=npc_actions, visual=visual), entries


def normalize_check_proposal_entity_ids(state: WorldState, proposal: CheckProposal, *, phase: str, attempt: int = 0, source_payload: str = "check_proposal") -> EntityNormalizationResult:
    target_ids, entries = _normalize_list(proposal.target_ids, state, "check.target_ids", phase, attempt, source_payload)
    return EntityNormalizationResult(replace(proposal, target_ids=target_ids), entries) if entries else EntityNormalizationResult(proposal, [])


def normalize_confront_proposal_entity_ids(state: WorldState, proposal: ConfrontProposal, *, phase: str, attempt: int = 0, source_payload: str = "confront_proposal") -> EntityNormalizationResult:
    target_id, entries = _normalize_one(proposal.target_id, state, "confront.target_id", phase, attempt, source_payload)
    return EntityNormalizationResult(replace(proposal, target_id=target_id), entries) if entries else EntityNormalizationResult(proposal, [])


def normalize_scene_entity_ids(state: WorldState, scene: FinalScene, *, phase: str, attempt: int = 0, source_payload: str = "scene") -> EntityNormalizationResult:
    scene, placeholder_entries = _repair_scene_placeholders(state, scene, phase=phase, attempt=attempt, source_payload=source_payload)
    entries: list[EntityNormalizationEntry] = list(placeholder_entries)
    mutations = []
    for index, mutation in enumerate(scene.mutations):
        target, item_entries = _normalize_one(mutation.target, state, f"mutations[{index}].target", phase, attempt, source_payload)
        entries.extend(item_entries)
        mutations.append(replace(mutation, target=target) if item_entries else mutation)
    dialogue = []
    for index, line in enumerate(scene.dialogue):
        to = line.to
        item_entries: list[EntityNormalizationEntry] = []
        if to:
            to, item_entries = _normalize_one(to, state, f"dialogue[{index}].to", phase, attempt, source_payload)
            entries.extend(item_entries)
        dialogue.append(replace(line, to=to) if item_entries else line)
    memory_events = []
    for index, memory in enumerate(scene.memory_events):
        witnesses, item_entries = _normalize_list(memory.witnesses, state, f"memory_events[{index}].witnesses", phase, attempt, source_payload)
        entries.extend(item_entries)
        memory_events.append(replace(memory, witnesses=witnesses) if item_entries else memory)
    initiatives = []
    for index, event in enumerate(scene.initiatives):
        source, source_entries = _normalize_one(event.source, state, f"initiatives[{index}].source", phase, attempt, source_payload)
        entries.extend(source_entries)
        target = event.target
        target_entries: list[EntityNormalizationEntry] = []
        if target:
            target, target_entries = _normalize_one(target, state, f"initiatives[{index}].target", phase, attempt, source_payload)
            entries.extend(target_entries)
        initiatives.append(replace(event, source=source, target=target) if source_entries or target_entries else event)
    disclosure_events = []
    for index, event in enumerate(scene.disclosure_events):
        npc_id, item_entries = _normalize_one(event.npc_id, state, f"disclosure_events[{index}].npc_id", phase, attempt, source_payload)
        entries.extend(item_entries)
        disclosure_events.append(replace(event, npc_id=npc_id) if item_entries else event)

    def normalize_npc_dicts(items: list[dict[str, Any]], field_name: str) -> list[dict[str, Any]]:
        mapped = []
        for index, item in enumerate(items):
            item = dict(item)
            if "npc_id" in item:
                npc_id, item_entries = _normalize_one(item["npc_id"], state, f"{field_name}[{index}].npc_id", phase, attempt, source_payload)
                if item_entries:
                    item["npc_id"] = npc_id
                    entries.extend(item_entries)
            mapped.append(item)
        return mapped

    intentions = normalize_npc_dicts(scene.intentions, "intentions")
    npc_actions = normalize_npc_dicts(scene.npc_actions, "npc_actions")
    visual = scene.visual
    if visual is not None:
        updates: dict[str, Any] = {}
        for field_name in ("focus_character", "speaker_character", "actor_character", "reactor_character"):
            normalized, item_entries = _normalize_one(getattr(visual, field_name), state, f"visual.{field_name}", phase, attempt, source_payload)
            if item_entries:
                updates[field_name] = normalized
                entries.extend(item_entries)
        for field_name in ("visible_characters", "multi_character_participants"):
            values, item_entries = _normalize_list(getattr(visual, field_name), state, f"visual.{field_name}", phase, attempt, source_payload)
            if item_entries:
                updates[field_name] = values
                entries.extend(item_entries)
        if updates:
            visual = replace(visual, **updates)
    if not entries:
        return EntityNormalizationResult(scene, [])
    return EntityNormalizationResult(replace(scene, mutations=mutations, dialogue=dialogue, memory_events=memory_events, initiatives=initiatives, disclosure_events=disclosure_events, intentions=intentions, npc_actions=npc_actions, visual=visual), entries)


def normalize_phase_response_entity_ids(state: WorldState, response: GmPhaseResponse, *, phase: str, attempt: int = 0, source_payload: str = "phase_response") -> EntityNormalizationResult:
    if response.mode == "no_check" and response.scene is not None:
        result = normalize_scene_entity_ids(state, response.scene, phase=phase, attempt=attempt, source_payload=source_payload)
        return EntityNormalizationResult(replace(response, scene=result.value), result.entries) if result.changed else EntityNormalizationResult(response, [])
    if response.mode == "check_proposal" and response.check is not None:
        result = normalize_check_proposal_entity_ids(state, response.check, phase=phase, attempt=attempt, source_payload=source_payload)
        return EntityNormalizationResult(replace(response, check=result.value), result.entries) if result.changed else EntityNormalizationResult(response, [])
    if response.mode == "confront_proposal" and response.confront is not None:
        result = normalize_confront_proposal_entity_ids(state, response.confront, phase=phase, attempt=attempt, source_payload=source_payload)
        return EntityNormalizationResult(replace(response, confront=result.value), result.entries) if result.changed else EntityNormalizationResult(response, [])
    return EntityNormalizationResult(response, [])
