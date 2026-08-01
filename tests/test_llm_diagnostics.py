import json
from pathlib import Path

import pytest

from epos.contract import GmPhaseResponse
from epos.gm import OpenAICompatibleGameMaster
from epos.llm import LlmProviderChain, LlmProviderConfig
from epos.state_store import StateStore
from epos.turn_service import TurnService
from epos.worldpack import load_pack


PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


def _scene(**overrides):
    data = {
        "narration": "Valid scene.",
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
            "visual_en": "Ulisse standing on volcanic rock",
            "tags_en": ["volcanic coast"],
        },
    }
    data.update(overrides)
    return data


def _phase(scene=None):
    return {"mode": "no_check", "scene": scene or _scene()}


def _openai_response(content):
    return {"choices": [{"message": {"content": content}}]}


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

    def __call__(self, request, timeout):
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
            "zai",
            "https://api.z.ai/api/paas/v4",
            "glm-4.7-flash",
            "ZAI_API_KEY",
            max_attempts=1,
        ),
        opener=fake,
    )


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("ZAI_API_KEY", "zai-test-key")


def _service(tmp_path, fake):
    pack = load_pack(PACK)
    gm = OpenAICompatibleGameMaster(provider_chain=_chain(fake))
    store = StateStore(tmp_path / "saves")
    state = pack.new_world("diag-session")
    service = TurnService(gm=gm, pack=pack, store=store)
    return service, state, store, gm


def _turn_dir(store):
    return store.turn_dir("diag-session", 0)


def test_semantic_failure_diagnostics_have_reason_and_report(tmp_path):
    invalid_scene = _scene(
        memory_events=[
            {
                "summary": "bad witness",
                "witnesses": ["not_present_npc"],
                "level": "immediate",
                "emotional_impact": 0,
                "public": True,
            }
        ]
    )
    fake = FakeOpen([
        _openai_response(json.dumps(_phase(invalid_scene))),
        _openai_response(json.dumps(_phase(invalid_scene))),
        _openai_response(json.dumps(_phase())),
    ])
    service, state, store, gm = _service(tmp_path, fake)
    service.play(state, "osservo")

    attempts = gm.last_llm_diagnostics["provider_attempts"]
    first = attempts[0]
    assert first["status"] == "semantic_validation_failed"
    assert first["validation_stage"] == "semantic"
    assert first["validation_reason"] == "invalid_memory_witness"
    assert first["validation_errors"][0]["path"] == "memory_events[0].witnesses[0]"
    report_path = _turn_dir(store) / first["validation_report_path"]
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["errors"][0]["code"] == "invalid_memory_witness"


def test_raw_response_saved_and_sanitized(tmp_path):
    secret_text = "Authorization: Bearer should-not-appear"
    invalid = json.dumps({"mode": "nope", "note": secret_text})
    fake = FakeOpen([
        _openai_response(invalid),
        _openai_response(invalid),
        _openai_response(json.dumps(_phase())),
    ])
    service, state, store, gm = _service(tmp_path, fake)
    service.play(state, "osservo")

    first = gm.last_llm_diagnostics["provider_attempts"][0]
    raw = (_turn_dir(store) / first["raw_response_path"]).read_text(encoding="utf-8")
    assert "should-not-appear" not in raw
    assert "Authorization: Bearer [REDACTED]" in raw


def test_parsed_response_saved_for_semantic_invalid(tmp_path):
    invalid_scene = _scene(visual={**_scene()["visual"], "visible_characters": ["polifemo"], "focus_character": "polifemo"})
    fake = FakeOpen([
        _openai_response(json.dumps(_phase(invalid_scene))),
        _openai_response(json.dumps(_phase())),
    ])
    chain = LlmProviderChain(
        primary=LlmProviderConfig("gemini", "https://g.example/v1", "gemini-3.6-flash", "GEMINI_API_KEY", max_attempts=1),
        secondary=LlmProviderConfig("zai", "https://z.example/v1", "glm-4.7-flash", "ZAI_API_KEY", max_attempts=1),
        opener=fake,
    )
    pack = load_pack(PACK)
    gm = OpenAICompatibleGameMaster(provider_chain=chain)
    store = StateStore(tmp_path / "saves")
    state = pack.new_world("diag-session")
    TurnService(gm=gm, pack=pack, store=store).play(state, "osservo")
    first = gm.last_llm_diagnostics["provider_attempts"][0]
    parsed = json.loads((_turn_dir(store) / first["parsed_response_path"]).read_text(encoding="utf-8"))
    assert parsed["mode"] == "no_check"
    assert parsed["scene"]["visual"]["visible_characters"] == ["polifemo"]


def test_invalid_json_has_raw_no_parsed_and_parsing_stage(tmp_path):
    fake = FakeOpen([
        _openai_response("{bad Authorization: Bearer should-not-appear"),
        _openai_response("{bad"),
        _openai_response(json.dumps(_phase())),
    ])
    service, state, store, gm = _service(tmp_path, fake)
    service.play(state, "osservo")

    first = gm.last_llm_diagnostics["provider_attempts"][0]
    assert first["status"] == "invalid_json"
    assert first["validation_stage"] == "parsing"
    assert first["validation_errors"][0]["code"] == "invalid_json"
    assert "parsed_response_path" not in first
    raw = (_turn_dir(store) / first["raw_response_path"]).read_text(encoding="utf-8")
    assert "should-not-appear" not in raw


def test_schema_invalid_has_schema_stage_and_field_path(tmp_path):
    fake = FakeOpen([
        _openai_response(json.dumps({"mode": "nope"})),
        _openai_response(json.dumps({"mode": "nope"})),
        _openai_response(json.dumps(_phase())),
    ])
    service, state, _store, gm = _service(tmp_path, fake)
    service.play(state, "osservo")

    first = gm.last_llm_diagnostics["provider_attempts"][0]
    assert first["status"] == "contract_invalid"
    assert first["validation_stage"] == "schema"
    assert first["validation_errors"][0]["code"] == "schema_validation_failed"


def test_success_diagnostics_have_no_validation_errors_or_secrets(tmp_path):
    fake = FakeOpen([_openai_response(json.dumps(_phase()))])
    service, state, store, gm = _service(tmp_path, fake)
    service.play(state, "osservo")

    diag = json.loads((_turn_dir(store) / "llm_diagnostics.json").read_text(encoding="utf-8"))
    assert diag["selected_provider"] == "gemini"
    assert diag["provider_attempts"][0]["status"] == "success"
    assert diag["provider_attempts"][0]["validation_errors"] == []
    text = json.dumps(diag)
    assert "gemini-test-key" not in text
    assert "zai-test-key" not in text
    assert "Authorization" not in text


def test_multiple_failed_providers_have_separate_files(tmp_path):
    fake = FakeOpen([
        _openai_response("{bad"),
        _openai_response("{bad"),
        _openai_response("{bad"),
    ])
    service, state, store, _gm = _service(tmp_path, fake)
    with pytest.raises(Exception):
        service.play(state, "osservo")

    diag = json.loads((_turn_dir(store) / "llm_diagnostics.json").read_text(encoding="utf-8"))
    attempts = diag["provider_attempts"]
    assert [a["provider"] for a in attempts] == ["gemini", "gemini", "zai"]
    paths = {a["raw_response_path"] for a in attempts}
    assert len(paths) == 3
    for attempt in attempts:
        assert (_turn_dir(store) / attempt["raw_response_path"]).is_file()
        assert (_turn_dir(store) / attempt["validation_report_path"]).is_file()
