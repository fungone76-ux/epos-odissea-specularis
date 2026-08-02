"""Deterministic selection of active NPC agent states."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import WorldState
from .npc_agent_registry import NpcAgentRegistry


@dataclass(frozen=True)
class NpcAgentSelectionRequest:
    registry: NpcAgentRegistry
    world_state: WorldState
    turn: int = 0
    present_npc_ids: tuple[str, ...] = ()
    mentioned_npc_ids: tuple[str, ...] = ()
    speaker_npc_id: str = ""
    actor_npc_id: str = ""
    reactor_npc_id: str = ""
    active_thread_ids: tuple[str, ...] = ()
    active_mission_ids: tuple[str, ...] = ()
    required_intervention_ids: tuple[str, ...] = ()
    max_agents: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(self, "present_npc_ids", _unique_ids(self.present_npc_ids))
        object.__setattr__(self, "mentioned_npc_ids", _unique_ids(self.mentioned_npc_ids))
        object.__setattr__(self, "active_thread_ids", _unique_ids(self.active_thread_ids))
        object.__setattr__(self, "active_mission_ids", _unique_ids(self.active_mission_ids))
        object.__setattr__(self, "required_intervention_ids", _unique_ids(self.required_intervention_ids))
        object.__setattr__(self, "speaker_npc_id", str(self.speaker_npc_id or "").strip())
        object.__setattr__(self, "actor_npc_id", str(self.actor_npc_id or "").strip())
        object.__setattr__(self, "reactor_npc_id", str(self.reactor_npc_id or "").strip())
        object.__setattr__(self, "turn", int(self.turn))
        object.__setattr__(self, "max_agents", max(0, int(self.max_agents)))


@dataclass(frozen=True)
class NpcAgentSelectionResult:
    selected_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]
    evaluated_ids: tuple[str, ...]
    reasons: tuple[tuple[str, tuple[str, ...]], ...]

    def reason_map(self) -> dict[str, tuple[str, ...]]:
        return {npc_id: reasons for npc_id, reasons in self.reasons}

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_ids": list(self.selected_ids),
            "excluded_ids": list(self.excluded_ids),
            "evaluated_ids": list(self.evaluated_ids),
            "reasons": {npc_id: list(reasons) for npc_id, reasons in self.reasons},
        }


def select_active_npc_agents(request: NpcAgentSelectionRequest) -> NpcAgentSelectionResult:
    present = set(request.present_npc_ids or tuple(request.world_state.present_npc_ids()))
    selected_candidates: list[tuple[tuple[int, int, int], str]] = []
    selected_reasons: dict[str, tuple[str, ...]] = {}
    excluded_reasons: dict[str, tuple[str, ...]] = {}
    evaluated: list[str] = []

    for index, agent in enumerate(request.registry.all()):
        npc_id = agent.npc_id
        evaluated.append(npc_id)
        if not agent.enabled:
            excluded_reasons[npc_id] = ("disabled",)
            continue
        if npc_id not in request.world_state.npcs:
            excluded_reasons[npc_id] = ("unknown_npc",)
            continue

        reasons = _selection_reasons(agent, request, present)
        if _is_selectable(npc_id, reasons, present):
            selected_reasons[npc_id] = reasons
            selected_candidates.append((_rank(reasons, agent.initiative_priority, index), npc_id))
        else:
            excluded_reasons[npc_id] = reasons + ("not_relevant",) if reasons else ("not_relevant",)

    selected = tuple(npc_id for _rank_key, npc_id in sorted(selected_candidates)[: request.max_agents])
    selected_set = set(selected)
    excluded: list[str] = []
    reasons_by_id: dict[str, tuple[str, ...]] = {}
    for npc_id in evaluated:
        if npc_id in selected_set:
            reasons_by_id[npc_id] = selected_reasons[npc_id]
            continue
        excluded.append(npc_id)
        reasons = excluded_reasons.get(npc_id, selected_reasons.get(npc_id, ()))
        if npc_id in selected_reasons and "over_budget" not in reasons:
            reasons = reasons + ("over_budget",)
        reasons_by_id[npc_id] = reasons

    return NpcAgentSelectionResult(
        selected_ids=selected,
        excluded_ids=tuple(excluded),
        evaluated_ids=tuple(evaluated),
        reasons=tuple((npc_id, reasons_by_id[npc_id]) for npc_id in evaluated),
    )


def _selection_reasons(agent, request: NpcAgentSelectionRequest, present: set[str]) -> tuple[str, ...]:
    npc_id = agent.npc_id
    reasons: list[str] = []
    if npc_id in present:
        reasons.append("present")
    if npc_id in request.required_intervention_ids:
        reasons.append("required_intervention")
    if npc_id == request.speaker_npc_id:
        reasons.append("speaker")
    if npc_id == request.actor_npc_id:
        reasons.append("actor")
    if npc_id == request.reactor_npc_id:
        reasons.append("reactor")
    if npc_id in request.mentioned_npc_ids:
        reasons.append("mentioned")
    if set(agent.open_thread_ids).intersection(request.active_thread_ids) or _has_open_world_thread(npc_id, request.world_state):
        reasons.append("open_thread")
    if set(agent.mission_refs).intersection(request.active_mission_ids):
        reasons.append("active_mission")
    if agent.next_evaluation_turn <= request.turn:
        reasons.append("next_evaluation_due")
    if agent.initiative_priority > 0:
        reasons.append("initiative_priority")
    return tuple(reasons)


def _is_selectable(npc_id: str, reasons: tuple[str, ...], present: set[str]) -> bool:
    if npc_id in present:
        return bool(reasons)
    explicit = {
        "required_intervention",
        "speaker",
        "actor",
        "reactor",
        "mentioned",
        "open_thread",
        "active_mission",
    }
    return any(reason in explicit for reason in reasons)


def _rank(reasons: tuple[str, ...], initiative_priority: int, index: int) -> tuple[int, int, int]:
    priority = {
        "present": 0,
        "required_intervention": 1,
        "speaker": 2,
        "actor": 3,
        "reactor": 4,
        "mentioned": 5,
        "open_thread": 6,
        "active_mission": 7,
        "next_evaluation_due": 8,
        "initiative_priority": 9,
    }
    best = min((priority[reason] for reason in reasons if reason in priority), default=99)
    return best, -int(initiative_priority), index


def _has_open_world_thread(npc_id: str, world_state: WorldState) -> bool:
    return any(
        thread.status == "open" and npc_id in thread.participants
        for thread in world_state.active_threads
    )


def _unique_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)
