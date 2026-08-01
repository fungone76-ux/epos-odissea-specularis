"""Iniziativa autonoma, dialoghi NPC-NPC, disclosure, story spine e pressioni."""

import random
from pathlib import Path

import pytest

from epos.contract import ContractError, DisclosureEvent, InitiativeEvent
from epos.disclosure import apply_disclosure, validate_disclosure
from epos.gm import DemoGameMaster
from epos.initiative import apply_initiatives, validate_initiative
from epos.spine import (
    apply_pressure_advance,
    pressure_context,
    spine_context,
    validate_pressure_advance,
    validate_story_marker,
)
from epos.state_store import StateStore
from epos.turn_service import TurnService
from epos.worldpack import load_pack

PACK_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


@pytest.fixture
def pack():
    return load_pack(PACK_DIR)


@pytest.fixture
def state(pack):
    return pack.new_world("npc-features")


def _initiative(**overrides):
    data = {"source": "maera", "type": "interrupt", "summary": "Maera si intromette"}
    data.update(overrides)
    return InitiativeEvent.from_dict(data)


class TestInitiativeValidation:
    def test_valid_npc_initiative(self, state):
        assert validate_initiative(state, _initiative()) == []

    def test_absent_npc_rejected(self, state):
        problems = validate_initiative(state, _initiative(source="corren"))
        assert any("assente" in p for p in problems)

    def test_unknown_source_rejected(self, state):
        problems = validate_initiative(state, _initiative(source="fantasma"))
        assert any("inesistente" in p for p in problems)

    def test_world_source_environmental(self, state):
        event = _initiative(
            source="weather", type="environmental_event", summary="La neve inizia a cadere"
        )
        assert validate_initiative(state, event) == []

    def test_world_source_rejects_npc_types(self, state):
        event = _initiative(source="crowd", type="interrupt", summary="La folla freme")
        problems = validate_initiative(state, event)
        assert any("non ambientale" in p for p in problems)

    def test_pure_reaction_rejected(self, state):
        event = _initiative(type="other", summary="Maera lancia uno sguardo freddo")
        problems = validate_initiative(state, event)
        assert any("reazione pura" in p for p in problems)

    def test_absent_target_rejected(self, state):
        problems = validate_initiative(state, _initiative(target="corren"))
        assert any("target" in p for p in problems)

    def test_alias_normalization(self):
        assert _initiative(type="warning").type == "warn"

    def test_unknown_type_rejected(self):
        with pytest.raises(ContractError, match="iniziativa"):
            _initiative(type="mind_read")


class TestInitiativeRhythm:
    def test_autonomous_resets_reactive_counter(self, state):
        apply_initiatives(state, [])
        apply_initiatives(state, [])
        assert state.initiative.consecutive_reactive_turns == 2
        apply_initiatives(state, [_initiative()])
        assert state.initiative.consecutive_reactive_turns == 0
        assert state.initiative.last_autonomous_turn == state.turn

    def test_recent_bounded(self, state):
        for _ in range(15):
            apply_initiatives(state, [_initiative()])
        assert len(state.initiative.recent) == 10


class TestNpcNpcDialogue:
    def test_npc_to_npc_line_valid(self, pack, state, tmp_path):
        """Un GM che mette in scena un dialogo Maera→Corren: prima portiamo
        Corren in scena, poi il turno con dialogo NPC-NPC viene accettato."""

        state.npcs["corren"].present = True

        class NpcDialogueGM(DemoGameMaster):
            def propose(self, state, pack, player_text):
                from epos.contract import GmPhaseResponse

                return GmPhaseResponse.from_dict(
                    {
                        "mode": "no_check",
                        "scene": {
                            "narration": "Maera e Corren si scambiano uno sguardo.",
                            "dialogue": [
                                {
                                    "speaker": "Maera Dolk",
                                    "to": "corren",
                                    "text": "Le stalle. Ora.",
                                },
                                {
                                    "speaker": "Corren Vail",
                                    "to": "maera",
                                    "text": "Non è colpa mia se le pattuglie...",
                                },
                            ],
                            "visual": {
                                "summary": "le due figure si fronteggiano",
                                "focus_character": "maera",
                                "visible_characters": ["maera", "corren"],
                                "shared_action": False,
                                "visual_en": "innkeeper and stablehand exchanging tense words",
                                "tags_en": ["tension"],
                            },
                        },
                    }
                )

        service = TurnService(
            gm=NpcDialogueGM(), pack=pack, store=StateStore(tmp_path / "saves"),
            rng=random.Random(1),
        )
        result = service.play(state, "Resto in disparte ad ascoltare.")
        assert len(result.dialogue) == 2
        assert result.dialogue[0]["speaker"] == "Maera Dolk"

    def test_dialogue_to_absent_rejected(self, pack, state):
        from epos.contract import FinalScene
        from epos.validators import validate_scene

        scene = FinalScene.from_dict(
            {
                "narration": "x",
                "dialogue": [{"speaker": "Maera Dolk", "to": "corren", "text": "..."}],
                "visual": {
                    "summary": "m",
                    "focus_character": "maera",
                    "visible_characters": ["maera"],
                    "shared_action": False,
                    "visual_en": "scene",
                    "tags_en": [],
                },
            }
        )
        report = validate_scene(state, pack, scene)
        assert any("assente" in p for p in report.problems)


class TestDisclosure:
    def _event(self, **overrides):
        data = {
            "npc_id": "maera",
            "fact": "Nasconde nella dispensa un corriere ferito arrivato tre giorni fa.",
            "action": "revealed",
        }
        data.update(overrides)
        return DisclosureEvent.from_dict(data)

    def test_reveal_owned_secret_valid(self, pack, state):
        assert validate_disclosure(state, pack, self._event()) == []

    def test_unknown_fact_rejected(self, pack, state):
        problems = validate_disclosure(
            state, pack, self._event(fact="Un fatto che Maera non conosce affatto.")
        )
        assert any("non possiede" in p for p in problems)

    def test_absent_npc_rejected(self, pack, state):
        problems = validate_disclosure(
            state, pack, self._event(npc_id="corren", fact="Il sentiero sud è ancora praticabile.")
        )
        assert any("assente" in p for p in problems)

    def test_truthful_reveal_transfers_knowledge(self, state):
        event = self._event()
        apply_disclosure(state, event)
        assert event.fact in state.player.knowledge
        assert event.fact in state.npcs["maera"].disclosed_facts

    def test_withheld_transfers_nothing(self, state):
        event = self._event(action="withheld")
        apply_disclosure(state, event)
        assert state.player.knowledge == []
        assert state.npcs["maera"].disclosed_facts == []

    def test_reveal_idempotent(self, state):
        event = self._event()
        apply_disclosure(state, event)
        apply_disclosure(state, event)
        assert state.player.knowledge.count(event.fact) == 1


class TestStorySpine:
    def test_canonical_marker_accepted(self, pack, state):
        assert validate_story_marker(pack, state, "met_maera") == []

    def test_unknown_marker_rejected(self, pack, state):
        problems = validate_story_marker(pack, state, "kill_maera")
        assert any("non canonico" in p for p in problems)

    def test_duplicate_marker_rejected(self, pack, state):
        from epos.spine import apply_story_marker

        apply_story_marker(state, "met_maera")
        problems = validate_story_marker(pack, state, "met_maera")
        assert any("già confermato" in p for p in problems)

    def test_spine_context_progress(self, pack, state):
        context = spine_context(pack, state)
        assert len(context["remaining"]) == 3
        assert context["slice_concluded"] is False

    def test_concluding_marker_marks_slice(self, pack, state):
        from epos.spine import apply_story_marker

        apply_story_marker(state, "courier_found")
        assert spine_context(pack, state)["slice_concluded"] is True


class TestPressure:
    def _advance(self, **overrides):
        data = {
            "source": "environment",
            "type": "pressure_advance",
            "summary": "Voci di pattuglie sulla strada",
            "reason": "pressure:patrols",
        }
        data.update(overrides)
        return InitiativeEvent.from_dict(data)

    def test_advance_valid(self, pack, state):
        assert validate_pressure_advance(pack, state, self._advance()) == []

    def test_unknown_pressure_rejected(self, pack, state):
        problems = validate_pressure_advance(
            pack, state, self._advance(reason="pressure:dragons")
        )
        assert any("senza pressione canonica" in p for p in problems)

    def test_advance_too_soon_rejected(self, pack, state):
        apply_pressure_advance(pack, state, self._advance())
        problems = validate_pressure_advance(pack, state, self._advance())
        assert any("troppo presto" in p for p in problems)

    def test_advance_after_interval_ok(self, pack, state):
        apply_pressure_advance(pack, state, self._advance())
        state.turn += 2
        assert validate_pressure_advance(pack, state, self._advance()) == []
        assert state.pressures["patrols"].level == 1

    def test_pressure_context_shows_level(self, pack, state):
        apply_pressure_advance(pack, state, self._advance())
        context = pressure_context(pack, state)
        assert context[0]["level"] == 1
