"""Validazione e commit: il confine in cui lo stato cambia davvero."""

from pathlib import Path

import pytest

from epos.commit import apply_scene
from epos.contract import CheckProposal, FinalScene
from epos.models import WorldState
from epos.validators import (
    MAX_RELATIONSHIP_DELTA,
    validate_check_proposal,
    validate_scene,
)
from epos.worldpack import WorldPack, load_pack

PACK_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


@pytest.fixture
def pack() -> WorldPack:
    return load_pack(PACK_DIR)


@pytest.fixture
def state(pack) -> WorldState:
    return pack.new_world("test-session")


def _scene(**overrides):
    data = {
        "narration": "Scena.",
        "visual": {
            "summary": "momento",
            "focus_character": "maera",
            "visible_characters": ["maera"],
            "shared_action": False,
            "visual_en": "a quiet moment",
            "tags_en": [],
        },
    }
    data.update(overrides)
    return FinalScene.from_dict(data)


class TestCheckProposalValidation:
    def _proposal(self, **overrides):
        data = {
            "action_kind": "social",
            "skill": "social",
            "difficulty": 3,
            "target_ids": ["maera"],
            "opposition": "npc_resistance",
            "reason": "x",
            "stakes": {
                "full_success": "a",
                "partial_success": "b",
                "failure": "c",
                "critical_failure": "d",
            },
        }
        data.update(overrides)
        return CheckProposal.from_dict(data)

    def test_valid_proposal(self, state, pack):
        assert validate_check_proposal(state, pack, self._proposal()).ok

    def test_absent_target_rejected(self, state, pack):
        report = validate_check_proposal(
            state, pack, self._proposal(target_ids=["corren"])
        )
        assert not report.ok
        assert any("non presente" in p for p in report.problems)

    def test_unknown_target_rejected(self, state, pack):
        report = validate_check_proposal(
            state, pack, self._proposal(target_ids=["ghost"])
        )
        assert not report.ok

    def test_npc_resistance_without_npc_rejected(self, state, pack):
        report = validate_check_proposal(
            state, pack, self._proposal(target_ids=[], opposition="npc_resistance")
        )
        assert not report.ok


class TestSceneValidation:
    def test_valid_scene(self, state, pack):
        assert validate_scene(state, pack, _scene()).ok

    def test_visual_required(self, state, pack):
        report = validate_scene(state, pack, _scene(visual=None))
        assert any("visual obbligatorio" in p for p in report.problems)

    def test_absent_character_not_visible(self, state, pack):
        scene = _scene(
            visual={
                "summary": "m",
                "focus_character": "corren",
                "visible_characters": ["corren"],
                "shared_action": False,
                "visual_en": "a man in the stables",
                "tags_en": [],
            }
        )
        report = validate_scene(state, pack, scene)
        assert any("assente" in p for p in report.problems)

    def test_relationship_delta_capped(self, state, pack):
        scene = _scene(
            mutations=[
                {
                    "type": "relationship_delta",
                    "target": "maera",
                    "payload": {"trust": MAX_RELATIONSHIP_DELTA + 10},
                }
            ]
        )
        report = validate_scene(state, pack, scene)
        assert any("oltre il limite" in p for p in report.problems)

    def test_memory_witness_must_be_present(self, state, pack):
        scene = _scene(
            memory_events=[
                {"summary": "ha sentito tutto", "witnesses": ["corren"]}
            ]
        )
        report = validate_scene(state, pack, scene)
        assert any("testimone assente" in p for p in report.problems)

    def test_location_change_to_unknown_rejected(self, state, pack):
        scene = _scene(
            mutations=[
                {
                    "type": "location_change",
                    "target": "player",
                    "payload": {"location_id": "moon"},
                }
            ]
        )
        report = validate_scene(state, pack, scene)
        assert any("sconosciuta" in p for p in report.problems)

    def test_outfit_remove_requires_worn(self, state, pack):
        scene = _scene(
            mutations=[
                {
                    "type": "outfit_remove",
                    "target": "player",
                    "payload": {"item": "armatura inesistente"},
                }
            ]
        )
        report = validate_scene(state, pack, scene)
        assert any("non indossato" in p for p in report.problems)


class TestCommit:
    def test_relationship_delta_applied(self, state, pack):
        scene = _scene(
            mutations=[
                {
                    "type": "relationship_delta",
                    "target": "maera",
                    "payload": {"trust": 5, "suspicion": -3},
                }
            ]
        )
        apply_scene(state, scene)
        rel = state.npcs["maera"].relationship_towards("player")
        assert rel.trust == 5
        assert rel.suspicion == -3

    def test_relationship_clamped(self, state, pack):
        scene = _scene(
            mutations=[
                {
                    "type": "relationship_delta",
                    "target": "maera",
                    "payload": {"trust": 15},
                }
            ]
        )
        for _ in range(10):
            apply_scene(state, scene)
        assert state.npcs["maera"].relationship_towards("player").trust == 100

    def test_knowledge_added_once(self, state, pack):
        scene = _scene(
            mutations=[
                {
                    "type": "knowledge_add",
                    "target": "maera",
                    "payload": {"fact": "il giocatore mente sulla sua origine"},
                }
            ]
        )
        apply_scene(state, scene)
        apply_scene(state, scene)
        assert state.npcs["maera"].knowledge.count(
            "il giocatore mente sulla sua origine"
        ) == 1

    def test_outfit_remove_persists(self, state, pack):
        scene = _scene(
            mutations=[
                {
                    "type": "outfit_remove",
                    "target": "player",
                    "payload": {"item": "mantello da viaggio pesante"},
                }
            ]
        )
        apply_scene(state, scene)
        assert "mantello da viaggio pesante" not in state.player.outfit.worn
        assert "mantello da viaggio pesante" in state.player.outfit.removed

    def test_location_change_recomputes_presence(self, state, pack):
        scene = _scene(
            mutations=[
                {
                    "type": "location_change",
                    "target": "player",
                    "payload": {"location_id": "stables"},
                }
            ],
            visual={
                "summary": "m",
                "focus_character": "player",
                "visible_characters": ["player"],
                "shared_action": False,
                "visual_en": "the traveller moves",
                "tags_en": [],
            },
        )
        apply_scene(state, scene)
        assert state.player.location_id == "stables"
        assert state.npcs["maera"].present is False
        assert state.npcs["corren"].present is True

    def test_memory_recorded_only_to_witnesses(self, state, pack):
        scene = _scene(
            memory_events=[
                {
                    "summary": "il giocatore ha mostrato la mappa",
                    "witnesses": ["maera"],
                    "level": "relational",
                    "emotional_impact": 1,
                }
            ]
        )
        apply_scene(state, scene)
        assert len(state.npcs["maera"].memories) == 1
        assert len(state.npcs["corren"].memories) == 0
        assert state.npcs["maera"].memories[0].level == "relational"

    def test_thread_open_and_close(self, state, pack):
        scene = _scene(
            mutations=[
                {
                    "type": "thread_open",
                    "target": "world",
                    "payload": {
                        "thread_id": "t1",
                        "type": "question",
                        "participants": ["player", "maera"],
                        "summary": "Chi è il corriere ferito?",
                    },
                }
            ]
        )
        apply_scene(state, scene)
        assert state.active_threads[0].status == "open"
        closing = _scene(
            mutations=[
                {"type": "thread_close", "target": "world", "payload": {"thread_id": "t1", "reason": "Maera ha rivelato l'identita del corriere."}}
            ]
        )
        apply_scene(state, closing)
        assert state.active_threads[0].status == "closed"

    def test_resource_delta(self, state, pack):
        scene = _scene(
            mutations=[
                {"type": "resource_delta", "target": "player", "payload": {"strain": 2}}
            ]
        )
        apply_scene(state, scene)
        assert state.player.resources["strain"] == 2

    def test_last_scene_updated(self, state, pack):
        apply_scene(state, _scene(narration="Nuova scena."))
        assert state.last_scene == "Nuova scena."
