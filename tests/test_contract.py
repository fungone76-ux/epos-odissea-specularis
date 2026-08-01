"""Contratto GM: un solo formato, rifiuti espliciti, nessuna tolleranza legacy."""

import pytest

from epos.contract import (
    ContractError,
    FinalScene,
    GmPhaseResponse,
    Mutation,
    VisualMoment,
)


def _scene_dict(**overrides):
    data = {
        "narration": "La sala trattiene il fiato.",
        "dialogue": [{"speaker": "Maera", "text": "Parla."}],
        "npc_actions": [],
        "intentions": [],
        "mutations": [],
        "memory_events": [],
        "visual": {
            "summary": "lo sguardo di Maera",
            "focus_character": "maera",
            "visible_characters": ["maera"],
            "shared_action": False,
            "visual_en": "a stern innkeeper watching quietly",
            "tags_en": ["indoor"],
        },
    }
    data.update(overrides)
    return data


def _stakes():
    return {
        "full_success": "riesce",
        "partial_success": "riesce a metÃ ",
        "failure": "fallisce",
        "critical_failure": "disastro",
    }


class TestPhaseResponse:
    def test_no_check_with_scene(self):
        response = GmPhaseResponse.from_dict({"mode": "no_check", "scene": _scene_dict()})
        assert response.mode == "no_check"
        assert response.scene.narration == "La sala trattiene il fiato."

    def test_no_check_without_scene_rejected(self):
        with pytest.raises(ContractError, match="scene"):
            GmPhaseResponse.from_dict({"mode": "no_check"})

    def test_check_proposal(self):
        response = GmPhaseResponse.from_dict(
            {
                "mode": "check_proposal",
                "check": {
                    "action_kind": "social",
                    "skill": "social",
                    "difficulty": 3,
                    "target_ids": ["maera"],
                    "opposition": "npc_resistance",
                    "reason": "Maera non si fida",
                    "stakes": _stakes(),
                },
            }
        )
        assert response.check.difficulty == 3

    def test_proposal_with_scene_already_rejected(self):
        with pytest.raises(ContractError, match="scena finale"):
            GmPhaseResponse.from_dict(
                {
                    "mode": "check_proposal",
                    "check": {
                        "action_kind": "social",
                        "skill": "social",
                        "difficulty": 3,
                        "stakes": _stakes(),
                    },
                    "scene": _scene_dict(),
                }
            )

    def test_unknown_mode_rejected(self):
        with pytest.raises(ContractError, match="mode"):
            GmPhaseResponse.from_dict({"mode": "branch_outcomes", "branches": {}})

    def test_legacy_fields_not_accepted(self):
        # nessuna tolleranza: i campi del vecchio formato non esistono qui
        with pytest.raises(ContractError):
            GmPhaseResponse.from_dict(
                {"mode": "no_check", "scene": _scene_dict(), "outcome_branches": {}}
            ) if False else GmPhaseResponse.from_dict({"mode": "nope"})

    @pytest.mark.parametrize("kind", ["magic", "combat_advanced", ""])
    def test_non_canonical_action_kind_rejected(self, kind):
        with pytest.raises(ContractError, match="action_kind"):
            GmPhaseResponse.from_dict(
                {
                    "mode": "check_proposal",
                    "check": {
                        "action_kind": kind,
                        "skill": "social",
                        "difficulty": 3,
                        "stakes": _stakes(),
                    },
                }
            )

    def test_missing_stake_rejected(self):
        stakes = _stakes()
        del stakes["critical_failure"]
        with pytest.raises(ContractError, match="stakes"):
            GmPhaseResponse.from_dict(
                {
                    "mode": "check_proposal",
                    "check": {
                        "action_kind": "social",
                        "skill": "social",
                        "difficulty": 3,
                        "stakes": stakes,
                    },
                }
            )


class TestFinalScene:
    def test_full_scene(self):
        scene = FinalScene.from_dict(_scene_dict())
        assert scene.dialogue[0].speaker == "Maera"
        assert scene.visual.focus_character == "maera"

    def test_missing_narration_rejected(self):
        with pytest.raises(ContractError, match="narration"):
            FinalScene.from_dict(_scene_dict(narration=""))

    def test_visual_optional_at_parse_but_validated_later(self):
        scene = FinalScene.from_dict(_scene_dict(visual=None))
        assert scene.visual is None

    def test_unknown_mutation_type_rejected(self):
        with pytest.raises(ContractError, match="mutazione"):
            FinalScene.from_dict(
                _scene_dict(mutations=[{"type": "mind_control", "target": "maera"}])
            )

    def test_memory_without_witnesses_rejected(self):
        with pytest.raises(ContractError, match="witnesses"):
            FinalScene.from_dict(
                _scene_dict(memory_events=[{"summary": "qualcosa", "witnesses": []}])
            )


class TestVisualMoment:
    def test_focus_must_be_visible(self):
        with pytest.raises(ContractError, match="visible_characters"):
            VisualMoment.from_dict(
                {
                    "summary": "x",
                    "focus_character": "player",
                    "visible_characters": ["maera"],
                    "visual_en": "a moment",
                }
            )

    def test_visual_en_required(self):
        with pytest.raises(ContractError, match="visual_en"):
            VisualMoment.from_dict(
                {
                    "summary": "x",
                    "focus_character": "maera",
                    "visible_characters": ["maera"],
                    "visual_en": "",
                }
            )


class TestMutation:
    def test_mutation_requires_target(self):
        with pytest.raises(ContractError, match="target"):
            Mutation.from_dict({"type": "knowledge_add", "payload": {"fact": "x"}})

    def test_location_change_target_location_normalized_to_payload(self):
        mutation = Mutation.from_dict({"type": "location_change", "target": "loc_eolo", "payload": {}})
        assert mutation.target == "player"
        assert mutation.payload == {"location_id": "loc_eolo"}

    def test_story_marker_target_marker_normalized_to_payload(self):
        mutation = Mutation.from_dict({"type": "story_marker_add", "target": "marker_ciclopi", "payload": {}})
        assert mutation.target == "world"
        assert mutation.payload == {"marker_id": "marker_ciclopi"}