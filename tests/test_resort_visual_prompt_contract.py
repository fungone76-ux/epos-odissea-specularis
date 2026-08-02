from pathlib import Path

from epos.contract import CheckProposal
from epos.llm import provider_chain_from_env
from epos.llm_retry import _semantic_retry_messages
from epos.prompt_phase1 import phase1_messages
from epos.prompt_phase2 import phase2_messages
from epos.prompt_visual_rules import RESORT_VISUAL_GENERATION_RULES
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.resort_turn_service import enforce_resort_player_pov, validate_resort_scene_policy
from epos.rules import Outcome, Roll
from epos.visual import build_visual_contract

from tests.test_resort_runtime_fidelity import _scene, _state

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def _resort_case(session="visual-contract"):
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, session)
    state.flags["resort_intro_active"] = False
    state.flags["resort_intro_completed"] = True
    state.flags["resort_intro_index"] = 4
    return pack, state


def _proposal():
    return CheckProposal(
        action_kind="intimate",
        skill="presence",
        difficulty=1,
        target_ids=["luna"],
        opposition="none",
        reason="Luna decide come guidare il rilassamento.",
        stakes={
            "full_success": "Luna procede con calma.",
            "partial_success": "Luna procede ma resta prudente.",
            "failure": "Luna rinvia.",
            "critical_failure": "Luna interrompe.",
        },
    )


def _roll():
    return Roll(pool_size=1, difficulty=1, dice=(6,), outcome=Outcome.FULL_SUCCESS)


def test_resort_visual_generation_rules_exist_in_dedicated_file():
    assert "VISUAL OUTPUT CONTRACT" in RESORT_VISUAL_GENERATION_RULES
    assert "visual_en" in RESORT_VISUAL_GENERATION_RULES
    assert "tags_en" in RESORT_VISUAL_GENERATION_RULES


def test_visual_contract_is_included_once_in_resort_phase1_system_prompt():
    pack, state = _resort_case("phase1-system")
    messages = phase1_messages(state, pack.world, "dimmi come")

    assert len(messages) == 2
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"].count("VISUAL OUTPUT CONTRACT") == 1
    assert "VISUAL OUTPUT CONTRACT" not in messages[1]["content"]


def test_visual_contract_is_included_once_in_resort_phase2_system_prompt():
    pack, state = _resort_case("phase2-system")
    messages = phase2_messages(
        state,
        pack.world,
        "comincia",
        _proposal().to_dict(),
        _roll().to_dict(),
        "Luna procede con calma.",
    )

    assert len(messages) == 2
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"].count("VISUAL OUTPUT CONTRACT") == 1
    assert "VISUAL OUTPUT CONTRACT" not in messages[1]["content"]


def test_retry_reuses_the_same_composed_system_prompt():
    pack, state = _resort_case("retry-system")
    messages = phase1_messages(state, pack.world, "sdraiati e mostrameli bene")

    retry_messages = _semantic_retry_messages(messages, {"problems": ["missing visual"]})

    assert retry_messages[0]["content"] == messages[0]["content"]
    assert retry_messages[0]["content"].count("VISUAL OUTPUT CONTRACT") == 1
    assert len(retry_messages) == len(messages)


def test_visual_contract_does_not_add_a_second_llm_call_or_message():
    pack, state = _resort_case("single-call-shape")

    assert len(phase1_messages(state, pack.world, "ciao")) == 2
    assert len(phase2_messages(state, pack.world, "ciao", _proposal().to_dict(), _roll().to_dict(), "ok")) == 2


def test_llm_max_attempt_defaults_remain_unchanged(monkeypatch):
    for key in (
        "EPOS_PRIMARY_LLM_PROVIDER",
        "EPOS_PRIMARY_LLM_BASE_URL",
        "EPOS_PRIMARY_LLM_MODEL",
        "EPOS_PRIMARY_LLM_KEY_ENV",
        "EPOS_PRIMARY_LLM_MAX_ATTEMPTS",
        "EPOS_LLM_MAX_ATTEMPTS",
        "EPOS_SECONDARY_LLM_MAX_ATTEMPTS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EPOS_LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("EPOS_LLM_MODEL", "test-model")
    monkeypatch.setenv("EPOS_LLM_API_KEY", "secret")
    monkeypatch.setenv("EPOS_SECONDARY_LLM_BASE_URL", "https://secondary.invalid/v1")
    monkeypatch.setenv("EPOS_SECONDARY_LLM_MODEL", "secondary-model")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")

    chain = provider_chain_from_env()

    assert chain.primary.max_attempts == 2
    assert chain.secondary is not None
    assert chain.secondary.max_attempts == 1


def test_player_off_camera_sunscreen_visual_is_accepted():
    pack, state = _state("prompt-off-camera")
    scene = _scene(
        visual_en="Luna applying sunscreen on the player, kneeling beside the unseen player.",
        tags=("kneeling", "sunscreen application", "player off camera"),
    )
    corrected = enforce_resort_player_pov(state, pack.world, scene)

    assert validate_resort_scene_policy(state, pack.world, corrected, "comincia pure").ok


def test_player_visible_visual_is_rejected():
    pack, state = _state("prompt-player-visible")
    scene = _scene(visual_en="Luna smiles while the player is visible beside her.")

    report = validate_resort_scene_policy(state, pack.world, scene, "ciao")

    assert any(error.code == "resort_player_visual_text_forbidden" for error in report.errors)


def test_named_missing_character_and_mandatory_requirements_are_rejected():
    pack, state = _state("prompt-validators")
    scene = _scene(
        visual_en="Luna and Maria stand near the massage table.",
        tags=("spa",),
    )

    report = validate_resort_scene_policy(state, pack.world, scene, "sdraiati e mostrameli bene")
    codes = {error.code for error in report.errors}

    assert "visible_character_text_conflict" in codes or "resort_mandatory_visual_requirement_missing" in codes
    assert "resort_mandatory_visual_requirement_missing" in codes


def test_python_compiler_keeps_identity_lora_outfit_and_concrete_action():
    pack, state = _state("prompt-compiler")
    scene = _scene(
        visual_en="Luna reclined on the massage table, bare feet clearly visible, showing her feet toward camera.",
        summary="Luna si sdraia e mostra i piedi.",
        tags=("lying down", "bare feet clearly visible", "showing her feet"),
    )
    contract = build_visual_contract(state, pack.world, scene.visual, state.turn)
    positive = contract.prompt_package["positive"]

    assert "fitted ivory VIP attendant mini dress" in positive
    assert "lora" in positive.lower() or "<lora:" in positive.lower()
    assert "reclined" in positive or "lying down" in positive
    assert "feet" in positive
    assert "bare feet clearly visible" in positive
