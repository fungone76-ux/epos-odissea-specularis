"""Fase 1: provenance canonica di memoria e conoscenza."""

from pathlib import Path

import pytest

from epos.commit import apply_scene
from epos.contract import FinalScene, MemoryProposal, Mutation, VisualMoment
from epos.disclosure import apply_disclosure
from epos.contract import DisclosureEvent
from epos.models import KnowledgeEntry, PlayerState
from epos.validators import validate_scene
from epos.worldpack import load_pack

PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


def _visual():
    return VisualMoment(
        summary="Maera ascolta",
        focus_character="maera",
        visible_characters=["maera"],
        shared_action=False,
        visual_en="an innkeeper listening",
    )


def _scene(**kwargs):
    data = {"narration": "La scena cambia.", "visual": _visual()}
    data.update(kwargs)
    return FinalScene(**data)


def test_knowledge_entry_roundtrip():
    entry = KnowledgeEntry(
        fact="Polifemo teme il nome Nessuno.",
        source="deduced",
        turn=3,
        credibility=0.8,
        origin="player_input",
    )
    assert KnowledgeEntry.from_dict(entry.to_dict()) == entry


def test_player_state_roundtrip_preserves_knowledge_log():
    player = PlayerState(name="Ulisse", location_id="loc_ciclopi")
    player.knowledge.append("La caverna ha un palo d'olivo.")
    player.knowledge_log.append(
        KnowledgeEntry(
            fact="La caverna ha un palo d'olivo.",
            source="observed",
            turn=0,
            credibility=1.0,
            origin="scene",
        )
    )
    restored = PlayerState.from_dict(player.to_dict())
    assert restored.knowledge == player.knowledge
    assert restored.knowledge_log == player.knowledge_log


def test_memory_proposal_requires_valid_source_and_credibility():
    assert MemoryProposal.from_dict(
        {
            "summary": "Maera ha sentito la promessa.",
            "witnesses": ["maera"],
            "source": "observed",
            "credibility": 1.0,
        }
    ).source == "observed"
    with pytest.raises(Exception, match="source"):
        MemoryProposal.from_dict(
            {"summary": "x", "witnesses": ["maera"], "source": "dreamed"}
        )
    with pytest.raises(Exception, match="credibility"):
        MemoryProposal.from_dict(
            {"summary": "x", "witnesses": ["maera"], "credibility": 1.5}
        )


def test_knowledge_add_creates_provenance_entry():
    pack = load_pack(PACK)
    state = pack.new_world()
    scene = _scene(
        mutations=[
            Mutation(
                type="knowledge_add",
                target="maera",
                payload={
                    "fact": "Il viandante conosce il sentiero nord.",
                    "source": "observed",
                    "credibility": 0.9,
                    "origin": "turn_action",
                },
            )
        ]
    )
    report = validate_scene(state, pack, scene)
    assert report.ok
    apply_scene(state, scene)
    entry = state.npcs["maera"].knowledge_log[0]
    assert entry.fact == "Il viandante conosce il sentiero nord."
    assert entry.source == "observed"
    assert entry.turn == 0
    assert entry.credibility == 0.9


def test_invalid_knowledge_provenance_rejected():
    pack = load_pack(PACK)
    state = pack.new_world()
    scene = _scene(
        mutations=[
            Mutation(
                type="knowledge_add",
                target="maera",
                payload={"fact": "x", "source": "omniscient", "credibility": 2},
            )
        ]
    )
    report = validate_scene(state, pack, scene)
    assert any("source non valida" in p for p in report.problems)
    assert any("credibility fuori range" in p for p in report.problems)


def test_truthful_disclosure_transfers_knowledge_with_source():
    pack = load_pack(PACK)
    state = pack.new_world()
    fact = "Il sentiero sud ? ancora praticabile."
    event = DisclosureEvent(npc_id="maera", fact=fact, action="partial_truth")
    apply_disclosure(state, event)
    assert fact in state.player.knowledge
    entry = state.player.knowledge_log[0]
    assert entry.fact == fact
    assert entry.source == "told"
    assert entry.origin == "maera"
    assert entry.credibility == 0.75


def test_snapshot_includes_compact_knowledge_provenance():
    from epos.models import add_knowledge
    from epos.prompt import build_snapshot

    pack = load_pack(PACK)
    state = pack.new_world()
    add_knowledge(
        state.npcs["maera"],
        "Il viandante conosce il sentiero nord.",
        source="observed",
        turn=state.turn,
        origin="test",
    )
    add_knowledge(
        state.player,
        "Il sentiero sud ? ancora praticabile.",
        source="told",
        turn=state.turn,
        origin="maera",
    )

    snapshot = build_snapshot(state, pack, "Osservo la sala.")
    npc = snapshot["present_npcs"][0]
    assert npc["knowledge_provenance"][0]["source"] == "observed"
    assert snapshot["player_knowledge_provenance"][0]["origin"] == "maera"
