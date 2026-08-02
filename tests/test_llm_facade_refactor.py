import json
from inspect import signature

import pytest

from epos.llm import (
    LlmProviderChain,
    LlmProviderConfig,
    LlmProviderError,
)


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
                "timeout": timeout,
                "body": body,
                "headers": dict(request.header_items()),
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return _Response(outcome)


def _chain(fake, *, max_attempts=1):
    return LlmProviderChain(
        primary=LlmProviderConfig(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-3.6-flash",
            "GEMINI_API_KEY",
            timeout_seconds=17,
            max_attempts=max_attempts,
        ),
        secondary=None,
        fallback_enabled=False,
        opener=fake,
    )


def _openai_response(content, usage=None):
    payload = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        payload["usage"] = dict(usage)
    return payload


def test_llm_public_api_is_stable():
    import epos.llm as llm

    assert [name for name in dir(llm) if not name.startswith("_")] == [
        "Any",
        "Callable",
        "Generic",
        "LlmCallResult",
        "LlmProviderChain",
        "LlmProviderConfig",
        "LlmProviderError",
        "Path",
        "T",
        "TypeVar",
        "annotations",
        "dataclass",
        "field",
        "json",
        "os",
        "provider_chain_from_env",
        "re",
        "time",
        "urllib",
    ]


def test_llm_public_signatures_are_stable():
    assert str(signature(LlmProviderConfig)) == (
        "(provider_id: 'str', base_url: 'str', model: 'str', key_env: 'str', "
        "timeout_seconds: 'int' = 120, max_attempts: 'int' = 1, "
        "omit_temperature: 'bool' = False) -> None"
    )
    assert str(signature(LlmProviderChain.complete_json)) == (
        "(self, messages: 'list[dict[str, str]]', *, phase: 'str', "
        "parse: 'Callable[[dict[str, Any]], T]', validate: 'Callable[[T], Any] | None' = None, "
        "diagnostics_dir: 'str | Path | None' = None) -> 'LlmCallResult[T]'"
    )


def test_missing_api_key_error_message_and_status(monkeypatch):
    monkeypatch.delenv("MISSING_LLM_KEY", raising=False)
    config = LlmProviderConfig("test", "https://example.test/v1", "model", "MISSING_LLM_KEY")

    with pytest.raises(LlmProviderError) as exc:
        config.api_key()

    assert str(exc.value) == "Missing API key environment variable: MISSING_LLM_KEY"
    assert exc.value.status == "missing_api_key"
    assert exc.value.http_status is None
    assert exc.value.diagnostics == {}


def test_call_once_payload_headers_timeout_and_usage(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    usage = {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
    fake = FakeOpen([_openai_response(json.dumps({"ok": True}), usage=usage)])

    result = _chain(fake).complete_json(
        [{"role": "system", "content": "s"}],
        phase="proposal",
        parse=lambda payload: payload,
    )

    assert result.value == {"ok": True}
    assert result.raw_payload == {"ok": True}
    assert result.diagnostics["token_usage"] == usage
    assert fake.requests == [
        {
            "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "timeout": 17,
            "body": {
                "model": "gemini-3.6-flash",
                "messages": [{"role": "system", "content": "s"}],
                "response_format": {"type": "json_object"},
                "temperature": 0.8,
            },
            "headers": {
                "Content-type": "application/json",
                "Authorization": "Bearer gemini-test-key",
            },
        }
    ]


def test_code_fence_content_remains_invalid_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    fake = FakeOpen([_openai_response("```json\n{\"ok\": true}\n```")])

    with pytest.raises(LlmProviderError) as exc:
        _chain(fake).complete_json(
            [{"role": "system", "content": "s"}],
            phase="proposal",
            parse=lambda payload: payload,
        )

    assert str(exc.value) == "Primary provider failed and fallback is disabled"
    assert exc.value.status == "invalid_json"


def test_array_content_remains_contract_invalid(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    fake = FakeOpen([_openai_response("[1, 2]")])

    with pytest.raises(LlmProviderError) as exc:
        _chain(fake).complete_json(
            [{"role": "system", "content": "s"}],
            phase="proposal",
            parse=lambda payload: payload,
        )

    assert str(exc.value) == "Primary provider failed and fallback is disabled"
    assert exc.value.status == "contract_invalid"
