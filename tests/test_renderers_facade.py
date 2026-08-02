import json

from epos.renderers import (
    A1111Renderer,
    ComfyUIRenderer,
    NovelAIRenderer,
    PendingRenderer,
    RenderRecord,
    Renderer,
    _checkpoint_available,
    _comfy_object_names,
    _comfy_sampler_name,
    _env_first,
    _extract_loras,
    _lora_filename,
    _missing_loras,
    _name_available,
    _safe_url,
    renderer_from_env,
)


def test_renderers_facade_reexports_existing_public_and_helper_symbols():
    assert RenderRecord(status="pending").to_dict()["backend"] == "pending"
    assert Renderer is not None
    assert PendingRenderer().render({"positive": "x"}, None).backend == "pending"
    assert A1111Renderer is not None
    assert ComfyUIRenderer is not None
    assert NovelAIRenderer is not None
    assert renderer_from_env is not None
    assert _env_first("__EPOS_TEST_MISSING_ENV__") is None
    assert _safe_url("http://user:secret@example.test:8188/path?token=x") == (
        "http://example.test:8188/path"
    )
    assert _extract_loras("<lora:demo:0.7>") == [{"name": "demo", "weight": 0.7}]
    assert _lora_filename("demo") == "demo.safetensors"
    assert _name_available("demo.safetensors", ["models/demo.safetensors"])
    assert _comfy_sampler_name("DPM++ 2M Karras") == "dpmpp_2m"
    assert _checkpoint_available([{"title": "demo.safetensors"}], "demo")
    assert _missing_loras(["demo"], [{"name": "other"}]) == ["demo"]
    assert _comfy_object_names(
        {"Node": {"input": {"required": {"name": [["one", "two"]]}}}},
        "Node",
        "name",
    ) == ["one", "two"]


def test_direct_renderer_modules_import_without_network():
    import epos.renderer_a1111
    import epos.renderer_base
    import epos.renderer_comfyui
    import epos.renderer_common
    import epos.renderer_novelai
    import epos.renderer_pending

    assert epos.renderer_base.RenderRecord is RenderRecord
    assert epos.renderer_pending.PendingRenderer is PendingRenderer
    assert epos.renderer_comfyui.ComfyUIRenderer is ComfyUIRenderer
    assert epos.renderer_a1111.A1111Renderer is A1111Renderer
    assert epos.renderer_novelai.NovelAIRenderer is NovelAIRenderer


def test_novelai_renderer_payload_and_zip_output(tmp_path, monkeypatch):
    calls = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"zip-bytes"

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return Response()

    monkeypatch.setattr("epos.renderer_novelai.urllib.request.urlopen", fake_urlopen)
    renderer = NovelAIRenderer(api_key="secret-token", model="nai-test", timeout_seconds=7)

    record = renderer.render(
        {"positive": "heroic portrait", "negative": "bad image"},
        tmp_path,
    )

    assert record.status == "complete"
    assert record.backend == "novelai"
    assert record.retryable is False
    assert (tmp_path / "image.zip").read_bytes() == b"zip-bytes"
    request, timeout = calls[0]
    assert request.full_url == NovelAIRenderer.API_URL
    assert timeout == 7
    assert request.headers["Content-type"] == "application/json"
    assert request.headers["Authorization"] == "Bearer secret-token"
    payload = json.loads(request.data.decode())
    assert payload["input"] == "heroic portrait"
    assert payload["model"] == "nai-test"
    assert payload["parameters"]["negative_prompt"] == "bad image"


def test_novelai_missing_api_key_fails_without_network(tmp_path, monkeypatch):
    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("NovelAI should not call the network without an API key")

    monkeypatch.setattr("epos.renderer_novelai.urllib.request.urlopen", fail_urlopen)
    record = NovelAIRenderer(api_key="").render({"positive": "x"}, tmp_path)

    assert record.status == "failed"
    assert record.backend == "novelai"
    assert record.retryable is True
    assert "EPOS_NOVELAI_API_KEY non configurata" in (record.error or "")
