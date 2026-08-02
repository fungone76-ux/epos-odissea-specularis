from dataclasses import FrozenInstanceError

import pytest

from epos.models import NpcState, PlayerState, Thread, WorldState
from epos.npc_agent_context import NpcAgentContext
from epos.npc_agent_coordinator import (
    NpcCoordinatorRequest,
    NpcCoordinatorResult,
    coordinate_npc_agents,
)
from epos.npc_agent_coordinator_diagnostics import build_npc_coordinator_diagnostics
from epos.npc_agent_models import NpcAgentState
from epos.npc_agent_registry import NpcAgentRegistry
from epos.npc_memory_long import NpcLongMemory
from epos.npc_memory_retrieval_policy import NpcMemoryRetrievalPolicy
from epos.npc_memory_short import NpcShortMemory


def _world_state() -> WorldState:
    return WorldState(
        session_id="session",
        turn=12,
        time_phase="day",
        location_id="cove",
        player=PlayerState(name="Player", location_id="cove"),
        npcs={
            "luna": NpcState(id="luna", name="Luna", age=30, location_id="cove", present=True),
            "maria": NpcState(id="maria", name="Maria", age=31, location_id="cove", present=True),
            "stella": NpcState(id="stella", name="Stella", age=29, location_id="tower", present=False),
        },
        active_threads=[
            Thread(
                id="thread_luna",
                type="promise",
                participants=["luna"],
                summary="Luna waits for the promise.",
                opened_turn=9,
            ),
            Thread(
                id="thread_maria",
                type="mission",
                participants=["maria"],
                summary="Maria tracks the mission.",
                opened_turn=10,
            ),
        ],
    )


def _short(npc_id: str = "luna", **overrides) -> NpcShortMemory:
    data = {
        "memory_id": f"short_{npc_id}_1",
        "npc_id": npc_id,
        "turn": 11,
        "memory_type": "thread_update",
        "summary": f"{npc_id} observed a promise at the cove",
        "source_event_id": f"event_{npc_id}_1",
        "importance": 0.8,
        "observed": True,
        "tags": (f"thread:thread_{npc_id}", "promise", "location:cove", f"participant:{npc_id}"),
        "active": True,
    }
    data.update(overrides)
    return NpcShortMemory(**data)


def _long(npc_id: str = "luna", **overrides) -> NpcLongMemory:
    data = {
        "memory_id": f"long_{npc_id}_1",
        "npc_id": npc_id,
        "memory_type": "promise",
        "summary": f"{npc_id} remembers a durable promise",
        "source_event_id": f"event_{npc_id}_1",
        "source_short_memory_id": f"short_{npc_id}_1",
        "created_turn": 10,
        "last_reinforced_turn": 12,
        "importance": 0.9,
        "tags": (f"thread:thread_{npc_id}", "promise", "location:cove", f"participant:{npc_id}"),
        "status": "active",
        "active": True,
    }
    data.update(overrides)
    return NpcLongMemory(**data)


def _registry() -> NpcAgentRegistry:
    return NpcAgentRegistry(
        (
            NpcAgentState(
                npc_id="luna",
                persona_summary="careful",
                current_goal="protect the promise",
                current_intention="watch",
                emotion="alert",
                relationship_refs=("luna:player",),
                knowledge_refs=("luna:knowledge:0",),
                open_thread_ids=("thread_luna",),
                mission_refs=("mission_luna",),
                short_memories=(_short("luna"),),
                long_memories=(_long("luna"),),
                initiative_priority=9,
                next_evaluation_turn=12,
            ),
            NpcAgentState(
                npc_id="maria",
                persona_summary="direct",
                current_goal="finish the mission",
                current_intention="ask",
                emotion="focused",
                relationship_refs=("maria:player",),
                knowledge_refs=("maria:knowledge:0",),
                open_thread_ids=("thread_maria",),
                mission_refs=("mission_maria",),
                short_memories=(_short("maria"),),
                long_memories=(_long("maria"),),
                initiative_priority=3,
                next_evaluation_turn=12,
            ),
            NpcAgentState(
                npc_id="stella",
                persona_summary="distant",
                relationship_refs=("stella:player",),
                knowledge_refs=("stella:knowledge:0",),
                short_memories=(_short("stella", tags=("thread:thread_stella", "location:tower")),),
                long_memories=(_long("stella", tags=("thread:thread_stella", "location:tower")),),
                enabled=False,
            ),
        )
    )


def _request(**overrides) -> NpcCoordinatorRequest:
    data = {
        "registry": _registry(),
        "world_state": _world_state(),
        "current_turn": 12,
        "present_npc_ids": ("luna", "maria"),
        "mentioned_npc_ids": ("stella",),
        "speaker_id": "luna",
        "actor_id": "maria",
        "reactor_id": "luna",
        "required_intervention_ids": ("maria",),
        "active_thread_ids": ("thread_luna", "thread_maria"),
        "active_mission_ids": ("mission_luna", "mission_maria"),
        "location_id": "cove",
        "player_input": "promise mission cove",
        "max_agents": 2,
        "retrieval_policy": NpcMemoryRetrievalPolicy(max_short_memories_per_npc=1, max_long_memories_per_npc=1),
    }
    data.update(overrides)
    return NpcCoordinatorRequest(**data)


def test_agent_context_minimum_validation_round_trip_and_immutability():
    context = NpcAgentContext(npc_id="luna")

    assert context.npc_id == "luna"
    assert NpcAgentContext.from_dict(context.to_dict()) == context
    with pytest.raises(ValueError):
        NpcAgentContext(npc_id="")
    with pytest.raises(FrozenInstanceError):
        context.npc_id = "maria"


def test_agent_context_complete_and_llm_structural_payload():
    context = NpcAgentContext.from_agent_state(
        _registry().get("luna"),
        selected_short_memories=(_short("luna"),),
        selected_long_memories=(_long("luna"),),
        selection_reasons=("present", "speaker"),
    )

    payload = context.to_llm_context_dict()
    assert context.relationship_refs == ("luna:player",)
    assert context.knowledge_refs == ("luna:knowledge:0",)
    assert payload["npc_id"] == "luna"
    assert payload["goal"] == "protect the promise"
    assert payload["short_memories"][0]["memory_id"] == "short_luna_1"
    assert "dialogue" not in payload
    assert "proposed_action" not in payload


def test_coordinator_empty_registry_result_is_serializable():
    result = coordinate_npc_agents(
        NpcCoordinatorRequest(
            registry=NpcAgentRegistry(),
            world_state=_world_state(),
            current_turn=12,
        )
    )

    assert result == NpcCoordinatorResult(
        selected_agent_ids=(),
        excluded_agent_ids=(),
        agent_contexts=(),
        selection_reasons=(),
        diagnostics={"selected_agents": [], "excluded_agents": [], "agent_contexts": {}},
    )
    assert result.to_dict()["agent_contexts"] == []


def test_coordinator_reuses_selector_order_and_reason_codes():
    result = coordinate_npc_agents(_request())

    assert result.selected_agent_ids == ("luna", "maria")
    assert result.excluded_agent_ids == ("stella",)
    assert [context.npc_id for context in result.agent_contexts] == ["luna", "maria"]
    reasons = dict(result.selection_reasons)
    assert "speaker" in reasons["luna"]
    assert "required_intervention" in reasons["maria"]
    assert reasons["stella"] == ("disabled",)


def test_coordinator_respects_max_agents_without_reordering_after_selector():
    result = coordinate_npc_agents(_request(max_agents=1))

    assert result.selected_agent_ids == ("luna",)
    assert result.excluded_agent_ids == ("maria", "stella")
    assert dict(result.selection_reasons)["maria"][-1] == "over_budget"


def test_coordinator_reuses_retrieval_and_respects_memory_limits():
    policy = NpcMemoryRetrievalPolicy(max_short_memories_per_npc=0, max_long_memories_per_npc=1)
    result = coordinate_npc_agents(_request(retrieval_policy=policy, max_agents=1))
    context = result.agent_contexts[0]

    assert context.npc_id == "luna"
    assert context.selected_short_memories == ()
    assert [memory.memory_id for memory in context.selected_long_memories] == ["long_luna_1"]
    diagnostics = result.diagnostics["agent_contexts"]["luna"]
    assert diagnostics["short_excluded"] == ["short_luna_1"]
    assert diagnostics["reasons"]["short_luna_1"] == "over_budget"


def test_coordinator_keeps_contexts_isolated_per_npc():
    result = coordinate_npc_agents(_request())
    contexts = {context.npc_id: context for context in result.agent_contexts}

    assert contexts["luna"].relationship_refs == ("luna:player",)
    assert contexts["maria"].relationship_refs == ("maria:player",)
    assert contexts["luna"].knowledge_refs == ("luna:knowledge:0",)
    assert contexts["maria"].knowledge_refs == ("maria:knowledge:0",)
    assert contexts["luna"].open_thread_ids == ("thread_luna",)
    assert contexts["maria"].open_thread_ids == ("thread_maria",)
    assert contexts["luna"].mission_refs == ("mission_luna",)
    assert contexts["maria"].mission_refs == ("mission_maria",)
    assert [memory.npc_id for memory in contexts["luna"].selected_short_memories] == ["luna"]
    assert [memory.npc_id for memory in contexts["maria"].selected_long_memories] == ["maria"]


def test_coordinator_does_not_mutate_registry_world_state_or_request():
    request = _request()
    registry_before = request.registry
    world_before = request.world_state.to_dict()

    result = coordinate_npc_agents(request)

    assert coordinate_npc_agents(request) == result
    assert request.registry == registry_before
    assert request.world_state.to_dict() == world_before
    assert request == _request()


def test_coordinator_result_llm_payload_is_structural_only():
    result = coordinate_npc_agents(_request(max_agents=1))
    payload = result.to_llm_context_dict()

    assert list(payload) == ["active_agents"]
    assert payload["active_agents"][0]["npc_id"] == "luna"
    assert "dialogue" not in payload["active_agents"][0]
    assert "proposed_action" not in payload["active_agents"][0]
    assert "proposed_intention" not in payload["active_agents"][0]


def test_coordinator_diagnostics_are_stable_and_serializable():
    first = build_npc_coordinator_diagnostics(coordinate_npc_agents(_request()))
    second = build_npc_coordinator_diagnostics(coordinate_npc_agents(_request()))

    assert first == second
    assert first["selected_agents"] == ["luna", "maria"]
    assert first["excluded_agents"] == ["stella"]
    assert first["agent_contexts"]["luna"]["short_selected"] == ["short_luna_1"]
    assert first["agent_contexts"]["maria"]["long_selected"] == ["long_maria_1"]
    assert "prompt" not in first

