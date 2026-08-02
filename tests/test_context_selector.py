import json
from copy import deepcopy
from pathlib import Path

import pytest

from epos.context_budget import ContextBudget
from epos.context_diagnostics import compare_context_size, estimate_context_size
from epos.context_selector import (
    ContextSelectionRequest,
    context_selector_enabled,
    select_context,
)
from epos.models import MemoryEvent, Thread, add_knowledge
from epos.prompt import build_snapshot, phase1_messages, phase2_messages
from epos.prompt_snapshot import _build_full_snapshot
from epos.contract import CheckProposal
from epos.rules import Outcome, Roll
from epos.worldpack import load_pack


DEMO_PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"
ODYSSEY_PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


def _demo():
    pack = load_pack(DEMO_PACK)
    state = pack.new_world("context-selector")
    return pack, state


def _odyssey():
    pack = load_pack(ODYSSEY_PACK)
    state = pack.new_world("context-selector-odyssey")
    return pack, state


def _request(pack, state, text="Parlo con Maera.", budget=None):
    full = _build_full_snapshot(state, pack, text)
    return ContextSelectionRequest(
        world_state=state,
        world_pack=pack,
        player_input=text,
        phase="phase1",
        full_snapshot=full,
        budget=budget or ContextBudget(),
    )


def test_context_selector_flag_parsing(monkeypatch):
    monkeypatch.delenv("EPOS_CONTEXT_SELECTOR_ENABLED", raising=False)
    assert context_selector_enabled() is False
    for value in ("true", "1", "yes", "on"):
        assert context_selector_enabled(value) is True
    for value in ("false", "0", "no", "off", ""):
        assert context_selector_enabled(value) is False
    with pytest.raises(ValueError):
        context_selector_enabled("maybe")


def test_context_budget_is_immutable_and_rejects_negative_values():
    budget = ContextBudget(max_active_npcs=2)
    with pytest.raises(Exception):
        budget.max_active_npcs = 4
    with pytest.raises(ValueError):
        ContextBudget(max_open_threads=-1)


def test_flag_disabled_preserves_legacy_snapshot_and_prompts(monkeypatch):
    pack, state = _demo()
    monkeypatch.delenv("EPOS_CONTEXT_SELECTOR_ENABLED", raising=False)
    proposal = CheckProposal(
        action_kind="social",
        skill="dolos",
        difficulty=2,
        target_ids=["maera"],
        opposition="npc_resistance",
        reason="Maera decide se fidarsi.",
        stakes={
            "full_success": "ok",
            "partial_success": "partial",
            "failure": "fail",
            "critical_failure": "bad",
        },
    )
    roll = Roll(pool_size=3, difficulty=2, dice=(4, 2), outcome=Outcome.PARTIAL_SUCCESS)

    assert build_snapshot(state, pack, "Chiedo a Maera.") == _build_full_snapshot(
        state, pack, "Chiedo a Maera."
    )
    phase1 = phase1_messages(state, pack, "Chiedo a Maera.")[-1]["content"]
    monkeypatch.setenv("EPOS_CONTEXT_SELECTOR_ENABLED", "false")
    assert phase1_messages(state, pack, "Chiedo a Maera.")[-1]["content"] == phase1
    phase2 = phase2_messages(
        state, pack, "Chiedo a Maera.", proposal.to_dict(), roll.to_dict(), "partial"
    )[-1]["content"]
    assert (
        phase2_messages(
            state, pack, "Chiedo a Maera.", proposal.to_dict(), roll.to_dict(), "partial"
        )[-1]["content"]
        == phase2
    )


def test_enabled_selector_includes_present_npc_and_excludes_absent_npc(monkeypatch):
    pack, state = _demo()
    state.npcs["corren"].present = False
    monkeypatch.setenv("EPOS_CONTEXT_SELECTOR_ENABLED", "true")

    snapshot = build_snapshot(state, pack, "Parlo con Maera e nomino Corren.")

    assert [npc["id"] for npc in snapshot["present_npcs"]] == ["maera"]
    result = select_context(_request(pack, state, "Parlo con Maera e nomino Corren."))
    assert result.diagnostics["included_npcs"] == ["maera"]
    assert "corren" not in result.diagnostics["included_npcs"]
    assert "excluded_not_present" in result.diagnostics["reasons"]["corren"]


def test_selector_respects_npc_limit_and_stable_order():
    pack, state = _odyssey()
    for npc in state.npcs.values():
        npc.present = True
        npc.location_id = state.location_id

    result = select_context(_request(pack, state, "Osservo tutti.", ContextBudget(max_active_npcs=3)))
    again = select_context(_request(pack, state, "Osservo tutti.", ContextBudget(max_active_npcs=3)))

    assert result.included_npcs == tuple(list(state.npcs.keys())[:3])
    assert result.to_dict() == again.to_dict()


def test_selector_filters_threads_and_excludes_closed_threads():
    pack, state = _demo()
    state.npcs["corren"].present = True
    state.open_thread(
        Thread(
            id="open-maera",
            type="question",
            participants=["player", "maera"],
            summary="Domanda aperta.",
            opened_turn=0,
            close_condition="Maera risponde.",
        )
    )
    state.active_threads.append(
        Thread(
            id="closed-corren",
            type="question",
            participants=["player", "corren"],
            summary="Domanda chiusa.",
            opened_turn=0,
            status="closed",
            close_condition="Corren risponde.",
            closed_turn=1,
        )
    )

    result = select_context(_request(pack, state, "Chiedo a Maera.", ContextBudget(max_open_threads=1)))

    assert result.included_threads == ("open-maera",)
    assert [thread["id"] for thread in result.selected_snapshot["active_threads"]] == ["open-maera"]


def test_selector_limits_missions_and_excludes_non_pertinent_missions():
    pack, state = _odyssey()
    result = select_context(
        _request(pack, state, "Osservo la caverna.", ContextBudget(max_missions=1))
    )

    assert result.included_missions == ("mission_ciclopi",)
    assert "mission_eolo" in result.excluded_missions
    assert [m["id"] for m in result.selected_snapshot["missions"]["current"]] == [
        "mission_ciclopi"
    ]


def test_selector_limits_events_and_knowledge_without_contamination():
    pack, state = _demo()
    npc = state.npcs["maera"]
    for index in range(6):
        npc.memories.append(
            MemoryEvent(
                summary=f"Maera observed event {index}",
                witnesses=["maera"],
                source="observed",
                turn=index,
            )
        )
        add_knowledge(npc, f"Maera fact {index}", source="observed", turn=index)
        add_knowledge(state.player, f"Player fact {index}", source="observed", turn=index)
    state.npcs["corren"].knowledge.append("Corren private fact")

    result = select_context(
        _request(
            pack,
            state,
            "Parlo con Maera.",
            ContextBudget(max_recent_events=2, max_knowledge_entries=3),
        )
    )
    selected_maera = result.selected_snapshot["present_npcs"][0]

    assert selected_maera["recent_memories"] == [
        "Maera observed event 4",
        "Maera observed event 5",
    ]
    assert selected_maera["knowledge"] == ["Maera fact 3", "Maera fact 4", "Maera fact 5"]
    assert result.selected_snapshot["player_knowledge"] == [
        "Player fact 3",
        "Player fact 4",
        "Player fact 5",
    ]
    assert "Corren private fact" not in json.dumps(
        result.selected_snapshot, ensure_ascii=False
    )


def test_selector_preserves_player_location_time_and_outfit_and_does_not_mutate_state():
    pack, state = _demo()
    before_state = deepcopy(state.to_dict())
    result = select_context(_request(pack, state, "Parlo con Maera."))
    snapshot = result.selected_snapshot

    assert snapshot["location"]["id"] == state.location_id
    assert snapshot["time_phase"] == state.time_phase
    assert snapshot["player"]["outfit_state"] == _build_full_snapshot(
        state, pack, "Parlo con Maera."
    )["player"]["outfit_state"]
    assert state.to_dict() == before_state


def test_context_size_estimates_are_deterministic_and_reduction_is_reported():
    pack, state = _odyssey()
    for npc in state.npcs.values():
        npc.present = True
        npc.location_id = state.location_id
        for index in range(4):
            npc.memories.append(
                MemoryEvent(
                    summary=f"{npc.id} observed {index}",
                    witnesses=[npc.id],
                    source="observed",
                    turn=index,
                )
            )
    full = _build_full_snapshot(state, pack, "Osservo la sala.")
    selected = select_context(
        _request(
            pack,
            state,
            "Osservo la sala.",
            ContextBudget(max_active_npcs=3, max_missions=1, max_recent_events=2),
        )
    ).selected_snapshot

    before = estimate_context_size(full)
    after = estimate_context_size(selected)
    comparison = compare_context_size(full, selected)

    assert before == estimate_context_size(full)
    assert after["characters"] < before["characters"]
    assert comparison["estimated_tokens_after"] < comparison["estimated_tokens_before"]
    assert comparison["reduction_percent"] > 0
    result = select_context(
        _request(
            pack,
            state,
            "Osservo la sala.",
            ContextBudget(max_active_npcs=3, max_missions=1, max_recent_events=2),
        )
    )
    assert result.diagnostics["characters_before"] == before["characters"]



def test_small_medium_large_metrics_cover_snapshot_and_phase_prompts(monkeypatch):
    proposal = CheckProposal(
        action_kind="social",
        skill="dolos",
        difficulty=2,
        target_ids=["maera"],
        opposition="npc_resistance",
        reason="x",
        stakes={
            "full_success": "a",
            "partial_success": "b",
            "failure": "c",
            "critical_failure": "d",
        },
    )
    roll = Roll(pool_size=3, difficulty=2, dice=(1, 2), outcome=Outcome.FAILURE)

    small_pack, small_state = _demo()
    medium_pack, medium_state = _odyssey()
    large_pack, large_state = _odyssey()
    for npc in medium_state.npcs.values():
        npc.present = npc.location_id == medium_state.location_id
    for npc in large_state.npcs.values():
        npc.present = True
        npc.location_id = large_state.location_id
        for index in range(4):
            npc.memories.append(
                MemoryEvent(
                    summary=f"{npc.id} observed {index}",
                    witnesses=[npc.id],
                    source="observed",
                    turn=index,
                )
            )

    scenarios = [
        ("small", small_pack, small_state, False),
        ("medium", medium_pack, medium_state, True),
        ("large", large_pack, large_state, True),
    ]
    reductions = []
    for _name, pack, state, should_reduce in scenarios:
        monkeypatch.setenv("EPOS_CONTEXT_SELECTOR_ENABLED", "false")
        full_snapshot = build_snapshot(state, pack, "Osservo la sala.")
        full_phase1 = phase1_messages(state, pack, "Osservo la sala.")[-1]["content"]
        full_phase2 = phase2_messages(
            state, pack, "Osservo la sala.", proposal.to_dict(), roll.to_dict(), "c"
        )[-1]["content"]

        monkeypatch.setenv("EPOS_CONTEXT_SELECTOR_ENABLED", "true")
        selected_snapshot = build_snapshot(state, pack, "Osservo la sala.")
        selected_phase1 = phase1_messages(state, pack, "Osservo la sala.")[-1]["content"]
        selected_phase2 = phase2_messages(
            state, pack, "Osservo la sala.", proposal.to_dict(), roll.to_dict(), "c"
        )[-1]["content"]

        comparison = compare_context_size(full_snapshot, selected_snapshot)
        assert comparison["estimated_tokens_before"] == estimate_context_size(full_snapshot)[
            "estimated_tokens"
        ]
        assert selected_snapshot["location"]
        assert selected_snapshot["time_phase"] == state.time_phase
        assert selected_snapshot["player"]
        if should_reduce:
            assert comparison["characters_after"] < comparison["characters_before"]
            assert len(selected_phase1) < len(full_phase1)
            assert len(selected_phase2) < len(full_phase2)
            reductions.append(comparison["reduction_percent"])
        else:
            assert comparison["characters_after"] <= comparison["characters_before"]

    assert len(reductions) == 2
    assert sum(reductions) / len(reductions) > 0
