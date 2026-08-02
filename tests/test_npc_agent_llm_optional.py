from dataclasses import FrozenInstanceError

import pytest

from epos.models import NpcState, PlayerState, Thread, WorldState
from epos.npc_agent_context import NpcAgentContext
from epos.npc_agent_coordinator import NpcCoordinatorRequest, coordinate_npc_agents
from epos.npc_agent_llm_contract import (
    NpcDedicatedLlmBudget,
    NpcDedicatedLlmRequest,
    NpcDedicatedLlmResponse,
    NpcDedicatedLlmRunResult,
    NpcLlmProposal,
)
from epos.npc_agent_llm_diagnostics import build_npc_dedicated_llm_diagnostics
from epos.npc_agent_llm_runner import (
    EPOS_NPC_DEDICATED_LLM_ENABLED,
    npc_dedicated_llm_enabled_from_env,
    parse_npc_dedicated_llm_enabled,
    run_optional_npc_llm,
)
from epos.npc_agent_llm_validator import (
    ALLOWED_PROPOSAL_FIELDS,
    FORBIDDEN_AUTHORITATIVE_FIELDS,
    validate_npc_llm_payload,
)
from epos.npc_agent_models import NpcAgentState
from epos.npc_agent_registry import NpcAgentRegistry
from epos.npc_memory_long import NpcLongMemory
from epos.npc_memory_short import NpcShortMemory


class FakeNpcProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete_json(self, payload):
        self.calls.append(payload)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _world_state():
    return WorldState(
        session_id="session",
        turn=12,
        time_phase="day",
        location_id="cove",
        player=PlayerState(name="Player", location_id="cove"),
        npcs={
            "luna": NpcState(id="luna", name="Luna", age=30, location_id="cove", present=True),
            "maria": NpcState(id="maria", name="Maria", age=31, location_id="cove", present=True),
        },
        active_threads=[
            Thread(
                id="thread_luna",
                type="promise",
                participants=["luna"],
                summary="Luna waits.",
                opened_turn=10,
            )
        ],
    )


def _short(npc_id="luna"):
    return NpcShortMemory(
        memory_id=f"short_{npc_id}_1",
        npc_id=npc_id,
        turn=11,
        memory_type="thread_update",
        summary=f"{npc_id} observed a promise",
        source_event_id=f"event_{npc_id}_1",
        importance=0.8,
        tags=(f"thread:thread_{npc_id}", "promise", f"participant:{npc_id}", "location:cove"),
    )


def _long(npc_id="luna"):
    return NpcLongMemory(
        memory_id=f"long_{npc_id}_1",
        npc_id=npc_id,
        memory_type="promise",
        summary=f"{npc_id} remembers a promise",
        source_event_id=f"event_{npc_id}_1",
        source_short_memory_id=f"short_{npc_id}_1",
        created_turn=10,
        last_reinforced_turn=12,
        importance=0.9,
        tags=(f"thread:thread_{npc_id}", "promise", f"participant:{npc_id}", "location:cove"),
    )


def _registry():
    return NpcAgentRegistry(
        (
            NpcAgentState(
                npc_id="luna",
                current_goal="protect the promise",
                current_intention="watch",
                emotion="alert",
                relationship_refs=("luna:player",),
                knowledge_refs=("luna:knowledge:0",),
                open_thread_ids=("thread_luna",),
                short_memories=(_short("luna"),),
                long_memories=(_long("luna"),),
                initiative_priority=9,
                next_evaluation_turn=12,
            ),
            NpcAgentState(
                npc_id="maria",
                current_goal="keep peace",
                knowledge_refs=("maria:knowledge:0",),
                short_memories=(_short("maria"),),
                long_memories=(_long("maria"),),
                initiative_priority=3,
                next_evaluation_turn=12,
            ),
        )
    )


def _coordinator_result(max_agents=2):
    return coordinate_npc_agents(
        NpcCoordinatorRequest(
            registry=_registry(),
            world_state=_world_state(),
            current_turn=12,
            present_npc_ids=("luna", "maria"),
            speaker_id="luna",
            active_thread_ids=("thread_luna",),
            location_id="cove",
            player_input="promise at cove",
            max_agents=max_agents,
        )
    )


def _valid_payload(npc_id="luna", memory_id="short_luna_1"):
    return {
        "proposals": [
            {
                "npc_id": npc_id,
                "stance": "cautious",
                "intention_hint": "waits for clarification",
                "emotional_reaction": "alert",
                "response_priority": 50,
                "referenced_memory_ids": [memory_id],
                "dialogue_hint": "not authoritative",
            }
        ]
    }


@pytest.mark.parametrize("value", ["true", "1", "yes", "on"])
def test_feature_flag_true_values(value):
    assert parse_npc_dedicated_llm_enabled(value) is True


@pytest.mark.parametrize("value", [None, "", "false", "0", "no", "off"])
def test_feature_flag_false_values(value):
    assert parse_npc_dedicated_llm_enabled(value) is False


def test_feature_flag_invalid_and_env_default_false(monkeypatch):
    monkeypatch.delenv(EPOS_NPC_DEDICATED_LLM_ENABLED, raising=False)
    assert npc_dedicated_llm_enabled_from_env() is False
    with pytest.raises(ValueError):
        parse_npc_dedicated_llm_enabled("maybe")


def test_budget_default_zero_invalid_and_one_call_cap():
    budget = NpcDedicatedLlmBudget()
    assert budget.max_calls_per_turn == 1
    assert budget.max_agents_per_call == 3
    assert NpcDedicatedLlmBudget(max_calls_per_turn=0).max_calls_per_turn == 0
    with pytest.raises(ValueError):
        NpcDedicatedLlmBudget(max_calls_per_turn=2)
    with pytest.raises(ValueError):
        NpcDedicatedLlmBudget(max_agents_per_call=-1)


def test_contracts_round_trip_priority_limits_refs_and_frozen():
    context = _coordinator_result(max_agents=1).agent_contexts[0]
    request = NpcDedicatedLlmRequest(turn=12, location_id="cove", player_input="promise", agents=(context,))
    proposal = NpcLlmProposal(
        npc_id="luna",
        stance="cautious",
        response_priority=100,
        referenced_memory_ids=("short_luna_1", "short_luna_1"),
    )
    response = NpcDedicatedLlmResponse((proposal,))

    assert NpcDedicatedLlmRequest.from_dict(request.to_dict()) == request
    assert NpcDedicatedLlmResponse.from_dict(response.to_dict()) == response
    assert proposal.referenced_memory_ids == ("short_luna_1",)
    with pytest.raises(ValueError):
        NpcLlmProposal(npc_id="")
    with pytest.raises(ValueError):
        NpcLlmProposal(npc_id="luna", response_priority=101)
    with pytest.raises(FrozenInstanceError):
        proposal.stance = "changed"


def test_validator_accepts_valid_payload_and_rejects_invalid_json_shape():
    result = _coordinator_result(max_agents=1)

    valid = validate_npc_llm_payload(_valid_payload(), result, max_proposals=1)
    invalid = validate_npc_llm_payload([], result, max_proposals=1)

    assert valid.valid is True
    assert valid.response.proposals[0].npc_id == "luna"
    assert invalid.valid is False
    assert invalid.errors[0].code == "invalid_schema"


def test_validator_rejects_unknown_forbidden_duplicate_unknown_npc_and_limit():
    result = _coordinator_result(max_agents=1)
    payload = {
        "proposals": [
            {"npc_id": "luna", "stance": "ok", "referenced_memory_ids": [], "mutations": []},
            {"npc_id": "luna", "stance": "dupe", "referenced_memory_ids": []},
            {"npc_id": "maria", "unknown": "x", "referenced_memory_ids": []},
        ],
        "state_changes": [],
    }

    validation = validate_npc_llm_payload(payload, result, max_proposals=1)
    codes = {error.code for error in validation.errors}

    assert validation.valid is False
    assert "forbidden_field" in codes
    assert "duplicate_npc" in codes
    assert "unknown_npc" in codes
    assert "proposal_limit_exceeded" in codes
    assert "mutations" in FORBIDDEN_AUTHORITATIVE_FIELDS
    assert "stance" in ALLOWED_PROPOSAL_FIELDS


def test_validator_rejects_memory_reference_from_another_npc_and_bad_id():
    result = _coordinator_result(max_agents=2)

    wrong_ref = validate_npc_llm_payload(_valid_payload("luna", "short_maria_1"), result, max_proposals=2)
    bad_id = validate_npc_llm_payload(_valid_payload("Luna Display", "short_luna_1"), result, max_proposals=2)

    assert wrong_ref.errors[0].code == "invalid_memory_reference"
    assert bad_id.errors[0].code == "invalid_npc_id"


def test_runner_disabled_no_agents_and_budget_zero_do_not_call_provider():
    provider = FakeNpcProvider(_valid_payload())

    disabled = run_optional_npc_llm(
        enabled=False,
        coordinator_result=_coordinator_result(),
        turn=12,
        location_id="cove",
        player_input="promise",
        provider=provider,
    )
    no_agents = run_optional_npc_llm(
        enabled=True,
        coordinator_result=_coordinator_result(max_agents=0),
        turn=12,
        location_id="cove",
        player_input="promise",
        provider=provider,
    )
    budget_zero = run_optional_npc_llm(
        enabled=True,
        coordinator_result=_coordinator_result(),
        turn=12,
        location_id="cove",
        player_input="promise",
        provider=provider,
        budget=NpcDedicatedLlmBudget(max_calls_per_turn=0),
    )

    assert provider.calls == []
    assert disabled.diagnostics["reason"] == "disabled"
    assert no_agents.diagnostics["reason"] == "no_agents"
    assert budget_zero.diagnostics["reason"] == "budget_exhausted"


def test_runner_success_calls_provider_once_and_truncates_agents_deterministically():
    provider = FakeNpcProvider(_valid_payload())

    run = run_optional_npc_llm(
        enabled=True,
        coordinator_result=_coordinator_result(max_agents=2),
        turn=12,
        location_id="cove",
        player_input="promise",
        provider=provider,
        budget=NpcDedicatedLlmBudget(max_agents_per_call=1),
    )

    assert run.status == "success"
    assert len(provider.calls) == 1
    assert provider.calls[0]["agents"][0]["npc_id"] == "luna"
    assert [agent["npc_id"] for agent in provider.calls[0]["agents"]] == ["luna"]
    assert run.diagnostics["excluded_by_budget"] == ["maria"]
    assert run.diagnostics["call_count"] == 1
    assert run.response.proposals[0].npc_id == "luna"


@pytest.mark.parametrize(
    "provider_response,reason",
    [
        (RuntimeError("boom"), "provider_error"),
        ("not json", "invalid_json"),
        ("[]", "invalid_schema"),
        ({"proposals": [{"npc_id": "stella", "referenced_memory_ids": []}]}, "unknown_npc"),
        ({"proposals": [{"npc_id": "luna", "referenced_memory_ids": ["short_maria_1"]}]}, "invalid_memory_reference"),
        ({"proposals": [{"npc_id": "luna", "referenced_memory_ids": [], "outcome": "win"}]}, "forbidden_field"),
    ],
)
def test_runner_fallback_cases_are_safe(provider_response, reason):
    provider = FakeNpcProvider(provider_response)

    run = run_optional_npc_llm(
        enabled=True,
        coordinator_result=_coordinator_result(max_agents=1),
        turn=12,
        location_id="cove",
        player_input="promise",
        provider=provider,
    )

    assert run.status == "fallback"
    assert run.response.proposals == ()
    assert run.diagnostics["reason"] == reason
    assert run.diagnostics["call_count"] == 1


def test_runner_does_not_mutate_inputs_or_accept_unselected_npc_memories():
    coordinator_result = _coordinator_result(max_agents=2)
    before = coordinator_result.to_dict()
    provider = FakeNpcProvider(_valid_payload())

    run = run_optional_npc_llm(
        enabled=True,
        coordinator_result=coordinator_result,
        turn=12,
        location_id="cove",
        player_input="promise",
        provider=provider,
        budget=NpcDedicatedLlmBudget(max_agents_per_call=1),
    )

    assert run.status == "success"
    assert coordinator_result.to_dict() == before
    payload_text = str(provider.calls[0])
    assert "short_maria_1" not in payload_text
    assert "long_maria_1" not in payload_text


def test_runner_diagnostics_are_serializable_and_do_not_include_raw_response():
    provider = FakeNpcProvider(_valid_payload())
    run = run_optional_npc_llm(
        enabled=True,
        coordinator_result=_coordinator_result(max_agents=1),
        turn=12,
        location_id="cove",
        player_input="promise",
        provider=provider,
    )

    diagnostics = build_npc_dedicated_llm_diagnostics(run)

    assert diagnostics["status"] == "success"
    assert diagnostics["proposal_count"] == 1
    assert "raw_provider_response" not in diagnostics



