from __future__ import annotations

from pathlib import Path

import pytest

from epos.models import Thread, add_knowledge
from epos.npc_agent_models import NpcAgentState
from epos.npc_agent_registry import NpcAgentRegistry, bootstrap_npc_agent_registry, build_npc_agent_state
from epos.npc_agent_selector import NpcAgentSelectionRequest, select_active_npc_agents
from epos.worldpack import load_pack

PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


def _world():
    pack = load_pack(PACK)
    state = pack.new_world("npc-agent")
    return pack, state


def test_bootstrap_uses_canonical_world_state_refs_without_mutating_world_state():
    pack, state = _world()
    before = state.to_dict()
    maera = state.npcs["maera"]
    maera.current_intention = "watch the door"
    maera.emotional_state["mood"] = "wary"
    maera.relationship_towards("player").trust = 12
    add_knowledge(maera, "The guest knows the old passphrase.", source="observed", turn=2)
    state.open_thread(
        Thread(
            id="thread_maera",
            type="social",
            participants=["player", "maera"],
            summary="Maera weighs whether to trust the guest.",
            opened_turn=2,
        )
    )
    before_after_setup = state.to_dict()

    agent = build_npc_agent_state(state, "maera", pack)

    assert agent.npc_id == "maera"
    assert agent.persona_summary == "calma; osservatrice; pragmatica; protettiva del proprio territorio"
    assert agent.current_goal == "valutare se la forestiera è un problema o un'opportunità"
    assert agent.current_intention == "watch the door"
    assert agent.emotion == "wary"
    assert agent.relationship_refs == ("maera:player",)
    assert agent.knowledge_refs == ("maera:knowledge:0",)
    assert agent.open_thread_ids == ("thread_maera",)
    assert state.to_dict() == before_after_setup
    assert before != state.to_dict()


def test_bootstrap_registry_multiple_npcs_and_missing_data_defaults():
    pack, state = _world()

    registry = bootstrap_npc_agent_registry(state, pack)

    assert tuple(agent.npc_id for agent in registry.all()) == tuple(state.npcs)
    assert registry.get("corren").persona_summary
    assert registry.get("corren").current_intention == ""
    with pytest.raises(ValueError):
        build_npc_agent_state(state, "missing", pack)


def test_bootstrap_keeps_knowledge_relationships_and_threads_isolated():
    _pack, state = _world()
    maera = state.npcs["maera"]
    corren = state.npcs["corren"]
    maera.relationship_towards("player").trust = 10
    add_knowledge(maera, "Maera-only fact.", source="observed", turn=1)
    add_knowledge(corren, "Corren-only fact.", source="observed", turn=1)
    state.open_thread(
        Thread(
            id="thread_corren",
            type="lead",
            participants=["player", "corren"],
            summary="Corren watches the stables.",
            opened_turn=1,
        )
    )

    registry = bootstrap_npc_agent_registry(state)
    maera_agent = registry.get("maera")
    corren_agent = registry.get("corren")

    assert maera_agent.knowledge_refs == ("maera:knowledge:0",)
    assert corren_agent.knowledge_refs == ("corren:knowledge:0",)
    assert maera_agent.relationship_refs == ("maera:player",)
    assert corren_agent.relationship_refs == ()
    assert maera_agent.open_thread_ids == ()
    assert corren_agent.open_thread_ids == ("thread_corren",)


def test_selector_includes_present_explicit_roles_mentions_threads_and_missions():
    _pack, state = _world()
    state.npcs["corren"].present = False
    registry = NpcAgentRegistry(
        (
            NpcAgentState(npc_id="maera"),
            NpcAgentState(npc_id="corren", open_thread_ids=("thread_corren",), mission_refs=("mission_corren",)),
        )
    )

    result = select_active_npc_agents(
        NpcAgentSelectionRequest(
            registry=registry,
            world_state=state,
            turn=0,
            mentioned_npc_ids=("corren",),
            speaker_npc_id="maera",
            actor_npc_id="maera",
            reactor_npc_id="corren",
            active_thread_ids=("thread_corren",),
            active_mission_ids=("mission_corren",),
            required_intervention_ids=("corren",),
            max_agents=2,
        )
    )

    assert result.selected_ids == ("maera", "corren")
    reasons = result.reason_map()
    assert reasons["maera"] == ("present", "speaker", "actor", "next_evaluation_due")
    assert "required_intervention" in reasons["corren"]
    assert "reactor" in reasons["corren"]
    assert "mentioned" in reasons["corren"]
    assert "open_thread" in reasons["corren"]
    assert "active_mission" in reasons["corren"]
    assert "present" not in reasons["corren"]


def test_selector_excludes_absent_disabled_unknown_and_future_agents():
    _pack, state = _world()
    state.npcs["maera"].present = False
    registry = NpcAgentRegistry(
        (
            NpcAgentState(npc_id="maera", next_evaluation_turn=10),
            NpcAgentState(npc_id="corren", enabled=False),
            NpcAgentState(npc_id="ghost"),
        )
    )

    result = select_active_npc_agents(NpcAgentSelectionRequest(registry=registry, world_state=state, turn=1))

    assert result.selected_ids == ()
    assert result.excluded_ids == ("maera", "corren", "ghost")
    assert result.reason_map()["maera"] == ("not_relevant",)
    assert result.reason_map()["corren"] == ("disabled",)
    assert result.reason_map()["ghost"] == ("unknown_npc",)


def test_selector_priority_budget_order_and_repeatability_without_mutation():
    _pack, state = _world()
    state.npcs["corren"].present = True
    registry = NpcAgentRegistry(
        (
            NpcAgentState(npc_id="maera", initiative_priority=10),
            NpcAgentState(npc_id="corren", initiative_priority=80),
        )
    )
    before_state = state.to_dict()
    before_registry = registry.to_dict()
    request = NpcAgentSelectionRequest(registry=registry, world_state=state, turn=0, max_agents=1)

    first = select_active_npc_agents(request)
    second = select_active_npc_agents(request)

    assert first == second
    assert first.selected_ids == ("corren",)
    assert first.excluded_ids == ("maera",)
    assert "over_budget" in first.reason_map()["maera"]
    assert state.to_dict() == before_state
    assert registry.to_dict() == before_registry
    assert first.to_dict()["selected_ids"] == ["corren"]
