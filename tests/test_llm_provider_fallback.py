import json
import urllib.error
from pathlib import Path

import pytest

from epos.contract import GmPhaseResponse
from epos.gm import GameMasterError, OpenAICompatibleGameMaster
from epos.llm import LlmProviderChain, LlmProviderConfig
from epos.turn_service import TurnService
from epos.visual import build_visual_contract
from epos.worldpack import load_pack


PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"
LUNA = "score_9, score_8_up, masterpiece, photorealistic, detailed, atmospheric, stsdebbie, dynamic pose, 1girl, mature woman, brown hair, athletic body, shiny skin, head tilt, massive breasts, cleavage"
LUNA_LORA = "<lora:stsDebbie-10e:0.7>"


def _scene(visual_en="Ulisse on all fours, both hands on volcanic rock"):
    return {
        "narration": "La scena si chiude in modo valido.",
        "dialogue": [],
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
            "visual_en": visual_en,
            "tags_en": ["volcanic coast"],
        },
    }


def _phase():
    return {"mode": "no_check", "scene": _scene()}


def _openai_response(content, usage=None):
    payload = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        payload["usage"] = dict(usage)
    return payload


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeOpen:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        self.requests.append(
            {
                "url": request.full_url,
                "model": body["model"],
                "messages": body["messages"],
                "headers": dict(request.header_items()),
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return _Response(outcome)


def _chain(fake):
    return LlmProviderChain(
        primary=LlmProviderConfig(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-3.6-flash",
            "GEMINI_API_KEY",
            max_attempts=2,
        ),
        secondary=LlmProviderConfig(
            "zai", "https://api.z.ai/api/paas/v4", "glm-4.7-flash", "ZAI_API_KEY", max_attempts=1
        ),
        opener=fake,
    )


def _gm(fake):
    return OpenAICompatibleGameMaster(provider_chain=_chain(fake))


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "zai-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")


def test_gemini_primario_valido_non_chiama_zai():
    fake = FakeOpen([_openai_response(json.dumps(_phase()))])
    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )
    assert result.value.mode == "no_check"
    assert len(fake.requests) == 1
    assert fake.requests[0]["model"] == "gemini-3.6-flash"
    assert result.diagnostics["selected_provider"] == "gemini"
    assert result.diagnostics["fallback_triggered"] is False


def test_diagnostics_include_token_usage_when_provider_returns_it():
    usage = {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19}
    fake = FakeOpen([_openai_response(json.dumps(_phase()), usage=usage)])

    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )

    assert result.diagnostics["token_usage"] == usage
    assert result.diagnostics["provider_attempts"][0]["token_usage"] == usage


def test_retry_gemini_riuscito_non_chiama_zai():
    fake = FakeOpen([TimeoutError(), _openai_response(json.dumps(_phase()))])
    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )
    assert result.diagnostics["selected_provider"] == "gemini"
    assert result.diagnostics["fallback_triggered"] is False
    assert result.diagnostics["fallback_reason"] == ""
    assert [a["provider"] for a in result.diagnostics["provider_attempts"]] == ["gemini", "gemini"]


def test_http_error_gemini_chiama_zai():
    err = urllib.error.HTTPError("u", 503, "busy", {}, None)
    fake = FakeOpen([err, err, _openai_response(json.dumps(_phase()))])
    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )
    assert result.diagnostics["provider_attempts"][0]["status"] == "http_error"
    assert result.diagnostics["selected_provider"] == "zai"


def test_json_invalido_gemini_chiama_zai():
    fake = FakeOpen([
        _openai_response("{bad"),
        _openai_response("{bad"),
        _openai_response(json.dumps(_phase())),
    ])
    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )
    assert result.diagnostics["fallback_reason"] == "primary_invalid_json"
    assert result.value.mode == "no_check"
    assert result.diagnostics["selected_provider"] == "zai"


def test_schema_invalido_gemini_chiama_zai():
    fake = FakeOpen([
        _openai_response(json.dumps({"mode": "nope"})),
        _openai_response(json.dumps({"mode": "nope"})),
        _openai_response(json.dumps(_phase())),
    ])
    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )
    assert result.diagnostics["fallback_reason"] == "primary_contract_invalid"
    assert result.diagnostics["selected_provider"] == "zai"


def test_validazione_semantica_gemini_fallita_chiama_zai():
    invalid = {"mode": "check_proposal", "check": {
        "action_kind": "physical",
        "skill": "sarissa",
        "difficulty": 99,
        "target_ids": [],
        "opposition": "none",
        "reason": "bad",
        "stakes": {
            "full_success": "a",
            "partial_success": "b",
            "failure": "c",
            "critical_failure": "d",
        },
    }}
    fake = FakeOpen([
        _openai_response(json.dumps(invalid)),
        _openai_response(json.dumps(invalid)),
        _openai_response(json.dumps(_phase())),
    ])
    gm = _gm(fake)
    pack = load_pack(PACK)
    state = pack.new_world("llm-semantic")
    service = TurnService(gm=gm, pack=pack)
    result = service.play(state, "osservo")
    assert result.mode == "no_check"
    assert gm.last_llm_diagnostics["selected_provider"] == "zai"
    assert gm.last_llm_diagnostics["fallback_reason"] == "primary_semantic_validation_failed"


def test_entrambi_falliscono_errore_controllato():
    fake = FakeOpen([TimeoutError(), TimeoutError(), _openai_response("{bad")])
    with pytest.raises(Exception) as exc:
        _chain(fake).complete_json(
            [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            phase="proposal",
            parse=GmPhaseResponse.from_dict,
        )
    assert "All LLM providers failed" in str(exc.value)
    assert len(fake.requests) == 3


def test_fallback_disabilitato_non_chiama_zai():
    fake = FakeOpen([TimeoutError(), TimeoutError()])
    chain = LlmProviderChain(
        primary=LlmProviderConfig("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.6-flash", "GEMINI_API_KEY", max_attempts=2),
        secondary=LlmProviderConfig("zai", "https://api.z.ai/api/paas/v4", "glm-4.7-flash", "ZAI_API_KEY"),
        fallback_enabled=False,
        opener=fake,
    )
    with pytest.raises(Exception):
        chain.complete_json(
            [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            phase="proposal",
            parse=GmPhaseResponse.from_dict,
        )
    assert len(fake.requests) == 2


def test_configurazione_legacy(monkeypatch):
    for name in (
        "EPOS_PRIMARY_LLM_PROVIDER",
        "EPOS_PRIMARY_LLM_BASE_URL",
        "EPOS_PRIMARY_LLM_MODEL",
        "EPOS_PRIMARY_LLM_KEY_ENV",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EPOS_LLM_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("EPOS_LLM_MODEL", "legacy-model")
    monkeypatch.setenv("EPOS_LLM_KEY_ENV", "LEGACY_KEY")
    monkeypatch.setenv("LEGACY_KEY", "legacy-secret")
    gm = OpenAICompatibleGameMaster(provider_chain=None)
    assert gm.provider_chain.primary.provider_id == "legacy"
    assert gm.provider_chain.primary.model == "legacy-model"


def test_configurazione_env_zai_primario_gemini_secondario(monkeypatch):
    for name in (
        "EPOS_PRIMARY_LLM_PROVIDER",
        "EPOS_PRIMARY_LLM_BASE_URL",
        "EPOS_PRIMARY_LLM_MODEL",
        "EPOS_PRIMARY_LLM_KEY_ENV",
        "EPOS_SECONDARY_LLM_PROVIDER",
        "EPOS_SECONDARY_LLM_BASE_URL",
        "EPOS_SECONDARY_LLM_MODEL",
        "EPOS_SECONDARY_LLM_KEY_ENV",
        "EPOS_LLM_FALLBACK_ENABLED",
        "GEMINI_API_KEY",
        "ZAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    env_values = {
        "EPOS_PRIMARY_LLM_PROVIDER": "zai",
        "EPOS_PRIMARY_LLM_BASE_URL": "https://api.z.ai/api/paas/v4",
        "EPOS_PRIMARY_LLM_MODEL": "glm-4.7-flash",
        "EPOS_PRIMARY_LLM_KEY_ENV": "ZAI_API_KEY",
        "EPOS_SECONDARY_LLM_PROVIDER": "gemini",
        "EPOS_SECONDARY_LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai",
        "EPOS_SECONDARY_LLM_MODEL": "gemini-2.5-flash",
        "EPOS_SECONDARY_LLM_KEY_ENV": "GEMINI_API_KEY",
        "EPOS_LLM_FALLBACK_ENABLED": "true",
    }
    for name, value in env_values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("ZAI_API_KEY", "zai-test-key")
    gm = OpenAICompatibleGameMaster(provider_chain=None)
    assert gm.provider_chain.primary.provider_id == "zai"
    assert gm.provider_chain.primary.model == "glm-4.7-flash"
    assert gm.provider_chain.primary.key_env == "ZAI_API_KEY"
    assert gm.provider_chain.secondary.provider_id == "gemini"
    assert gm.provider_chain.secondary.model == "gemini-2.5-flash"
    assert gm.provider_chain.secondary.key_env == "GEMINI_API_KEY"


def test_chiave_secondaria_assente(monkeypatch):
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    valid_fake = FakeOpen([_openai_response(json.dumps(_phase()))])
    result = _chain(valid_fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )
    assert result.diagnostics["selected_provider"] == "gemini"

    fail_fake = FakeOpen([TimeoutError(), TimeoutError()])
    with pytest.raises(Exception) as exc:
        _chain(fail_fake).complete_json(
            [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            phase="proposal",
            parse=GmPhaseResponse.from_dict,
        )
    assert "fallback is not available" in str(exc.value) or "All LLM providers failed" in str(exc.value)


def test_diagnostica_non_contiene_chiavi_o_authorization():
    fake = FakeOpen([TimeoutError(), TimeoutError(), _openai_response(json.dumps(_phase()))])
    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )
    text = json.dumps(result.diagnostics)
    assert "zai-test-key" not in text
    assert "gemini-test-key" not in text
    assert "Authorization" not in text
    assert "provider_attempts" in result.diagnostics


def test_diagnostico_normale_solo_gemini():
    fake = FakeOpen([_openai_response(json.dumps(_phase()))])
    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )
    assert result.diagnostics["selected_provider"] == "gemini"
    assert result.diagnostics["selected_model"] == "gemini-3.6-flash"
    assert result.diagnostics["fallback_triggered"] is False
    assert result.diagnostics["fallback_reason"] == ""
    assert [a["provider"] for a in result.diagnostics["provider_attempts"]] == ["gemini"]


def test_diagnostico_fallback_mostra_gemini_prima_di_zai():
    fake = FakeOpen([_openai_response("{bad"), _openai_response("{bad"), _openai_response(json.dumps(_phase()))])
    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        phase="proposal",
        parse=GmPhaseResponse.from_dict,
    )
    assert result.diagnostics["selected_provider"] == "zai"
    assert [a["provider"] for a in result.diagnostics["provider_attempts"]] == ["gemini", "gemini", "zai"]


def test_stesso_prompt_per_zai_e_gemini():
    messages = [{"role": "system", "content": "same system"}, {"role": "user", "content": "same user"}]
    fake = FakeOpen([TimeoutError(), TimeoutError(), _openai_response(json.dumps(_phase()))])
    _chain(fake).complete_json(messages, phase="proposal", parse=GmPhaseResponse.from_dict)
    assert fake.requests[0]["messages"] == messages
    assert fake.requests[1]["messages"] == messages
    assert fake.requests[2]["messages"] == messages


def test_odissea_visuale_restano_prompt_lora_visual_e_sanitizzazione():
    pack = load_pack(PACK)
    state = pack.new_world("llm-visual")
    moment = GmPhaseResponse.from_dict({
        "mode": "no_check",
        "scene": _scene(
            "Ulisse on all fours, her bronze-ringed braided hair wind-swept, "
            "both hands on volcanic rock"
        ),
    }).scene.visual
    contract = build_visual_contract(state, pack, moment, 0)
    positive = contract.prompt_package["positive"]
    assert positive.startswith(LUNA)
    assert LUNA_LORA in positive
    assert "on all fours" in positive
    assert "both hands on volcanic rock" in positive
    assert "braided" not in positive[len(LUNA):].lower()
