"""Fase 1: thread narrativi con criterio di chiusura validabile."""

from pathlib import Path

from epos.commit import apply_scene
from epos.contract import FinalScene, Mutation, VisualMoment
from epos.models import Thread
from epos.prompt import build_snapshot
from epos.validators import validate_scene
from epos.worldpack import load_pack

PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


def _visual():
    return VisualMoment(
        summary="Maera osserva il fuoco",
        focus_character="maera",
        visible_characters=["maera"],
        shared_action=False,
        visual_en="an innkeeper near the fire",
    )


def _scene(mutations):
    return FinalScene(narration="La questione resta sospesa.", mutations=mutations, visual=_visual())


def test_thread_roundtrip_preserves_close_condition_and_close_metadata():
    thread = Thread(
        id="t1",
        type="question",
        participants=["player", "maera"],
        summary="Chi e il corriere ferito?",
        opened_turn=2,
        close_condition="Maera rivela l'identita del corriere.",
        status="closed",
        closed_turn=5,
        close_reason="Identita rivelata.",
    )
    assert Thread.from_dict(thread.to_dict()) == thread


def test_thread_open_requires_close_condition():
    pack = load_pack(PACK)
    state = pack.new_world()
    scene = _scene([
        Mutation(
            type="thread_open",
            target="world",
            payload={
                "thread_id": "t1",
                "type": "question",
                "participants": ["player", "maera"],
                "summary": "Chi e il corriere ferito?",
            },
        )
    ])
    report = validate_scene(state, pack, scene)
    assert any("close_condition obbligatoria" in p for p in report.problems)


def test_thread_open_rejects_absent_participant():
    pack = load_pack(PACK)
    state = pack.new_world()
    scene = _scene([
        Mutation(
            type="thread_open",
            target="world",
            payload={
                "thread_id": "t1",
                "type": "question",
                "participants": ["player", "corren"],
                "summary": "Dov'e Corren?",
                "close_condition": "Corren entra in scena o qualcuno rivela dov'e.",
            },
        )
    ])
    report = validate_scene(state, pack, scene)
    assert any("partecipante assente" in p for p in report.problems)


def test_thread_open_and_close_record_metadata():
    pack = load_pack(PACK)
    state = pack.new_world()
    opening = _scene([
        Mutation(
            type="thread_open",
            target="world",
            payload={
                "thread_id": "t1",
                "type": "question",
                "participants": ["player", "maera"],
                "summary": "Chi e il corriere ferito?",
                "close_condition": "Maera rivela l'identita del corriere.",
            },
        )
    ])
    assert validate_scene(state, pack, opening).ok
    apply_scene(state, opening)
    thread = state.active_threads[0]
    assert thread.close_condition.startswith("Maera rivela")
    assert thread.opened_turn == 0

    state.turn = 3
    closing = _scene([
        Mutation(
            type="thread_close",
            target="world",
            payload={
                "thread_id": "t1",
                "reason": "Maera ha rivelato l'identita del corriere.",
            },
        )
    ])
    assert validate_scene(state, pack, closing).ok
    apply_scene(state, closing)
    assert thread.status == "closed"
    assert thread.closed_turn == 3
    assert "Maera" in thread.close_reason


def test_thread_close_requires_reason():
    pack = load_pack(PACK)
    state = pack.new_world()
    state.open_thread(
        Thread(
            id="t1",
            type="question",
            participants=["player", "maera"],
            summary="Chi e il corriere ferito?",
            opened_turn=0,
            close_condition="Maera rivela l'identita del corriere.",
        )
    )
    scene = _scene([
        Mutation(type="thread_close", target="world", payload={"thread_id": "t1"})
    ])
    report = validate_scene(state, pack, scene)
    assert any("reason obbligatoria" in p for p in report.problems)


def test_snapshot_includes_thread_closure_condition():
    pack = load_pack(PACK)
    state = pack.new_world()
    state.open_thread(
        Thread(
            id="t1",
            type="question",
            participants=["player", "maera"],
            summary="Chi e il corriere ferito?",
            opened_turn=0,
            close_condition="Maera rivela l'identita del corriere.",
        )
    )
    snapshot = build_snapshot(state, pack, "Chiedo del corriere.")
    assert snapshot["active_threads"] == [
        {
            "id": "t1",
            "type": "question",
            "summary": "Chi e il corriere ferito?",
            "participants": ["player", "maera"],
            "opened_turn": 0,
            "close_condition": "Maera rivela l'identita del corriere.",
        }
    ]
