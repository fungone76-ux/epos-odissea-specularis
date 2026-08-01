import json
import random
from pathlib import Path

import pytest

from epos.contract import CheckProposal, FinalScene, GmPhaseResponse
from epos.entity_ids import (
    PLAYER_ALIASES,
    normalize_check_proposal_entity_ids,
    normalize_entity_id,
    normalize_scene_entity_ids,
)
from epos.outfit import format_current_outfit_for_ui, normalize_player_outfit_scene
from epos.renderers import RenderRecord
from epos.state_store import StateStore
from epos.turn_service import PlayerDecision, TurnService
from epos.validators import validate_check_proposal, validate_scene
from epos.visual import build_visual_contract
from epos.worldpack import load_pack


PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"
CHITON = "very short crimson wool chiton with deep low-cut neckline"


def _pack():
    return load_pack(PACK)


@pytest.fixture
def pack():
    return _pack()


@pytest.fixture
def state(pack):
    return pack.new_world("entity-alias")


def _visual(**overrides):
    data = {
        "summary": "frame",
        "focus_character": "player",
        "visible_characters": ["player"],
        "shared_action": False,
        "moment_type": "action",
        "speaker_character": "",
        "actor_character": "player",
        "reactor_character": "",
        "intimate_shared_moment": False,
        "multi_character_reason": "",
        "multi_character_participants": [],
        "visual_en": "Ulisse moves through the cave.",
        "tags_en": ["full body"],
    }
    data.update(overrides)
    return data


def _scene(**overrides):
    data = {
        "narration": "Ulisse entra nella caverna.",
        "dialogue": [{"speaker": "Ulisse", "to": "ulisse", "text": "Ulisse resiste."}],
        "npc_actions": [],
        "intentions": [],
        "initiatives": [],
        "disclosure_events": [],
        "mutations": [],
        "memory_events": [],
        "visual": _visual(),
    }
    data.update(overrides)
    return FinalScene.from_dict(data)


def _proposal(target_ids):
    return CheckProposal.from_dict(
        {
            "action_kind": "physical",
            "skill": "bia",
            "difficulty": 2,
            "target_ids": target_ids,
            "opposition": "self",
            "reason": "Ulisse tenta un gesto difficile.",
            "stakes": {
                "full_success": "ok",
                "partial_success": "partial",
                "failure": "fail",
                "critical_failure": "bad",
            },
        }
    )


@pytest.mark.parametrize(
    ("field", "alias"),
    [
        ("focus_character", "ulisse"),
        ("focus_character", "Ulisse"),
        ("actor_character", "odysseus"),
        ("reactor_character", "odisseo"),
        ("speaker_character", "Ulisse"),
    ],
)
def test_visual_single_id_aliases_normalize_to_player(state, field, alias):
    scene = _scene(
        visual=_visual(
            **{
                "focus_character": alias,
                "visible_characters": [alias],
                field: alias,
            }
        )
    )

    result = normalize_scene_entity_ids(state, scene, phase="test")

    assert getattr(result.value.visual, field) == "player"
    assert result.value.visual.visible_characters == ["player"]


def test_visual_visible_characters_alias_normalizes_to_player(state):
    scene = _scene(visual=_visual(focus_character="ulisse", visible_characters=["ulisse"]))

    result = normalize_scene_entity_ids(state, scene, phase="test")

    assert result.value.visual.visible_characters == ["player"]


def test_visual_multi_character_participants_alias_normalizes_to_player(state):
    scene = _scene(
        visual=_visual(
            focus_character="ulisse",
            visible_characters=["ulisse", "polifemo"],
            shared_action=True,
            moment_type="intimate",
            intimate_shared_moment=True,
            multi_character_participants=[" ulisse ", "polifemo"],
        )
    )

    result = normalize_scene_entity_ids(state, scene, phase="test")

    assert result.value.visual.multi_character_participants == ["player", "polifemo"]


def test_mutation_target_alias_normalizes_to_player(state):
    scene = _scene(
        mutations=[
            {
                "type": "condition_add",
                "target": "ulisse",
                "payload": {"condition": "tested"},
                "reason": "Ulisse resta nella prosa.",
            }
        ]
    )

    result = normalize_scene_entity_ids(state, scene, phase="test")

    assert result.value.mutations[0].target == "player"
    assert result.value.mutations[0].reason == "Ulisse resta nella prosa."


def test_target_ids_alias_normalizes_to_player(state, pack):
    result = normalize_check_proposal_entity_ids(state, _proposal(["ulisse"]), phase="test")

    assert result.value.target_ids == ["player"]
    assert validate_check_proposal(state, pack, result.value).ok


def test_memory_witness_dialogue_to_and_initiative_target_aliases_normalize(state):
    scene = _scene(
        memory_events=[
            {
                "summary": "Ulisse vede la soglia.",
                "witnesses": ["Ulisse"],
                "level": "immediate",
                "emotional_impact": 0,
                "public": True,
            }
        ],
        initiatives=[
            {
                "source": "environment",
                "type": "other",
                "summary": "La soglia cede.",
                "target": "ulisse",
            }
        ],
    )

    result = normalize_scene_entity_ids(state, scene, phase="test")

    assert result.value.memory_events[0].witnesses == ["player"]
    assert result.value.dialogue[0].to == "player"
    assert result.value.initiatives[0].target == "player"


def test_free_text_fields_are_not_modified(state):
    scene = _scene(
        narration="Ulisse entra nella caverna.",
        dialogue=[{"speaker": "Ulisse", "to": "ulisse", "text": "Ulisse parla piano."}],
        mutations=[
            {
                "type": "condition_add",
                "target": "ulisse",
                "payload": {"condition": "steady"},
                "reason": "Ulisse sceglie il rischio.",
            }
        ],
        memory_events=[
            {
                "summary": "Ulisse ha parlato.",
                "witnesses": ["Ulisse"],
                "level": "immediate",
                "emotional_impact": 0,
                "public": True,
            }
        ],
    )

    result = normalize_scene_entity_ids(state, scene, phase="test")

    assert result.value.narration == "Ulisse entra nella caverna."
    assert result.value.dialogue[0].speaker == "Ulisse"
    assert result.value.dialogue[0].text == "Ulisse parla piano."
    assert result.value.mutations[0].reason == "Ulisse sceglie il rischio."
    assert result.value.memory_events[0].summary == "Ulisse ha parlato."


def test_npcs_are_not_normalized_to_player(state):
    scene = _scene(
        visual=_visual(
            focus_character="polifemo",
            visible_characters=["polifemo", "atena", "antinoo"],
            shared_action=True,
            moment_type="intimate",
            intimate_shared_moment=True,
            multi_character_participants=["polifemo", "atena", "antinoo"],
        )
    )

    result = normalize_scene_entity_ids(state, scene, phase="test")

    assert result.value.visual.focus_character == "polifemo"
    assert result.value.visual.visible_characters == ["polifemo", "atena", "antinoo"]


def test_alias_with_spaces_and_case_normalizes(state):
    assert normalize_entity_id("  OdYsSeUs  ", state, "visual.focus_character") == "player"


def test_unknown_alias_stays_unknown_and_validator_rejects(state, pack):
    scene = _scene(visual=_visual(focus_character="nessuno", visible_characters=["nessuno"]))

    result = normalize_scene_entity_ids(state, scene, phase="test")
    report = validate_scene(state, pack, result.value)

    assert result.value.visual.visible_characters == ["nessuno"]
    assert not report.ok
    assert report.errors[0].code == "visible_character_not_present"


def test_validator_accepts_visual_after_alias_normalization(state, pack):
    scene = _scene(visual=_visual(focus_character="ulisse", visible_characters=["ulisse"]))

    raw_report = validate_scene(state, pack, scene)
    normalized = normalize_scene_entity_ids(state, scene, phase="test").value
    normalized_report = validate_scene(state, pack, normalized)

    assert not raw_report.ok
    assert normalized_report.ok


def test_outfit_target_alias_works_before_validation(state, pack):
    scene = _scene(
        mutations=[
            {
                "type": "outfit_remove",
                "target": "ulisse",
                "payload": {"item": CHITON},
                "reason": "outfit",
            }
        ]
    )

    normalized = normalize_scene_entity_ids(state, scene, phase="test").value
    outfit_normalized = normalize_player_outfit_scene(state, "mi tolgo il chitone", normalized).scene

    assert outfit_normalized.mutations[0].target == "player"
    assert validate_scene(state, pack, outfit_normalized).ok


def test_player_display_name_in_dialogue_is_valid_and_ui_keeps_ulisse(state, pack):
    scene = _scene(dialogue=[{"speaker": "Ulisse", "text": "Parlo come Ulisse."}])
    result = normalize_scene_entity_ids(state, scene, phase="test")

    assert validate_scene(state, pack, result.value).ok
    assert result.value.dialogue[0].speaker == "Ulisse"
    assert format_current_outfit_for_ui(state.player).value == "Indossa"


def test_player_alias_registry_is_conservative():
    assert {"player", "ulisse", "odysseus", "odisseo"} <= PLAYER_ALIASES
    assert "polifemo" not in PLAYER_ALIASES
    assert "atena" not in PLAYER_ALIASES


class AliasSceneGM:
    def propose(self, state, pack, player_text):
        return GmPhaseResponse.from_dict(
            {
                "mode": "no_check",
                "scene": {
                    "narration": "Ulisse si toglie il chitone.",
                    "dialogue": [
                        {"speaker": "Ulisse", "to": "ulisse", "text": "Ulisse resta ferma."}
                    ],
                    "npc_actions": [],
                    "intentions": [],
                    "initiatives": [],
                    "disclosure_events": [],
                    "mutations": [
                        {
                            "type": "outfit_remove",
                            "target": "ulisse",
                            "payload": {"item": CHITON},
                            "reason": "outfit_remove target alias",
                        }
                    ],
                    "memory_events": [],
                    "visual": _visual(
                        focus_character="ulisse",
                        visible_characters=["ulisse"],
                        actor_character="ulisse",
                    ),
                },
            }
        )


class CaptureRenderer:
    def __init__(self):
        self.packages = []

    def render(self, prompt_package, out_dir):
        self.packages.append(dict(prompt_package))
        return RenderRecord(status="complete", image_path=str(out_dir / "image.png"), backend="capture")


def test_turn_service_normalizes_aliases_before_commit_visual_and_renderer(tmp_path, pack):
    renderer = CaptureRenderer()
    service = TurnService(
        gm=AliasSceneGM(),
        pack=pack,
        store=StateStore(tmp_path / "saves"),
        rng=random.Random(4),
        decision_provider=lambda *a, **k: PlayerDecision(choice="safe"),
        renderer=renderer,
    )
    state = service.new_session("entity-turn")

    result = service.play(state, 'mi tolgo il chitone e dico "Ulisse resta ferma."')

    assert result.narration == "Ulisse si toglie il chitone."
    assert result.dialogue[0]["speaker"] == "Ulisse"
    assert result.dialogue[0]["text"] == "Ulisse resta ferma."
    assert result.dialogue[0]["to"] == "player"
    assert result.scene_mutations[0]["target"] == "player"
    assert result.visual_contract.focus_character == "player"
    assert result.visual_contract.visible_characters == ["player"]
    assert renderer.packages[0]["visible_characters"] == ["player"]
    assert CHITON in state.player.outfit.removed

    entity_diag = service.store.load_turn_artifact(state.session_id, 0, "entity_id_diagnostics")
    paths = {entry["field_path"] for entry in entity_diag["normalizations"]}
    assert "mutations[0].target" in paths
    assert "visual.focus_character" in paths
    assert any(entry["alias_rule"] == "player_alias" for entry in entity_diag["normalizations"])


def test_visual_contract_keeps_a1111_and_comfy_prompt_shape_after_normalization(state, pack):
    scene = _scene(visual=_visual(focus_character="Ulisse", visible_characters=["Ulisse"]))
    normalized = normalize_scene_entity_ids(state, scene, phase="test").value

    contract = build_visual_contract(state, pack, normalized.visual, 0)

    assert contract.prompt_package["focus_character"] == "player"
    assert contract.prompt_package["visible_characters"] == ["player"]
    assert "positive" in contract.prompt_package
    assert "negative" in contract.prompt_package


def test_entity_diagnostics_are_json_serializable(state):
    scene = _scene(
        visual=_visual(
            focus_character="ulisse",
            visible_characters=["ulisse"],
            actor_character="  Ulisse  ",
        )
    )
    result = normalize_scene_entity_ids(state, scene, phase="test", attempt=2, source_payload="raw")

    payload = result.to_dict()
    encoded = json.dumps(payload)

    assert "visual.focus_character" in encoded
    assert payload["normalizations"][0]["attempt"] == 2
    assert payload["normalizations"][0]["source_payload"] == "raw"
