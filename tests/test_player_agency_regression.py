from pathlib import Path

from epos.contract import CheckProposal, FinalScene, VisualMoment
from epos.models import outfit_state
from epos.narrative_policy import derive_narrative_policy
from epos.outfit import format_current_outfit_for_ui
from epos.player_agency import (
    player_agency_diagnostics,
    validate_check_proposal_player_agency,
    validate_scene_player_agency,
)
from epos.validators import validate_scene
from epos.visual import build_visual_contract
from epos.worldpack import load_pack


PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


def _pack_state():
    pack = load_pack(PACK)
    state = pack.new_world("agency-regression")
    state.npcs["polifemo"].present = True
    state.npcs["polifemo"].location_id = state.location_id
    return pack, state


def _scene(**overrides):
    visual = {
        "summary": "Ulisse wakes on a straw bed",
        "focus_character": "player",
        "visible_characters": ["player"],
        "shared_action": False,
        "moment_type": "reaction",
        "speaker_character": "",
        "actor_character": "",
        "reactor_character": "player",
        "intimate_shared_moment": False,
        "multi_character_reason": "",
        "multi_character_participants": [],
        "visual_en": "Ulisse waking on a straw bed inside a filthy damp cave",
        "tags_en": ["full body", "dirty cave"],
    }
    data = {
        "narration": "Apri gli occhi sul giaciglio umido. La grotta odora di latte acido e paglia marcia.",
        "dialogue": [],
        "npc_actions": [],
        "intentions": [],
        "initiatives": [],
        "disclosure_events": [],
        "mutations": [],
        "memory_events": [],
        "visual": visual,
    }
    for key, value in overrides.items():
        if key == "visual":
            visual.update(value)
        else:
            data[key] = value
    return FinalScene.from_dict(data)


def _social_deception_check():
    return CheckProposal.from_dict(
        {
            "action_kind": "social",
            "skill": "dolos",
            "difficulty": 2,
            "target_ids": ["polifemo"],
            "opposition": "npc_resistance",
            "reason": "Ulisse prova a ingannare Polifemo per ottenere informazioni",
            "stakes": {
                "full_success": "Polifemo crede all'inganno.",
                "partial_success": "Polifemo dubita.",
                "failure": "Polifemo non crede.",
                "critical_failure": "Polifemo si irrita.",
            },
        }
    )


def test_mi_risveglio_non_crea_dialogo_player():
    pack, state = _pack_state()
    scene = _scene()
    report = validate_scene_player_agency(state, pack, scene, "mi risveglio su un letto di paglia")
    assert report.ok


def test_mi_risveglio_non_crea_prova_social():
    pack, state = _pack_state()
    report = validate_check_proposal_player_agency(
        state, pack, _social_deception_check(), "mi risveglio su un letto di paglia"
    )
    assert not report.ok
    assert report.errors[0].code == "player_action_semantic_drift"


def test_mi_risveglio_nuda_resta_neutral():
    pack, state = _pack_state()
    state.player.outfit.worn = ["barefoot"]
    policy = derive_narrative_policy(
        state,
        pack,
        "mi risveglio completamente nuda in un letto di paglia dentro ad una grotta fetida e sporca",
    )
    assert policy.applied_tone == "neutral"


def test_nudita_sola_non_e_intimacy_detected():
    pack, state = _pack_state()
    state.player.outfit.worn = ["barefoot"]
    policy = derive_narrative_policy(state, pack, "sono nuda nella grotta")
    assert policy.intimacy_detected is False
    assert policy.nudity_only_signal is True
    assert "nudity_alone_is_not_intimacy" in policy.intensity_blockers


def test_nudita_sola_consenso_not_applicable():
    pack, state = _pack_state()
    policy = derive_narrative_policy(state, pack, "mi risveglio nuda")
    assert policy.consent_state == "not_applicable"


def test_gm_non_inventa_obiettivo_fuga():
    pack, state = _pack_state()
    scene = _scene(narration="Decidi di trovare un piano di fuga e ottenere informazioni da Polifemo.")
    report = validate_scene_player_agency(state, pack, scene, "mi risveglio su un letto di paglia")
    assert not report.ok
    assert any(error.code == "invented_player_intention" for error in report.errors)


def test_gm_non_inventa_inganno():
    pack, state = _pack_state()
    scene = _scene(narration="Inganni Polifemo con una voce calma.")
    report = validate_scene_player_agency(state, pack, scene, "mi risveglio su un letto di paglia")
    assert not report.ok
    assert any(error.code == "player_action_semantic_drift" for error in report.errors)


def test_dialogue_speaker_player_inventato_rifiutato():
    pack, state = _pack_state()
    scene = _scene(dialogue=[{"speaker": "player", "text": "Dimmi come uscire.", "to": "polifemo"}])
    report = validate_scene_player_agency(state, pack, scene, "mi risveglio su un letto di paglia")
    assert not report.ok
    assert any(error.code == "invented_player_dialogue" for error in report.errors)


def test_citazione_esplicita_player_riportabile_invariata():
    pack, state = _pack_state()
    scene = _scene(dialogue=[{"speaker": "player", "text": "Chi sei?", "to": "polifemo"}])
    report = validate_scene_player_agency(state, pack, scene, 'dico "Chi sei?"')
    assert report.ok


def test_npc_puo_parlare_liberamente():
    pack, state = _pack_state()
    scene = _scene(dialogue=[{"speaker": "Polifemo", "text": "Chi entra nella mia grotta?", "to": "player"}])
    report = validate_scene_player_agency(state, pack, scene, "mi risveglio su un letto di paglia")
    assert report.ok


def test_visual_conserva_letto_di_paglia():
    pack, state = _pack_state()
    scene = _scene()
    report = validate_scene_player_agency(state, pack, scene, "mi risveglio su un letto di paglia")
    assert report.ok
    assert "straw bed" in scene.visual.visual_en


def test_visual_conserva_posa_di_risveglio():
    pack, state = _pack_state()
    scene = _scene()
    report = validate_scene_player_agency(state, pack, scene, "mi risveglio su un letto di paglia")
    assert report.ok
    assert "waking" in scene.visual.visual_en


def test_visible_solo_player_nessun_gigante_nel_visual_en():
    pack, state = _pack_state()
    scene = _scene(visual={"visual_en": "Ulisse wakes on a straw bed while Polyphemus stands behind her"})
    report = validate_scene(state, pack, scene)
    assert not report.ok
    assert any(error.code == "visible_character_text_conflict" for error in report.errors)

def test_visible_solo_player_accetta_nome_luogo_possessivo():
    pack, state = _pack_state()
    scene = _scene(
        visual={
            "summary": "Ulisse observes Polyphemus' cave from the entrance.",
            "visual_en": "Ulisse stands at the entrance of Polyphemus' cave, bow lowered and observing carefully.",
        }
    )
    report = validate_scene(state, pack, scene)
    assert report.ok


def test_full_body_close_up_conflitto_risolto():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        VisualMoment.from_dict(
            {
                **_scene().visual.__dict__,
                "visual_en": "Ulisse waking on a straw bed, close-up shot",
                "tags_en": ["full body", "close-up"],
            }
        ),
        0,
    )
    positive = contract.prompt_package["positive"].lower()
    assert "full body" in positive
    assert "close-up" not in positive
    assert "close up" not in positive
    assert contract.prompt_package["camera_tag_conflicts"]


def test_sanitizzazione_rimuove_intero_earnest_expression():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        VisualMoment.from_dict(
            {
                **_scene().visual.__dict__,
                "visual_en": "Ulisse waking on a straw bed, with an earnest expression",
            }
        ),
        0,
    )
    assert "with an earnest expression" not in contract.prompt_package["positive"]
    assert "with an earnest" not in contract.prompt_package["positive"]
    assert "with an earnest expression" in contract.prompt_package["facial_expression_sanitization"]["removed_terms"]


def test_athletic_body_presente_una_sola_volta():
    pack, state = _pack_state()
    contract = build_visual_contract(state, pack, VisualMoment.from_dict(_scene().visual.__dict__), 0)
    assert contract.prompt_package["positive"].count("athletic body") == 1


def test_outfit_fully_nude_invariato():
    pack, state = _pack_state()
    state.player.outfit.worn = ["barefoot"]
    state.player.outfit.removed = ["very short crimson wool chiton with deep low-cut neckline"]
    before = state.player.outfit.to_dict()
    derive_narrative_policy(state, pack, "mi risveglio nuda")
    assert state.player.outfit.to_dict() == before
    assert outfit_state(state.player.outfit)["nudity_mode"] == "fully_nude"


def test_ui_mostra_nuda():
    _pack, state = _pack_state()
    state.player.outfit.worn = ["barefoot"]
    assert format_current_outfit_for_ui(state.player).value == "Nuda"


def test_prompt_nude_coerente():
    pack, state = _pack_state()
    state.player.outfit.worn = ["barefoot"]
    contract = build_visual_contract(state, pack, VisualMoment.from_dict(_scene().visual.__dict__), 0)
    assert contract.prompt_package["nudity_mode"] == "fully_nude"
    assert "completely nude" in contract.prompt_package["positive"]
    assert "no clothing" in contract.prompt_package["positive"]


def test_speaker_focus_invariato():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        VisualMoment.from_dict(
            {
                **_scene().visual.__dict__,
                "focus_character": "player",
                "visible_characters": ["player", "polifemo"],
                "shared_action": True,
                "moment_type": "speech",
                "speaker_character": "polifemo",
                "visual_en": "Polyphemus speaks from the cave threshold",
            }
        ),
        0,
    )
    assert contract.focus_character == "polifemo"
    assert contract.visible_characters == ["polifemo"]


def test_comfyui_invariato():
    pack, state = _pack_state()
    contract = build_visual_contract(state, pack, VisualMoment.from_dict(_scene().visual.__dict__), 0)
    assert "positive" in contract.prompt_package
    assert "negative" in contract.prompt_package


def test_a1111_invariato():
    pack, state = _pack_state()
    contract = build_visual_contract(state, pack, VisualMoment.from_dict(_scene().visual.__dict__), 0)
    assert contract.prompt_package["positive_prompt"] == contract.prompt_package["positive"]
    assert contract.prompt_package["negative_prompt"] == contract.prompt_package["negative"]


def test_diagnostica_agency_regressione():
    pack, state = _pack_state()
    diag = player_agency_diagnostics(
        state,
        "mi risveglio su un letto di paglia",
        proposal=_social_deception_check(),
        scene=_scene(dialogue=[{"speaker": "Ulisse", "text": "Dimmi come uscire.", "to": "polifemo"}]),
    ).to_dict()
    assert diag["player_input_action"] == "waking"
    assert diag["proposed_player_action"] == "deception"
    assert diag["player_agency_violation"] is True
    assert diag["invented_player_dialogue"] is True
    assert diag["action_semantic_drift"] is True
