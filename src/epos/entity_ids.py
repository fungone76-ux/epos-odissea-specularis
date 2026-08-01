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


def _key(value: Any) -> str:
    return str(value or "").strip().casefold()


def player_aliases_for_state(state: WorldState) -> set[str]:
    aliases = set(PLAYER_ALIASES)
    if state.player.name:
        aliases.add(_key(state.player.name))
    return {alias for alias in aliases if alias}


def normalize_entity_id(value: Any, world_state: WorldState, context_field: str) -> str:
    """Normalize one structured entity id.

    Only the protagonist aliases map to "player". NPC ids/display names are
    mapped from the current world state. Unknown ids are left untouched so the
    semantic validator can still reject genuinely invalid references.
    """

    text = str(value or "").strip()
    if not text:
        return text
    folded = text.casefold()
    if folded in player_aliases_for_state(world_state):
        return "player"
    if folded in {_key(npc_id) for npc_id in world_state.npcs}:
        for npc_id in world_state.npcs:
            if _key(npc_id) == folded:
                return npc_id
    for npc_id, npc in world_state.npcs.items():
        if npc.name and _key(npc.name) == folded:
            return npc_id
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
        return "npc_id_or_display_name"
    return "entity_id"


def _normalize_one(
    value: Any,
    state: WorldState,
    field_path: str,
    phase: str,
    attempt: int,
    source_payload: str,
) -> tuple[str, list[EntityNormalizationEntry]]:
    original = str(value or "").strip()
    normalized = normalize_entity_id(original, state, field_path)
    if normalized == original:
        return normalized, []
    return normalized, [
        EntityNormalizationEntry(
            field_path=field_path,
            original_value=original,
            normalized_value=normalized,
            alias_rule=_alias_rule(original, normalized, state),
            phase=phase,
            attempt=attempt,
            source_payload=source_payload,
        )
    ]


def _normalize_list(
    values: list[Any],
    state: WorldState,
    field_path: str,
    phase: str,
    attempt: int,
    source_payload: str,
) -> tuple[list[str], list[EntityNormalizationEntry]]:
    normalized_values: list[str] = []
    entries: list[EntityNormalizationEntry] = []
    for index, value in enumerate(values):
        normalized, item_entries = _normalize_one(
            value, state, f"{field_path}[{index}]", phase, attempt, source_payload
        )
        normalized_values.append(normalized)
        entries.extend(item_entries)
    return normalized_values, entries


def normalize_check_proposal_entity_ids(
    state: WorldState,
    proposal: CheckProposal,
    *,
    phase: str,
    attempt: int = 0,
    source_payload: str = "check_proposal",
) -> EntityNormalizationResult:
    target_ids, entries = _normalize_list(
        proposal.target_ids,
        state,
        "check.target_ids",
        phase,
        attempt,
        source_payload,
    )
    if not entries:
        return EntityNormalizationResult(proposal, [])
    return EntityNormalizationResult(replace(proposal, target_ids=target_ids), entries)


def normalize_confront_proposal_entity_ids(
    state: WorldState,
    proposal: ConfrontProposal,
    *,
    phase: str,
    attempt: int = 0,
    source_payload: str = "confront_proposal",
) -> EntityNormalizationResult:
    target_id, entries = _normalize_one(
        proposal.target_id,
        state,
        "confront.target_id",
        phase,
        attempt,
        source_payload,
    )
    if not entries:
        return EntityNormalizationResult(proposal, [])
    return EntityNormalizationResult(replace(proposal, target_id=target_id), entries)


def normalize_scene_entity_ids(
    state: WorldState,
    scene: FinalScene,
    *,
    phase: str,
    attempt: int = 0,
    source_payload: str = "scene",
) -> EntityNormalizationResult:
    entries: list[EntityNormalizationEntry] = []

    mutations = []
    for index, mutation in enumerate(scene.mutations):
        target, target_entries = _normalize_one(
            mutation.target,
            state,
            f"mutations[{index}].target",
            phase,
            attempt,
            source_payload,
        )
        entries.extend(target_entries)
        mutations.append(replace(mutation, target=target) if target_entries else mutation)

    dialogue = []
    for index, line in enumerate(scene.dialogue):
        # speaker is often display text in the contract. Keep display names
        # intact; normalize the addressee, which is an entity id field.
        to = line.to
        to_entries: list[EntityNormalizationEntry] = []
        if to:
            to, to_entries = _normalize_one(
                to,
                state,
                f"dialogue[{index}].to",
                phase,
                attempt,
                source_payload,
            )
            entries.extend(to_entries)
        dialogue.append(replace(line, to=to) if to_entries else line)

    memory_events = []
    for index, memory in enumerate(scene.memory_events):
        witnesses, witness_entries = _normalize_list(
            memory.witnesses,
            state,
            f"memory_events[{index}].witnesses",
            phase,
            attempt,
            source_payload,
        )
        entries.extend(witness_entries)
        memory_events.append(
            replace(memory, witnesses=witnesses) if witness_entries else memory
        )

    initiatives = []
    for index, event in enumerate(scene.initiatives):
        source, source_entries = _normalize_one(
            event.source,
            state,
            f"initiatives[{index}].source",
            phase,
            attempt,
            source_payload,
        )
        entries.extend(source_entries)
        target = event.target
        target_entries: list[EntityNormalizationEntry] = []
        if target:
            target, target_entries = _normalize_one(
                target,
                state,
                f"initiatives[{index}].target",
                phase,
                attempt,
                source_payload,
            )
            entries.extend(target_entries)
        initiatives.append(
            replace(event, source=source, target=target)
            if source_entries or target_entries
            else event
        )

    disclosure_events = []
    for index, event in enumerate(scene.disclosure_events):
        npc_id, npc_entries = _normalize_one(
            event.npc_id,
            state,
            f"disclosure_events[{index}].npc_id",
            phase,
            attempt,
            source_payload,
        )
        entries.extend(npc_entries)
        disclosure_events.append(replace(event, npc_id=npc_id) if npc_entries else event)

    def _normalize_npc_dicts(
        items: list[dict[str, Any]], field: str
    ) -> list[dict[str, Any]]:
        mapped: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            item = dict(item)
            if "npc_id" in item:
                npc_id, npc_entries = _normalize_one(
                    item["npc_id"],
                    state,
                    f"{field}[{index}].npc_id",
                    phase,
                    attempt,
                    source_payload,
                )
                if npc_entries:
                    item["npc_id"] = npc_id
                    entries.extend(npc_entries)
            mapped.append(item)
        return mapped

    intentions = _normalize_npc_dicts(scene.intentions, "intentions")
    npc_actions = _normalize_npc_dicts(scene.npc_actions, "npc_actions")

    visual = scene.visual
    if visual is not None:
        visual_updates: dict[str, Any] = {}
        for field_name in (
            "focus_character",
            "speaker_character",
            "actor_character",
            "reactor_character",
        ):
            value = getattr(visual, field_name)
            normalized, field_entries = _normalize_one(
                value,
                state,
                f"visual.{field_name}",
                phase,
                attempt,
                source_payload,
            )
            if field_entries:
                visual_updates[field_name] = normalized
                entries.extend(field_entries)
        for field_name in ("visible_characters", "multi_character_participants"):
            values, list_entries = _normalize_list(
                getattr(visual, field_name),
                state,
                f"visual.{field_name}",
                phase,
                attempt,
                source_payload,
            )
            if list_entries:
                visual_updates[field_name] = values
                entries.extend(list_entries)
        if visual_updates:
            visual = replace(visual, **visual_updates)

    if not entries:
        return EntityNormalizationResult(scene, [])
    return EntityNormalizationResult(
        replace(
            scene,
            mutations=mutations,
            dialogue=dialogue,
            memory_events=memory_events,
            initiatives=initiatives,
            disclosure_events=disclosure_events,
            intentions=intentions,
            npc_actions=npc_actions,
            visual=visual,
        ),
        entries,
    )


def normalize_phase_response_entity_ids(
    state: WorldState,
    response: GmPhaseResponse,
    *,
    phase: str,
    attempt: int = 0,
    source_payload: str = "phase_response",
) -> EntityNormalizationResult:
    if response.mode == "no_check" and response.scene is not None:
        result = normalize_scene_entity_ids(
            state,
            response.scene,
            phase=phase,
            attempt=attempt,
            source_payload=source_payload,
        )
        if not result.changed:
            return EntityNormalizationResult(response, [])
        return EntityNormalizationResult(replace(response, scene=result.value), result.entries)
    if response.mode == "check_proposal" and response.check is not None:
        result = normalize_check_proposal_entity_ids(
            state,
            response.check,
            phase=phase,
            attempt=attempt,
            source_payload=source_payload,
        )
        if not result.changed:
            return EntityNormalizationResult(response, [])
        return EntityNormalizationResult(replace(response, check=result.value), result.entries)
    if response.mode == "confront_proposal" and response.confront is not None:
        result = normalize_confront_proposal_entity_ids(
            state,
            response.confront,
            phase=phase,
            attempt=attempt,
            source_payload=source_payload,
        )
        if not result.changed:
            return EntityNormalizationResult(response, [])
        return EntityNormalizationResult(replace(response, confront=result.value), result.entries)
    return EntityNormalizationResult(response, [])
