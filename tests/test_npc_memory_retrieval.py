from dataclasses import FrozenInstanceError

import pytest

from epos.npc_agent_models import NpcAgentState
from epos.npc_agent_registry import NpcAgentRegistry
from epos.npc_memory_long import NpcLongMemory
from epos.npc_memory_retrieval import (
    NpcMemoryRetrievalRequest,
    NpcMemoryRetrievalResult,
    retrieve_memories,
    retrieve_memories_for_npc,
)
from epos.npc_memory_retrieval_diagnostics import build_memory_retrieval_diagnostics
from epos.npc_memory_retrieval_policy import NpcMemoryRetrievalPolicy
from epos.npc_memory_short import NpcShortMemory


def _short(**overrides):
    data = {
        "memory_id": "short_maera_1",
        "npc_id": "maera",
        "turn": 10,
        "memory_type": "thread_update",
        "summary": "Maera heard Corren promise help at the cove",
        "source_event_id": "event_1",
        "importance": 0.7,
        "observed": True,
        "tags": ("thread:thread_cove", "promise", "participant:corren", "location:cove"),
        "active": True,
    }
    data.update(overrides)
    return NpcShortMemory(**data)


def _long(**overrides):
    data = {
        "memory_id": "long_maera_1",
        "npc_id": "maera",
        "memory_type": "promise",
        "summary": "Corren promised Maera protection during the storm",
        "source_event_id": "event_1",
        "source_short_memory_id": "short_maera_1",
        "created_turn": 10,
        "last_reinforced_turn": 12,
        "importance": 0.85,
        "tags": ("promise", "thread:thread_cove", "participant:corren", "location:cove"),
        "status": "active",
        "active": True,
    }
    data.update(overrides)
    return NpcLongMemory(**data)


def _request(**overrides):
    data = {
        "npc_id": "maera",
        "short_memories": (_short(),),
        "long_memories": (_long(),),
        "current_turn": 12,
        "location_id": "cove",
        "player_input": "Corren promise at cove",
        "active_thread_ids": ("thread_cove",),
        "active_mission_ids": ("mission_a",),
        "relevant_tags": ("promise",),
        "relevant_memory_types": ("promise", "thread_update"),
        "participant_ids": ("corren",),
    }
    data.update(overrides)
    return NpcMemoryRetrievalRequest(**data)


def test_retrieval_policy_default_and_round_trip():
    policy = NpcMemoryRetrievalPolicy()

    assert policy.max_short_memories_per_npc == 4
    assert policy.max_long_memories_per_npc == 3
    assert policy.minimum_score == 0.0
    assert NpcMemoryRetrievalPolicy.from_dict(policy.to_dict()) == policy
    with pytest.raises(FrozenInstanceError):
        policy.minimum_score = 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_short_memories_per_npc": -1},
        {"max_long_memories_per_npc": -1},
        {"minimum_score": -0.1},
        {"importance_weight": -1.0},
        {"recency_window_turns": 0},
    ],
)
def test_retrieval_policy_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        NpcMemoryRetrievalPolicy(**kwargs)


def test_request_and_empty_result_are_serializable():
    request = NpcMemoryRetrievalRequest(npc_id="maera")
    result = retrieve_memories(request)

    assert request.participant_ids == ("maera",)
    assert result.to_dict() == {
        "npc_id": "maera",
        "selected_short_memories": [],
        "selected_long_memories": [],
        "excluded_short_memory_ids": [],
        "excluded_long_memory_ids": [],
        "scores": {},
        "reasons": {},
    }
    assert NpcMemoryRetrievalResult(npc_id="maera").to_dict()["npc_id"] == "maera"


def test_retrieval_selects_short_and_long_with_deterministic_scores():
    request = _request()

    first = retrieve_memories(request)
    second = retrieve_memories(request)

    assert first == second
    assert [memory.memory_id for memory in first.selected_short_memories] == ["short_maera_1"]
    assert [memory.memory_id for memory in first.selected_long_memories] == ["long_maera_1"]
    score_map = {score.memory_id: score.to_dict()["components"] for score in first.scores}
    assert score_map["short_maera_1"]["importance"] == 0.7
    assert score_map["short_maera_1"]["recency"] == pytest.approx(0.333333)
    assert score_map["short_maera_1"]["thread_match"] == 0.9
    assert "recency" not in score_map["long_maera_1"]


def test_retrieval_applies_limits_minimum_score_and_tie_break():
    memories = (
        _short(memory_id="short_maera_b", importance=0.5, turn=10),
        _short(memory_id="short_maera_a", importance=0.5, turn=10, source_event_id="event_2"),
        _short(memory_id="short_maera_c", importance=0.4, turn=11, source_event_id="event_3"),
    )
    policy = NpcMemoryRetrievalPolicy(
        max_short_memories_per_npc=1,
        max_long_memories_per_npc=0,
        minimum_score=0.0,
        recency_weight=0.0,
        type_match_weight=0.0,
        tag_match_weight=0.0,
        thread_match_weight=0.0,
        mission_match_weight=0.0,
        location_match_weight=0.0,
        participant_match_weight=0.0,
        text_match_weight=0.0,
    )
    result = retrieve_memories(_request(short_memories=memories, long_memories=(), policy=policy))

    assert [memory.memory_id for memory in result.selected_short_memories] == ["short_maera_a"]
    assert set(result.excluded_short_memory_ids) == {"short_maera_b", "short_maera_c"}
    assert dict(result.reasons)["short_maera_b"] == "over_budget"

    high_minimum = retrieve_memories(_request(policy=NpcMemoryRetrievalPolicy(minimum_score=10.0)))
    assert high_minimum.selected_short_memories == ()
    assert high_minimum.selected_long_memories == ()
    assert dict(high_minimum.reasons)["short_maera_1"] == "below_minimum_score"


def test_retrieval_pre_filters_short_memories_with_reason_codes():
    memories = (
        _short(memory_id="short_wrong", npc_id="corren", source_event_id="event_wrong"),
        _short(memory_id="short_unseen", observed=False, source_event_id="event_unseen"),
        _short(memory_id="short_inactive", active=False, source_event_id="event_inactive"),
        _short(memory_id="short_missing_source", source_event_id=""),
        _short(memory_id="short_valid", source_event_id="event_valid"),
    )

    result = retrieve_memories(_request(short_memories=memories, long_memories=()))
    reasons = dict(result.reasons)

    assert [memory.memory_id for memory in result.selected_short_memories] == ["short_valid"]
    assert reasons["short_wrong"] == "wrong_npc"
    assert reasons["short_unseen"] == "not_observed"
    assert reasons["short_inactive"] == "inactive"
    assert reasons["short_missing_source"] == "missing_provenance"


def test_retrieval_pre_filters_long_memories_with_reason_codes():
    memories = (
        _long(memory_id="long_wrong", npc_id="corren", source_event_id="event_wrong", source_short_memory_id="short_wrong"),
        _long(memory_id="long_inactive", active=False, source_event_id="event_inactive", source_short_memory_id="short_inactive"),
        _long(memory_id="long_resolved", status="resolved", source_event_id="event_resolved", source_short_memory_id="short_resolved"),
        _long(memory_id="long_valid", source_event_id="event_valid", source_short_memory_id="short_valid"),
    )

    result = retrieve_memories(_request(short_memories=(), long_memories=memories))
    reasons = dict(result.reasons)

    assert [memory.memory_id for memory in result.selected_long_memories] == ["long_valid"]
    assert reasons["long_wrong"] == "wrong_npc"
    assert reasons["long_inactive"] == "inactive"
    assert reasons["long_resolved"] == "resolved"


def test_retrieval_scores_all_allowed_components():
    memory = _short(
        tags=(
            "promise",
            "thread:thread_cove",
            "mission:mission_a",
            "location:cove",
            "participant:corren",
        ),
        summary="Corren promise mission cove",
        memory_type="mission_event",
        importance=0.8,
        turn=12,
    )

    result = retrieve_memories(
        _request(
            short_memories=(memory,),
            long_memories=(),
            relevant_memory_types=("mission_event",),
            player_input="promise mission",
        )
    )
    components = result.scores[0].to_dict()["components"]

    assert components["importance"] == 0.8
    assert components["recency"] == 0.4
    assert components["type_match"] == 0.8
    assert components["tag_match"] == 0.6
    assert components["thread_match"] == 0.9
    assert components["mission_match"] == 0.9
    assert components["location_match"] == 0.5
    assert components["participant_match"] == 0.7
    assert components["text_match"] == 0.3


def test_long_memory_priority_is_importance_based_not_short_recency_decay():
    long_memory = _long(memory_id="long_maera_old_secret", memory_type="secret", importance=1.0, created_turn=1, last_reinforced_turn=1)
    short_memory = _short(memory_id="short_maera_recent", importance=0.2, turn=12, source_event_id="event_recent")

    result = retrieve_memories(
        _request(
            short_memories=(short_memory,),
            long_memories=(long_memory,),
            relevant_memory_types=("secret",),
            player_input="secret",
        )
    )
    long_score = next(score for score in result.scores if score.memory_id == "long_maera_old_secret")

    assert result.selected_long_memories == (long_memory,)
    assert "recency" not in long_score.to_dict()["components"]
    assert long_score.total > 1.0


def test_text_matching_is_exact_lowercase_and_not_fuzzy_or_synonym_based():
    memory = _short(
        memory_id="short_maera_text",
        summary="The bronze key opened the cove shrine",
        tags=("Key_Item",),
    )

    lower = retrieve_memories(_request(short_memories=(memory,), long_memories=(), player_input="BRONZE"))
    tag = retrieve_memories(_request(short_memories=(memory,), long_memories=(), player_input="key_item"))
    stopword = retrieve_memories(_request(short_memories=(memory,), long_memories=(), player_input="the and of"))
    fuzzy = retrieve_memories(_request(short_memories=(memory,), long_memories=(), player_input="bronzed"))
    synonym = retrieve_memories(_request(short_memories=(memory,), long_memories=(), player_input="copper"))

    assert "text_match" in lower.scores[0].to_dict()["components"]
    assert "tag_match" in tag.scores[0].to_dict()["components"]
    assert "text_match" not in stopword.scores[0].to_dict()["components"]
    assert "text_match" not in fuzzy.scores[0].to_dict()["components"]
    assert "text_match" not in synonym.scores[0].to_dict()["components"]
    assert memory.summary == "The bronze key opened the cove shrine"


def test_retrieval_preserves_npc_isolation_and_inputs():
    maera_memory = _short(memory_id="short_maera_isolated", source_event_id="event_maera")
    corren_memory = _short(memory_id="short_corren_isolated", npc_id="corren", source_event_id="event_corren")
    request = _request(short_memories=(maera_memory, corren_memory), long_memories=())

    before = request
    result = retrieve_memories(request)

    assert request == before
    assert maera_memory in result.selected_short_memories
    assert corren_memory not in result.selected_short_memories
    assert "short_corren_isolated" in result.excluded_short_memory_ids
    assert dict(result.reasons)["short_corren_isolated"] == "wrong_npc"


def test_registry_helper_retrieves_only_requested_npc_without_mutating_registry():
    maera_state = NpcAgentState(npc_id="maera", short_memories=(_short(),), long_memories=(_long(),))
    corren_state = NpcAgentState(
        npc_id="corren",
        short_memories=(_short(memory_id="short_corren_1", npc_id="corren", source_event_id="event_corren"),),
    )
    registry = NpcAgentRegistry((maera_state, corren_state))

    result = retrieve_memories_for_npc(
        registry,
        "maera",
        current_turn=12,
        player_input="promise",
        active_thread_ids=("thread_cove",),
        relevant_tags=("promise",),
    )

    assert [memory.memory_id for memory in result.selected_short_memories] == ["short_maera_1"]
    assert registry.get("maera") == maera_state
    assert registry.get("corren") == corren_state
    assert retrieve_memories_for_npc(registry, "stella").to_dict()["selected_short_memories"] == []


def test_retrieval_diagnostics_are_serializable_and_do_not_include_prompt_text():
    result = retrieve_memories(
        _request(policy=NpcMemoryRetrievalPolicy(max_short_memories_per_npc=0, max_long_memories_per_npc=1))
    )

    diagnostics = build_memory_retrieval_diagnostics(result)

    assert diagnostics["npc_id"] == "maera"
    assert diagnostics["selected_long"] == ["long_maera_1"]
    assert diagnostics["excluded"]["short_maera_1"] == "over_budget"
    assert diagnostics["counts"]["excluded_short"] == 1
    assert "prompt" not in diagnostics

