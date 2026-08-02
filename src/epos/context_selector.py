"""Deterministic context selector V1.

The selector only removes existing snapshot items. It does not summarize,
invent facts, call providers, or mutate WorldState.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from .context_budget import ContextBudget
from .context_diagnostics import compare_context_size
from .models import WorldState
from .worldpack import WorldPack


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}


def context_selector_enabled(value: str | None = None) -> bool:
    raw = os.environ.get("EPOS_CONTEXT_SELECTOR_ENABLED", "false") if value is None else value
    normalized = str(raw).strip().casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"EPOS_CONTEXT_SELECTOR_ENABLED value not recognized: {raw!r}")


@dataclass(frozen=True)
class ContextSelectionRequest:
    world_state: WorldState
    world_pack: WorldPack
    player_input: str
    phase: str
    full_snapshot: dict[str, Any]
    budget: ContextBudget = field(default_factory=ContextBudget)


@dataclass(frozen=True)
class ContextSelectionResult:
    selected_snapshot: dict[str, Any]
    included_npcs: tuple[str, ...]
    excluded_npcs: tuple[str, ...]
    included_missions: tuple[str, ...]
    excluded_missions: tuple[str, ...]
    included_threads: tuple[str, ...]
    excluded_threads: tuple[str, ...]
    included_events: int
    excluded_events: int
    reasons: dict[str, list[str]]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_snapshot": self.selected_snapshot,
            "included_npcs": list(self.included_npcs),
            "excluded_npcs": list(self.excluded_npcs),
            "included_missions": list(self.included_missions),
            "excluded_missions": list(self.excluded_missions),
            "included_threads": list(self.included_threads),
            "excluded_threads": list(self.excluded_threads),
            "included_events": self.included_events,
            "excluded_events": self.excluded_events,
            "reasons": {k: list(v) for k, v in self.reasons.items()},
            "diagnostics": dict(self.diagnostics),
        }


def select_context(request: ContextSelectionRequest) -> ContextSelectionResult:
    snapshot = _copy_snapshot(request.full_snapshot)
    reasons: dict[str, list[str]] = {}
    selected_npcs = _select_npcs(request, reasons)
    selected_set = set(selected_npcs)

    present_npcs = list(snapshot.get("present_npcs", []))
    selected_present_npcs = [
        npc for npc in present_npcs if str(npc.get("id", "")) in selected_set
    ]
    excluded_npcs = tuple(
        str(npc.get("id", "")) for npc in present_npcs if str(npc.get("id", "")) not in selected_set
    )
    snapshot["present_npcs"] = selected_present_npcs

    _limit_player_fields(snapshot, request.budget)
    _limit_npc_fields(snapshot, request.budget)

    included_threads, excluded_threads = _select_threads(snapshot, selected_set, request.budget)
    included_missions, excluded_missions = _select_missions(
        snapshot, request, selected_set, request.budget
    )
    snapshot["npc_relationships"] = _select_relationships(
        list(snapshot.get("npc_relationships", [])), selected_set, request.budget
    )

    before_events = _count_events(request.full_snapshot)
    after_events = _count_events(snapshot)
    size = compare_context_size(request.full_snapshot, snapshot)
    diagnostics = {
        "enabled": True,
        "phase": request.phase,
        "included_npcs": list(selected_npcs),
        "excluded_npcs": list(excluded_npcs),
        "included_missions": list(included_missions),
        "excluded_missions": list(excluded_missions),
        "included_threads": list(included_threads),
        "excluded_threads": list(excluded_threads),
        "included_events": after_events,
        "excluded_events": max(0, before_events - after_events),
        **size,
        "reasons": {k: list(v) for k, v in reasons.items()},
    }
    return ContextSelectionResult(
        selected_snapshot=snapshot,
        included_npcs=tuple(selected_npcs),
        excluded_npcs=excluded_npcs,
        included_missions=tuple(included_missions),
        excluded_missions=tuple(excluded_missions),
        included_threads=tuple(included_threads),
        excluded_threads=tuple(excluded_threads),
        included_events=after_events,
        excluded_events=max(0, before_events - after_events),
        reasons=reasons,
        diagnostics=diagnostics,
    )


def _copy_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    copied: dict[str, Any] = {}
    for key, value in snapshot.items():
        if isinstance(value, list):
            copied[key] = [dict(item) if isinstance(item, dict) else item for item in value]
        elif isinstance(value, dict):
            copied[key] = dict(value)
        else:
            copied[key] = value
    return copied


def _select_npcs(
    request: ContextSelectionRequest, reasons: dict[str, list[str]]
) -> list[str]:
    state = request.world_state
    mentioned = _mentioned_npc_ids(state, request.player_input)
    thread_ids = _thread_participants(state)
    mission_ids = _mission_npc_ids(request.world_pack, state)
    candidates: list[str] = []
    present = set(state.present_npc_ids())
    for npc_id in state.npcs:
        npc_reasons: list[str] = []
        if npc_id in present:
            npc_reasons.append("present")
        if npc_id in mentioned:
            npc_reasons.append("mentioned")
        if npc_id in thread_ids:
            npc_reasons.append("open_thread")
        if npc_id in mission_ids:
            npc_reasons.append("mission")
        if npc_reasons and npc_id in present:
            reasons[npc_id] = npc_reasons
            candidates.append(npc_id)
        elif npc_reasons:
            reasons[npc_id] = [*npc_reasons, "excluded_not_present"]
    return candidates[: request.budget.max_active_npcs]


def _mentioned_npc_ids(state: WorldState, player_input: str) -> set[str]:
    text = f" {player_input.casefold()} "
    mentioned: set[str] = set()
    for npc_id, npc in state.npcs.items():
        aliases = {npc_id.casefold(), str(npc.name).casefold()}
        for alias in aliases:
            if alias and re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text):
                mentioned.add(npc_id)
                break
    return mentioned


def _thread_participants(state: WorldState) -> set[str]:
    ids: set[str] = set()
    for thread in state.active_threads:
        if thread.status != "open":
            continue
        ids.update(pid for pid in thread.participants if pid != "player")
    return ids


def _mission_npc_ids(pack: WorldPack, state: WorldState) -> set[str]:
    ids: set[str] = set()
    for mission in pack.missions.values():
        if mission.location_id != state.location_id:
            continue
        for collection in (
            mission.objectives,
            mission.success_conditions,
            mission.failure_conditions,
            mission.rewards,
            mission.consequences,
            mission.transitions,
            mission.alternative_solutions,
        ):
            for item in collection:
                for value in item.values():
                    if isinstance(value, str) and value in state.npcs:
                        ids.add(value)
                    elif isinstance(value, list):
                        ids.update(str(v) for v in value if str(v) in state.npcs)
    return ids


def _limit_player_fields(snapshot: dict[str, Any], budget: ContextBudget) -> None:
    player = snapshot.get("player")
    if isinstance(player, dict):
        player["inventory"] = list(player.get("inventory", []))[: budget.max_inventory_items]
    snapshot["player_knowledge"] = _tail(
        list(snapshot.get("player_knowledge", [])), budget.max_knowledge_entries
    )
    snapshot["player_knowledge_provenance"] = _tail(
        list(snapshot.get("player_knowledge_provenance", [])),
        budget.max_knowledge_entries,
    )


def _limit_npc_fields(snapshot: dict[str, Any], budget: ContextBudget) -> None:
    for npc in snapshot.get("present_npcs", []):
        if not isinstance(npc, dict):
            continue
        npc["knowledge"] = _tail(list(npc.get("knowledge", [])), budget.max_knowledge_entries)
        npc["knowledge_provenance"] = _tail(
            list(npc.get("knowledge_provenance", [])), budget.max_knowledge_entries
        )
        npc["recent_memories"] = _tail(
            list(npc.get("recent_memories", [])), budget.max_recent_events
        )


def _select_threads(
    snapshot: dict[str, Any], selected_npcs: set[str], budget: ContextBudget
) -> tuple[list[str], list[str]]:
    threads = list(snapshot.get("active_threads", []))
    selected: list[dict[str, Any]] = []
    excluded: list[str] = []
    for thread in threads:
        tid = str(thread.get("id", ""))
        participants = set(str(v) for v in thread.get("participants", []))
        if "player" in participants or participants.intersection(selected_npcs):
            if len(selected) < budget.max_open_threads:
                selected.append(thread)
            else:
                excluded.append(tid)
        else:
            excluded.append(tid)
    snapshot["active_threads"] = selected
    return [str(t.get("id", "")) for t in selected], excluded


def _select_missions(
    snapshot: dict[str, Any],
    request: ContextSelectionRequest,
    selected_npcs: set[str],
    budget: ContextBudget,
) -> tuple[list[str], list[str]]:
    missions = snapshot.get("missions", {})
    if not isinstance(missions, dict):
        return [], []
    ordered = [
        *[(m, "current") for m in missions.get("current", [])],
        *[(m, "upcoming") for m in missions.get("upcoming", [])],
    ]
    included: list[dict[str, Any]] = []
    excluded: list[str] = []
    input_text = request.player_input.casefold()
    for mission, _bucket in ordered:
        mission_id = str(mission.get("id", ""))
        relevant = (
            mission.get("location_id") == request.world_state.location_id
            or mission_id.casefold() in input_text
            or str(mission.get("name", "")).casefold() in input_text
            or _mission_mentions_npc(mission, selected_npcs)
        )
        if relevant and len(included) < budget.max_missions:
            included.append(mission)
        else:
            excluded.append(mission_id)
    included_ids = [str(m.get("id", "")) for m in included]
    snapshot["missions"] = {
        "current": [m for m in included if m.get("location_id") == request.world_state.location_id],
        "upcoming": [m for m in included if m.get("location_id") != request.world_state.location_id],
    }
    return included_ids, excluded


def _mission_mentions_npc(mission: dict[str, Any], selected_npcs: set[str]) -> bool:
    text = repr(mission)
    return any(npc_id in text for npc_id in selected_npcs)


def _select_relationships(
    relationships: list[dict[str, Any]], selected_npcs: set[str], budget: ContextBudget
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    relevant = {"player", *selected_npcs}
    for relationship in relationships:
        known_by = set(str(v) for v in relationship.get("known_by", []))
        endpoints = {str(relationship.get("from", "")), str(relationship.get("to", ""))}
        if endpoints.intersection(relevant) or known_by.intersection(selected_npcs):
            selected.append(relationship)
            if len(selected) >= budget.max_relationships:
                break
    return selected


def _count_events(snapshot: dict[str, Any]) -> int:
    count = 0
    for npc in snapshot.get("present_npcs", []):
        if isinstance(npc, dict):
            count += len(npc.get("recent_memories", []))
    initiative = snapshot.get("initiative_rhythm", {})
    if isinstance(initiative, dict):
        count += len(initiative.get("recent", []))
    return count


def _tail(items: list[Any], limit: int) -> list[Any]:
    if limit <= 0:
        return []
    return items[-limit:]
