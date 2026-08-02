"""Passive deterministic orchestration for selected NPC agent contexts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from epos.models import WorldState
from epos.npc_agent_context import NpcAgentContext
from epos.npc_agent_registry import NpcAgentRegistry
from epos.npc_agent_selector import NpcAgentSelectionRequest, select_active_npc_agents
from epos.npc_memory_retrieval import retrieve_memories_for_npc
from epos.npc_memory_retrieval_policy import NpcMemoryRetrievalPolicy


def _ids(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)


@dataclass(frozen=True)
class NpcCoordinatorRequest:
    registry: NpcAgentRegistry
    world_state: WorldState
    current_turn: int = 0
    present_npc_ids: tuple[str, ...] = ()
    mentioned_npc_ids: tuple[str, ...] = ()
    speaker_id: str = ""
    actor_id: str = ""
    reactor_id: str = ""
    required_intervention_ids: tuple[str, ...] = ()
    active_thread_ids: tuple[str, ...] = ()
    active_mission_ids: tuple[str, ...] = ()
    location_id: str = ""
    player_input: str = ""
    max_agents: int = 3
    retrieval_policy: NpcMemoryRetrievalPolicy = field(default_factory=NpcMemoryRetrievalPolicy)

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_turn", int(self.current_turn))
        if self.current_turn < 0:
            raise ValueError("current_turn must be non-negative")
        object.__setattr__(self, "present_npc_ids", _ids(self.present_npc_ids))
        object.__setattr__(self, "mentioned_npc_ids", _ids(self.mentioned_npc_ids))
        object.__setattr__(self, "required_intervention_ids", _ids(self.required_intervention_ids))
        object.__setattr__(self, "active_thread_ids", _ids(self.active_thread_ids))
        object.__setattr__(self, "active_mission_ids", _ids(self.active_mission_ids))
        object.__setattr__(self, "speaker_id", str(self.speaker_id or "").strip())
        object.__setattr__(self, "actor_id", str(self.actor_id or "").strip())
        object.__setattr__(self, "reactor_id", str(self.reactor_id or "").strip())
        object.__setattr__(self, "location_id", str(self.location_id or self.world_state.location_id or "").strip())
        object.__setattr__(self, "max_agents", max(0, int(self.max_agents)))


@dataclass(frozen=True)
class NpcCoordinatorResult:
    selected_agent_ids: tuple[str, ...] = ()
    excluded_agent_ids: tuple[str, ...] = ()
    agent_contexts: tuple[NpcAgentContext, ...] = ()
    selection_reasons: tuple[tuple[str, tuple[str, ...]], ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_agent_ids": list(self.selected_agent_ids),
            "excluded_agent_ids": list(self.excluded_agent_ids),
            "agent_contexts": [context.to_dict() for context in self.agent_contexts],
            "selection_reasons": {
                npc_id: list(reasons)
                for npc_id, reasons in self.selection_reasons
            },
            "diagnostics": self.diagnostics,
        }

    def to_llm_context_dict(self) -> dict[str, Any]:
        """Structural-only payload for a future single multi-agent LLM call."""

        return {
            "active_agents": [
                context.to_llm_context_dict()
                for context in self.agent_contexts
            ]
        }


def coordinate_npc_agents(request: NpcCoordinatorRequest) -> NpcCoordinatorResult:
    selection = select_active_npc_agents(
        NpcAgentSelectionRequest(
            registry=request.registry,
            world_state=request.world_state,
            turn=request.current_turn,
            present_npc_ids=request.present_npc_ids,
            mentioned_npc_ids=request.mentioned_npc_ids,
            speaker_npc_id=request.speaker_id,
            actor_npc_id=request.actor_id,
            reactor_npc_id=request.reactor_id,
            active_thread_ids=request.active_thread_ids,
            active_mission_ids=request.active_mission_ids,
            required_intervention_ids=request.required_intervention_ids,
            max_agents=request.max_agents,
        )
    )
    selection_reasons = selection.reason_map()
    contexts: list[NpcAgentContext] = []
    retrieval_diagnostics: dict[str, Any] = {}

    for npc_id in selection.selected_ids:
        agent = request.registry.get(npc_id)
        if agent is None:
            continue
        retrieval = retrieve_memories_for_npc(
            request.registry,
            npc_id,
            current_turn=request.current_turn,
            location_id=request.location_id,
            player_input=request.player_input,
            speaker_id=request.speaker_id,
            actor_id=request.actor_id,
            reactor_id=request.reactor_id,
            active_thread_ids=request.active_thread_ids,
            active_mission_ids=request.active_mission_ids,
            relevant_tags=(
                *request.active_thread_ids,
                *request.active_mission_ids,
                request.location_id,
            ),
            relevant_memory_types=("promise", "thread_update", "mission_event"),
            participant_ids=(request.speaker_id, request.actor_id, request.reactor_id, npc_id),
            policy=request.retrieval_policy,
        )
        contexts.append(
            NpcAgentContext.from_agent_state(
                agent,
                selected_short_memories=retrieval.selected_short_memories,
                selected_long_memories=retrieval.selected_long_memories,
                selection_reasons=selection_reasons.get(npc_id, ()),
            )
        )
        retrieval_diagnostics[npc_id] = {
            "short_selected": [memory.memory_id for memory in retrieval.selected_short_memories],
            "long_selected": [memory.memory_id for memory in retrieval.selected_long_memories],
            "short_excluded": list(retrieval.excluded_short_memory_ids),
            "long_excluded": list(retrieval.excluded_long_memory_ids),
            "reasons": {memory_id: reason for memory_id, reason in retrieval.reasons},
        }

    diagnostics = {
        "selected_agents": list(selection.selected_ids),
        "excluded_agents": list(selection.excluded_ids),
        "agent_contexts": {
            context.npc_id: {
                "selection_reasons": list(context.selection_reasons),
                **retrieval_diagnostics.get(context.npc_id, {}),
            }
            for context in contexts
        },
    }
    return NpcCoordinatorResult(
        selected_agent_ids=selection.selected_ids,
        excluded_agent_ids=selection.excluded_ids,
        agent_contexts=tuple(contexts),
        selection_reasons=selection.reasons,
        diagnostics=diagnostics,
    )
