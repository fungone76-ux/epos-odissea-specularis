import random
from pathlib import Path

from epos.contract import CheckProposal, FinalScene, GmPhaseResponse, VisualMoment
from epos.models import Relationship
from epos.narrative_policy import derive_narrative_policy
from epos.prompt import phase1_messages, phase2_messages
from epos.renderers import RenderRecord
from epos.rules import Outcome, Roll
from epos.state_store import StateStore
from epos.turn_service import PlayerDecision, TurnService
from epos.visual import build_visual_contract
from epos.worldpack import load_pack


PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"
LUNA_BEFORE = "score_9, score_8_up, masterpiece, photorealistic, detailed, atmospheric, stsdebbie, dynamic pose, 1girl, mature woman, brown hair, shiny skin, head tilt, massive breasts, cleavage"
LUNA_AFTER = "score_9, score_8_up, masterpiece, photorealistic, detailed, atmospheric, stsdebbie, dynamic pose, 1girl, mature woman, brown hair, athletic body, shiny skin, head tilt, massive breasts, cleavage"
LUNA_LORA = "<lora:stsDebbie-10e:0.7>"
CHITON = "very short crimson wool chiton with deep low-cut neckline"


def _pack():
    return load_pack(PACK)


def _state():
    pack = _pack()
    state = pack.new_world("narrative-policy")
    state.npcs["penelope"].present = True
    state.npcs["penelope"].location_id = state.location_id
    state.npcs["penelope"].relationships["player"] = Relationship(
        attraction=35, trust=35
    )
    return pack, state


def _scene(**overrides):
    data = {
        "narration": "Ulisse osserva la costa.",
        "dialogue": [{"speaker": "Penelope", "to": "player", "text": "Ti ascolto."}],
        "npc_actions": [],
        "intentions": [],
        "initiatives": [],
        "disclosure_events": [],
        "mutations": [],
        "memory_events": [],
        "visual": {
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
            "visual_en": "Ulisse stands on volcanic rock.",
            "tags_en": ["full body"],
        },
    }
    data.update(overrides)
    return FinalScene.from_dict(data)


def _proposal(action_kind="social", skill="eros"):
    return CheckProposal.from_dict(
        {
            "action_kind": action_kind,
            "skill": skill,
            "difficulty": 2,
            "target_ids": ["penelope"],
            "opposition": "npc_resistance",
            "reason": "tensione intima",
            "stakes": {
                "full_success": "ok",
                "partial_success": "partial",
                "failure": "fail",
                "critical_failure": "bad",
            },
        }
    )


def _roll(outcome):
    return Roll(pool_size=3, difficulty=2, dice=(6, 5), outcome=outcome)


def test_base_prompt_ulisse_contiene_athletic_body():
    pack = _pack()
    assert "athletic body" in pack.visual_sheets["player"].base_prompt


def test_athletic_body_compare_una_sola_volta():
    pack = _pack()
    assert pack.visual_sheets["player"].base_prompt.count("athletic body") == 1


def test_lora_e_pesi_invariati():
    pack = _pack()
    sheet = pack.visual_sheets["player"]
    assert sheet.character_lora_en == LUNA_LORA
    assert "<lora:stsDebbie-10e:0.7>" == LUNA_LORA


def test_altri_tratti_identitari_invariati():
    pack = _pack()
    base = pack.visual_sheets["player"].base_prompt
    for trait in (
        "mature woman",
        "brown hair",
        "shiny skin",
        "head tilt",
        "massive breasts",
        "cleavage",
    ):
        assert trait in base
    assert "muscular body" not in base
    assert "bodybuilder" not in base
    assert "overly muscular" not in base


def test_base_prompt_prima_e_dopo_sono_modifica_minima():
    assert LUNA_AFTER == LUNA_BEFORE.replace("brown hair, shiny skin", "brown hair, athletic body, shiny skin")


def test_prompt_finale_conserva_athletic_body():
    pack, state = _state()
    contract = build_visual_contract(
        state,
        pack,
        VisualMoment.from_dict(_scene().visual.__dict__),
        0,
    )
    assert "athletic body" in contract.prompt_package["positive"]
    assert contract.prompt_package["positive"].count("athletic body") == 1


def test_nessuna_duplicazione_nei_turni_successivi():
    pack, state = _state()
    for turn in range(3):
        contract = build_visual_contract(
            state,
            pack,
            VisualMoment.from_dict(_scene().visual.__dict__),
            turn,
        )
        assert contract.prompt_package["positive"].count("athletic body") == 1


def test_esplorazione_neutra_neutral():
    pack, state = _state()
    policy = derive_narrative_policy(state, pack, "osservo la costa e cerco tracce")
    assert policy.applied_tone == "neutral"


def test_combattimento_neutral():
    pack, state = _state()
    policy = derive_narrative_policy(state, pack, "attacco Polifemo con il pugnale")
    assert policy.applied_tone == "neutral"
    assert "combat_context" in policy.intensity_blockers


def test_flirt_leggero_suggestive():
    pack, state = _state()
    policy = derive_narrative_policy(state, pack, "sussurro una provocazione leggera")
    assert policy.applied_tone == "suggestive"


def test_tensione_romantica_reciproca_sensual():
    pack, state = _state()
    policy = derive_narrative_policy(
        state, pack, "Penelope ricambia la carezza con tenerezza"
    )
    assert policy.applied_tone == "sensual"
    assert "reciprocal_romantic_tension" in policy.intensity_reasons


def test_nudita_non_erotica_non_oltre_sensual():
    pack, state = _state()
    state.player.outfit.remove_item(CHITON)
    policy = derive_narrative_policy(state, pack, "mi spoglio per lavarmi al mare")
    assert policy.applied_tone == "neutral"
    assert policy.intimacy_detected is False
    assert policy.consent_state == "not_applicable"
    assert policy.nudity_only_signal is True
    assert "nudity_alone_is_not_intimacy" in policy.intensity_blockers


def test_seduzione_consensuale_adulta_erotic():
    pack, state = _state()
    policy = derive_narrative_policy(
        state,
        pack,
        "seduco Penelope, che ricambia e acconsente al contatto intimo",
        proposal=_proposal(action_kind="intimate"),
    )
    assert policy.applied_tone == "erotic"
    assert policy.consent_state == "consented"


def test_scena_sessuale_adulta_richiesta_consensuale_explicit_adult():
    pack, state = _state()
    policy = derive_narrative_policy(
        state,
        pack,
        "Penelope acconsente: vogliamo fare l'amore di comune accordo",
        proposal=_proposal(action_kind="intimate"),
    )
    assert policy.applied_tone == "explicit_adult"
    assert policy.adult_participants_verified is True


def test_consenso_unknown_non_explicit_adult():
    pack, state = _state()
    policy = derive_narrative_policy(
        state, pack, "voglio fare l'amore con Penelope", proposal=_proposal("intimate")
    )
    assert policy.consent_state == "unknown"
    assert policy.applied_tone != "explicit_adult"


def test_consenso_negato_blocca_erotic_explicit():
    pack, state = _state()
    policy = derive_narrative_policy(
        state,
        pack,
        "Penelope rifiuta, ma provo a sedurla e a fare l'amore",
        proposal=_proposal("intimate"),
    )
    assert policy.consent_state == "not_consented"
    assert policy.applied_tone not in ("erotic", "explicit_adult")


def test_personaggio_incapace_di_scegliere_blocca():
    pack, state = _state()
    policy = derive_narrative_policy(
        state,
        pack,
        "Penelope dorme, provo a fare l'amore",
        proposal=_proposal("intimate"),
    )
    assert "incapable_to_choose" in policy.intensity_blockers
    assert policy.applied_tone not in ("erotic", "explicit_adult")


def test_attrazione_alta_senza_consenso_blocca_explicit():
    pack, state = _state()
    state.npcs["penelope"].relationships["player"].attraction = 80
    policy = derive_narrative_policy(
        state, pack, "mi avvicino a Penelope con desiderio", proposal=_proposal()
    )
    assert "penelope:high_attraction" in policy.intensity_reasons
    assert policy.consent_state == "unknown"
    assert policy.applied_tone != "explicit_adult"


def test_full_success_conserva_tono_coerente():
    pack, state = _state()
    policy = derive_narrative_policy(
        state,
        pack,
        "Penelope acconsente: vogliamo fare l'amore di comune accordo",
        proposal=_proposal("intimate"),
        roll=_roll(Outcome.FULL_SUCCESS),
    )
    assert policy.applied_tone == "explicit_adult"
    assert "full_success_may_intensify_within_limits" in policy.intensity_reasons


def test_failure_non_diventa_successo_erotico():
    pack, state = _state()
    policy = derive_narrative_policy(
        state,
        pack,
        "Penelope acconsente: vogliamo fare l'amore di comune accordo",
        proposal=_proposal("intimate"),
        roll=_roll(Outcome.FAILURE),
    )
    assert policy.applied_tone == "sensual"
    assert "failure_cannot_be_rewritten_as_erotic_success" in policy.intensity_blockers


def test_retry_conserva_livello_scelto():
    pack, state = _state()
    text = "Penelope acconsente: vogliamo fare l'amore di comune accordo"
    proposal = _proposal("intimate")
    roll = _roll(Outcome.FULL_SUCCESS)
    first = phase2_messages(state, pack, text, proposal.to_dict(), roll.to_dict(), "ok")
    retry = phase2_messages(state, pack, text, proposal.to_dict(), roll.to_dict(), "ok")
    assert '"narrative_intensity": "explicit_adult"' in first[-1]["content"]
    assert first[-1]["content"] == retry[-1]["content"]


def test_narrazione_neutra_non_riceve_lessico_sessuale_dalla_policy():
    pack, state = _state()
    policy = derive_narrative_policy(state, pack, "cammino sulla spiaggia")
    assert policy.applied_tone == "neutral"
    assert policy.intimacy_detected is False


def test_dialogo_erotico_mantiene_voce_del_personaggio_nel_prompt():
    pack, state = _state()
    msg = phase1_messages(
        state,
        pack,
        "Penelope acconsente: vogliamo fare l'amore di comune accordo",
    )[-1]["content"]
    assert '"speech_style": "Parla poco' in msg
    assert '"narrative_intensity": "explicit_adult"' in msg


def test_visual_policy_invariata():
    pack, state = _state()
    before = pack.visual_policy.__dict__.copy()
    derive_narrative_policy(state, pack, "Penelope acconsente al contatto intimo")
    assert pack.visual_policy.__dict__ == before


def test_speaker_focus_invariato():
    pack, state = _state()
    moment = VisualMoment.from_dict(
        {
            **_scene().visual.__dict__,
            "focus_character": "player",
            "visible_characters": ["player", "penelope"],
            "shared_action": True,
            "moment_type": "speech",
            "speaker_character": "penelope",
        }
    )
    contract = build_visual_contract(state, pack, moment, 0)
    assert contract.focus_character == "penelope"
    assert contract.visible_characters == ["penelope"]


def test_outfit_state_invariato():
    pack, state = _state()
    before = state.player.outfit.to_dict()
    derive_narrative_policy(
        state, pack, "Penelope acconsente al contatto intimo", proposal=_proposal("intimate")
    )
    assert state.player.outfit.to_dict() == before


def test_comfyui_prompt_shape_invariato():
    pack, state = _state()
    contract = build_visual_contract(
        state,
        pack,
        VisualMoment.from_dict(_scene().visual.__dict__),
        0,
    )
    assert "positive" in contract.prompt_package
    assert "negative" in contract.prompt_package
    assert contract.prompt_package["character_lora_by_character"]["player"] == LUNA_LORA


def test_a1111_prompt_shape_invariato():
    pack, state = _state()
    contract = build_visual_contract(
        state,
        pack,
        VisualMoment.from_dict(_scene().visual.__dict__),
        0,
    )
    assert contract.prompt_package["positive_prompt"] == contract.prompt_package["positive"]
    assert contract.prompt_package["negative_prompt"] == contract.prompt_package["negative"]


class OneSceneGM:
    def propose(self, state, pack, player_text):
        return GmPhaseResponse(mode="no_check", scene=_scene())


class CaptureRenderer:
    def render(self, prompt_package, out_dir):
        return RenderRecord(status="complete", image_path=str(out_dir / "image.png"), backend="capture")


def test_narrative_diagnostics_salvati_per_turno(tmp_path):
    pack, state = _state()
    service = TurnService(
        gm=OneSceneGM(),
        pack=pack,
        store=StateStore(tmp_path / "saves"),
        rng=random.Random(7),
        decision_provider=lambda *a, **k: PlayerDecision(choice="safe"),
        renderer=CaptureRenderer(),
    )

    service.play(state, "Penelope ricambia la carezza con tenerezza")

    diag = service.store.load_turn_artifact(state.session_id, 0, "narrative_diagnostics")
    assert diag["narrative_intensity"] == "sensual"
    assert diag["base_prompt_athletic_body_present"] is True
    assert diag["base_prompt_athletic_body_count"] == 1
    assert diag["requested_tone"] == "sensual"
    assert diag["applied_tone"] == "sensual"
    assert diag["narrative_intensity_before"] == "sensual"
    assert diag["narrative_intensity_after"] == "sensual"
    assert diag["tone_changed_during_retry"] is False
