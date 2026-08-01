import json
import random
from pathlib import Path

import pytest

from epos.contract import FinalScene, GmPhaseResponse, VisualMoment
from epos.gm import GameMasterError, SceneValidationError
from epos.models import outfit_state
from epos.outfit import format_current_outfit_for_ui, normalize_player_outfit_scene
from epos.renderers import RenderRecord
from epos.rules import Roll
from epos.state_store import StateStore
from epos.turn_service import PlayerDecision, TurnService
from epos.validators import validate_scene
from epos.visual import build_visual_contract
from epos.worldpack import load_pack


PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"
CHITON = "very short crimson wool chiton with deep low-cut neckline"
ARMOR = "worn revealing leather armor with bronze studs"


def _pack():
    return load_pack(PACK)


def _visual(text="Ulisse moves silently through the cave."):
    return {
        "summary": "frame",
        "focus_character": "player",
        "visible_characters": ["player"],
        "shared_action": False,
        "moment_type": "action",
        "actor_character": "player",
        "speaker_character": "",
        "reactor_character": "",
        "intimate_shared_moment": False,
        "multi_character_reason": "",
        "multi_character_participants": [],
        "visual_en": text,
        "tags_en": ["full body", "cave"],
    }


def _scene(mutations=None, visual_text="Ulisse moves silently through the cave."):
    return {
        "narration": "Scena valida.",
        "dialogue": [],
        "npc_actions": [],
        "intentions": [],
        "initiatives": [],
        "disclosure_events": [],
        "mutations": list(mutations or []),
        "memory_events": [],
        "visual": _visual(visual_text),
    }


def _remove(item):
    return {
        "type": "outfit_remove",
        "target": "player",
        "payload": {"item": item},
        "reason": "outfit state change",
    }


def _wear(item):
    return {
        "type": "outfit_wear",
        "target": "player",
        "payload": {"item": item},
        "reason": "explicitly worn again",
    }


class SequenceGM:
    def __init__(self, scenes):
        self.scenes = list(scenes)

    def propose(self, state, pack, player_text):
        return GmPhaseResponse.from_dict({"mode": "no_check", "scene": self.scenes.pop(0)})

    def narrate(self, *args, **kwargs):
        return FinalScene.from_dict(self.scenes.pop(0))


class RetryGM:
    def __init__(self, first, second):
        self.first = FinalScene.from_dict(first)
        self.second = FinalScene.from_dict(second)
        self.calls = 0

    def propose(self, state, pack, player_text):
        return GmPhaseResponse.from_dict(
            {
                "mode": "check_proposal",
                "check": {
                    "action_kind": "stealth",
                    "skill": "dolos",
                    "difficulty": 2,
                    "target_ids": ["polifemo"],
                    "opposition": "npc_resistance",
                    "reason": "risky",
                    "stakes": {
                        "full_success": "ok",
                        "partial_success": "partial",
                        "failure": "fail",
                        "critical_failure": "bad",
                    },
                },
            }
        )

    def narrate(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise SceneValidationError("bad scene")
        return self.second


class CaptureRenderer:
    def __init__(self):
        self.packages = []

    def render(self, prompt_package, out_dir):
        self.packages.append(dict(prompt_package))
        return RenderRecord(status="complete", image_path=str(out_dir / "image.png"), backend="capture")


def _service(tmp_path, gm, renderer=None):
    pack = _pack()
    return TurnService(
        gm=gm,
        pack=pack,
        store=StateStore(tmp_path / "saves"),
        rng=random.Random(3),
        decision_provider=lambda *a, **k: PlayerDecision(choice="safe"),
        renderer=renderer,
    )


def test_nuova_partita_con_outfit_iniziale():
    state = _pack().new_world("outfit-new")
    current = outfit_state(state.player.outfit)
    assert CHITON in state.player.outfit.worn
    assert ARMOR in state.player.outfit.worn
    assert current["nudity_mode"] == "clothed"
    assert current["torso_slot"]
    assert current["lower_body_slot"]


def test_outfit_remove_torso_e_lower_body_porta_a_fully_nude(tmp_path):
    gm = SequenceGM([_scene([_remove(CHITON), _remove(ARMOR)], "Ulisse stands completely nude in the cave.")])
    service = _service(tmp_path, gm)
    state = service.new_session("outfit-remove")

    result = service.play(state, "mi spoglio completamente")

    current = outfit_state(state.player.outfit)
    assert current["nudity_mode"] == "fully_nude"
    assert current["torso_slot"] == []
    assert current["lower_body_slot"] == []
    assert CHITON in state.player.outfit.removed
    assert ARMOR in state.player.outfit.removed
    assert result.visual_contract.prompt_package["nudity_mode"] == "fully_nude"


def test_input_mi_spoglio_completamente_normalizza_mutations_vuote(tmp_path):
    gm = SequenceGM([_scene([], "Ulisse stands completely nude in the cave, no clothing.")])
    service = _service(tmp_path, gm)
    state = service.new_session("outfit-normalize-empty")

    result = service.play(state, "mi spoglio completamente")

    assert [m["type"] for m in result.scene_mutations if m["type"].startswith("outfit_")] == [
        "outfit_remove",
        "outfit_remove",
    ]
    assert CHITON in state.player.outfit.removed
    assert ARMOR in state.player.outfit.removed
    assert outfit_state(state.player.outfit)["nudity_mode"] == "fully_nude"
    diag = service.store.load_turn_artifact(state.session_id, 0, "outfit_diagnostics")
    assert diag["outfit_intent_detected"] == "remove_all_worn_clothing"
    assert len(diag["outfit_mutations_normalized"]) == 2
    assert diag["outfit_ui_value"] == "Nuda"


def test_normalizzazione_rimuove_solo_veri_capi_non_armi_o_descrittori():
    pack = _pack()
    state = pack.new_world("outfit-real-items")
    state.player.outfit.wear("bare thighs clearly visible")
    state.player.outfit.wear("exposed shoulders")
    state.player.outfit.wear("recurved bow with bronze tips")
    scene = FinalScene.from_dict(_scene([], "Ulisse stands completely nude in the cave."))

    normalized = normalize_player_outfit_scene(state, "mi spoglio completamente", scene)
    items = [m["payload"]["item"] for m in normalized.mutations_normalized]

    assert CHITON in items
    assert ARMOR in items
    assert "bare thighs clearly visible" not in items
    assert "exposed shoulders" not in items
    assert "recurved bow with bronze tips" not in items


def test_ui_mostra_nuda_e_filtra_descrittori_visuali():
    pack = _pack()
    state = pack.new_world("outfit-ui-nude")
    state.player.outfit.wear("bare thighs clearly visible")
    state.player.outfit.wear("exposed shoulders")
    state.player.outfit.remove_item(CHITON)
    state.player.outfit.remove_item(ARMOR)

    ui = format_current_outfit_for_ui(state.player)

    assert ui.value == "Nuda"
    assert ui.items == []


def test_save_e_reload_dopo_fully_nude_restano_fully_nude(tmp_path):
    gm = SequenceGM([_scene([_remove(CHITON), _remove(ARMOR)], "Ulisse stands completely nude in the cave.")])
    service = _service(tmp_path, gm)
    state = service.new_session("outfit-save")
    service.play(state, "mi spoglio completamente")

    saved = json.loads((tmp_path / "saves" / state.session_id / "state.json").read_text(encoding="utf-8"))
    loaded = service.load_session(state.session_id)

    assert saved["player"]["outfit"]["nudity_mode"] == "fully_nude"
    assert saved["player"]["outfit"]["torso_slot"] == []
    assert saved["player"]["outfit"]["lower_body_slot"] == []
    assert outfit_state(loaded.player.outfit)["nudity_mode"] == "fully_nude"
    assert loaded.player.outfit.removed == state.player.outfit.removed


def test_turno_successivo_senza_mutation_resta_fully_nude_nel_prompt(tmp_path):
    gm = SequenceGM(
        [
            _scene([_remove(CHITON), _remove(ARMOR)], "Ulisse stands completely nude in the cave."),
            _scene([], "Ulisse moves silently through the dark cave."),
        ]
    )
    service = _service(tmp_path, gm)
    state = service.new_session("outfit-next")
    service.play(state, "mi spoglio completamente")
    result = service.play(state, "avanzo")

    positive = result.visual_contract.prompt_package["positive"].lower()
    negative = result.visual_contract.prompt_package["negative"].lower()
    assert result.visual_contract.prompt_package["nudity_mode"] == "fully_nude"
    assert "completely nude" in positive
    assert "fully naked" in positive
    assert "no clothing" in positive
    assert "very short crimson wool chiton" not in positive
    assert "worn revealing leather armor" not in positive
    assert "dress" in negative
    assert "chiton" in negative
    assert "armor" in negative


def test_visual_contract_che_reintroduce_abiti_viene_bloccato():
    pack = _pack()
    state = pack.new_world("outfit-block")
    state.player.outfit.remove_item(CHITON)
    state.player.outfit.remove_item(ARMOR)
    scene = FinalScene.from_dict(_scene([], "Ulisse is wearing a crimson chiton in the cave."))

    report = validate_scene(state, pack, scene)

    assert not report.ok
    assert report.errors[0].code == "visual_outfit_state_mismatch"


def test_nudita_visuale_senza_mutation_outfit_viene_bloccata():
    pack = _pack()
    state = pack.new_world("outfit-missing-mutation")
    scene = FinalScene.from_dict(_scene([], "Ulisse stands completely nude under the sun."))

    report = validate_scene(state, pack, scene)

    assert not report.ok
    assert report.errors[0].code == "visual_outfit_state_mismatch"


def test_equip_esplicito_successivo_ripristina_outfit(tmp_path):
    gm = SequenceGM(
        [
            _scene([_remove(CHITON), _remove(ARMOR)], "Ulisse stands completely nude in the cave."),
            _scene([_wear(CHITON)], "Ulisse wears her crimson chiton again."),
        ]
    )
    service = _service(tmp_path, gm)
    state = service.new_session("outfit-wear")
    service.play(state, "mi spoglio")
    result = service.play(state, "rimetto il chitone")

    assert CHITON in state.player.outfit.worn
    assert CHITON not in state.player.outfit.removed
    assert outfit_state(state.player.outfit)["nudity_mode"] == "clothed"
    assert CHITON in result.visual_contract.prompt_package["positive"]


def test_input_indosso_chitone_normalizza_outfit_wear(tmp_path):
    gm = SequenceGM(
        [
            _scene([_remove(CHITON), _remove(ARMOR)], "Ulisse stands completely nude in the cave."),
            _scene([], "Ulisse wears her crimson chiton again."),
        ]
    )
    service = _service(tmp_path, gm)
    state = service.new_session("outfit-normalize-wear")
    service.play(state, "mi spoglio completamente")
    result = service.play(state, "indosso il chitone")

    assert any(
        m["type"] == "outfit_wear" and m["payload"]["item"] == CHITON
        for m in result.scene_mutations
    )
    assert CHITON in state.player.outfit.worn
    assert CHITON not in state.player.outfit.removed
    assert format_current_outfit_for_ui(state.player).value == "Indossa"


def test_input_mi_tolgo_il_chitone_risolve_capo_indossato(tmp_path):
    gm = SequenceGM([_scene([], "Ulisse removes the crimson chiton but keeps the armor.")])
    service = _service(tmp_path, gm)
    state = service.new_session("outfit-normalize-remove-one")

    service.play(state, "mi tolgo il chitone")

    assert CHITON in state.player.outfit.removed
    assert ARMOR in state.player.outfit.worn


def test_retry_llm_non_altera_stato_outfit(tmp_path):
    gm = RetryGM(
        _scene([], "bad"),
        _scene([], "Ulisse moves silently through the cave."),
    )
    service = _service(tmp_path, gm)
    state = service.new_session("outfit-retry")
    state.player.outfit.remove_item(CHITON)
    state.player.outfit.remove_item(ARMOR)
    before = state.player.outfit.to_dict()

    service.play(state, "avanzo")

    assert state.player.outfit.to_dict()["worn"] == before["worn"]
    assert state.player.outfit.to_dict()["removed"] == before["removed"]
    assert outfit_state(state.player.outfit)["nudity_mode"] == "fully_nude"


def test_fallback_demo_non_reintroduce_outfit_iniziale(tmp_path):
    service = _service(tmp_path, SequenceGM([_scene([], "Ulisse moves silently through the cave.")]))
    state = service.new_session("outfit-demo")
    state.player.outfit.remove_item(CHITON)
    state.player.outfit.remove_item(ARMOR)
    result = service.play(state, "osservo la caverna")

    positive = result.visual_contract.prompt_package["positive"].lower()
    assert outfit_state(state.player.outfit)["nudity_mode"] == "fully_nude"
    assert "completely nude" in positive
    assert "very short crimson wool chiton" not in positive
    assert "worn revealing leather armor" not in positive


def test_renderer_comfy_riceve_prompt_corretto(tmp_path):
    renderer = CaptureRenderer()
    gm = SequenceGM([_scene([_remove(CHITON), _remove(ARMOR)], "Ulisse stands completely nude in the cave.")])
    service = _service(tmp_path, gm, renderer=renderer)
    state = service.new_session("outfit-render")

    service.play(state, "mi spoglio")

    prompt = renderer.packages[0]["positive"].lower()
    assert "completely nude" in prompt
    assert "very short crimson wool chiton" not in prompt
    assert "worn revealing leather armor" not in prompt


def test_a1111_regressione_prompt_fully_nude_preparato_senza_abiti():
    pack = _pack()
    state = pack.new_world("outfit-a1111")
    state.player.outfit.remove_item(CHITON)
    state.player.outfit.remove_item(ARMOR)
    contract = build_visual_contract(
        state,
        pack,
        VisualMoment.from_dict(_visual("Ulisse moves through the cave.")),
        0,
    )
    positive = contract.prompt_package["positive"].lower()
    assert "completely nude" in positive
    assert "no chiton" in positive
    assert "very short crimson wool chiton" not in positive
    assert "worn revealing leather armor" not in positive


def test_outfit_diagnostics_salvati_per_turno(tmp_path):
    gm = SequenceGM([_scene([_remove(CHITON), _remove(ARMOR)], "Ulisse stands completely nude in the cave.")])
    service = _service(tmp_path, gm)
    state = service.new_session("outfit-diag")
    service.play(state, "mi spoglio")

    diag = service.store.load_turn_artifact(state.session_id, 0, "outfit_diagnostics")
    assert diag["source_of_truth"] == "WorldState.player.outfit"
    assert diag["outfit_state_before_turn"]["nudity_mode"] == "clothed"
    assert diag["outfit_state_after_turn"]["nudity_mode"] == "fully_nude"
    assert diag["outfit_state_saved"]["nudity_mode"] == "fully_nude"
    assert len(diag["outfit_mutations_applied"]) == 2
