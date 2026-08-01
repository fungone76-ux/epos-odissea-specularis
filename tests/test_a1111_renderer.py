import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from epos.renderers import A1111Renderer, ComfyUIRenderer, renderer_from_env


FAKE_PNG = base64.b64encode(b"\x89PNGforge").decode()


def _serve(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _url(server):
    return f"http://127.0.0.1:{server.server_address[1]}"


class ForgeOkStub(BaseHTTPRequestHandler):
    seen_posts = []
    get_counts = {"/sdapi/v1/options": 0, "/sdapi/v1/sd-models": 0, "/sdapi/v1/loras": 0}

    def do_GET(self):
        type(self).get_counts[self.path] = type(self).get_counts.get(self.path, 0) + 1
        if self.path == "/sdapi/v1/options":
            body = json.dumps({"sd_model_checkpoint": "luna_main_model.safetensors"}).encode()
        elif self.path == "/sdapi/v1/sd-models":
            body = json.dumps([{"title": "luna_main_model.safetensors"}]).encode()
        elif self.path == "/sdapi/v1/loras":
            body = json.dumps(
                [
                    {"name": "stsDebbie-10e", "alias": "stsDebbie-10e"},
                    {"name": "Expressive_H-000001", "alias": "Expressive_H-000001"},
                    {"name": "FantasyWorldPonyV2", "alias": "FantasyWorldPonyV2"},
                ]
            ).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        type(self).seen_posts.append(json.loads(self.rfile.read(length)))
        body = json.dumps({"images": [FAKE_PNG]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _prompt_package():
    return {
        "positive": "base prompt, <lora:stsDebbie-10e:0.7>, scene visual",
        "negative": "bad image",
    }


def test_renderer_selection_and_url_from_environment(monkeypatch):
    monkeypatch.setenv("EPOS_RENDER_MODE", "a1111")
    monkeypatch.setenv("A1111_BASE_URL", "http://127.0.0.1:17860")
    monkeypatch.setenv("A1111_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("A1111_CHECKPOINT", "luna_main_model.safetensors")
    renderer = renderer_from_env()
    assert isinstance(renderer, A1111Renderer)
    assert renderer.base_url == "http://127.0.0.1:17860"
    assert renderer.timeout_seconds == 600
    assert renderer.checkpoint == "luna_main_model.safetensors"


def test_txt2img_payload_preserves_prompts_and_selects_checkpoint(tmp_path):
    ForgeOkStub.seen_posts = []
    ForgeOkStub.get_counts = {"/sdapi/v1/options": 0, "/sdapi/v1/sd-models": 0, "/sdapi/v1/loras": 0}
    server = _serve(ForgeOkStub)
    try:
        renderer = A1111Renderer(base_url=_url(server), steps=24, width=832, height=832, cfg_scale=3.0)
        record = renderer.render(_prompt_package(), tmp_path)
    finally:
        server.shutdown()

    assert record.status == "complete"
    payload = ForgeOkStub.seen_posts[0]
    assert payload["prompt"] == _prompt_package()["positive"]
    assert payload["negative_prompt"] == _prompt_package()["negative"]
    assert payload["seed"] == -1
    assert payload["steps"] == 24
    assert payload["width"] == 832
    assert payload["height"] == 832
    assert payload["cfg_scale"] == 3.0
    assert payload["override_settings"]["sd_model_checkpoint"] == "luna_main_model.safetensors"
    assert payload["override_settings_restore_afterwards"] is True


def test_decodes_base64_and_saves_png(tmp_path):
    ForgeOkStub.seen_posts = []
    server = _serve(ForgeOkStub)
    try:
        record = A1111Renderer(base_url=_url(server)).render(_prompt_package(), tmp_path)
    finally:
        server.shutdown()

    assert record.status == "complete"
    assert (tmp_path / "image.png").read_bytes() == b"\x89PNGforge"
    assert record.diagnostics["image_path"] == str(tmp_path / "image.png")
    assert record.diagnostics["base_url"].startswith("http://127.0.0.1:")
    assert record.diagnostics["endpoint"] == "/sdapi/v1/txt2img"


def test_timeout_reports_failure_without_fake_image(tmp_path):
    class SlowStub(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(0.2)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = _serve(SlowStub)
    try:
        record = A1111Renderer(base_url=_url(server), timeout_seconds=0.01).render(
            _prompt_package(), tmp_path
        )
    finally:
        server.shutdown()

    assert record.status == "failed"
    assert not (tmp_path / "image.png").exists()
    assert "timed out" in (record.error or "").lower() or "timeout" in json.dumps(record.diagnostics).lower()


def test_invalid_http_response_reports_failure(tmp_path):
    class InvalidPostStub(ForgeOkStub):
        def do_POST(self):
            body = b"{not json"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = _serve(InvalidPostStub)
    try:
        record = A1111Renderer(base_url=_url(server)).render(_prompt_package(), tmp_path)
    finally:
        server.shutdown()

    assert record.status == "failed"
    assert not (tmp_path / "image.png").exists()
    assert record.diagnostics["error"] == "a1111_render_failed"


def test_missing_checkpoint_blocks_render_before_txt2img(tmp_path):
    class MissingModelStub(ForgeOkStub):
        seen_posts = []

        def do_GET(self):
            if self.path == "/sdapi/v1/options":
                body = json.dumps({}).encode()
            elif self.path == "/sdapi/v1/sd-models":
                body = json.dumps([{"title": "other_model.safetensors"}]).encode()
            elif self.path == "/sdapi/v1/loras":
                body = json.dumps([]).encode()
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = _serve(MissingModelStub)
    try:
        record = A1111Renderer(base_url=_url(server)).render(_prompt_package(), tmp_path)
    finally:
        server.shutdown()

    assert record.status == "failed"
    assert "checkpoint A1111 non trovato" in (record.error or "")
    assert MissingModelStub.seen_posts == []
    assert record.diagnostics["missing_checkpoint"] == "luna_main_model.safetensors"


def test_missing_lora_blocks_render_before_txt2img(tmp_path):
    class MissingLoraStub(ForgeOkStub):
        seen_posts = []

        def do_GET(self):
            if self.path == "/sdapi/v1/options":
                body = json.dumps({}).encode()
            elif self.path == "/sdapi/v1/sd-models":
                body = json.dumps([{"title": "luna_main_model.safetensors"}]).encode()
            elif self.path == "/sdapi/v1/loras":
                body = json.dumps([{"name": "Expressive_H-000001"}]).encode()
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = _serve(MissingLoraStub)
    try:
        record = A1111Renderer(base_url=_url(server)).render(_prompt_package(), tmp_path)
    finally:
        server.shutdown()

    assert record.status == "failed"
    assert MissingLoraStub.seen_posts == []
    assert not (tmp_path / "image.png").exists()
    assert "stsDebbie-10e" in (record.error or "")
    assert record.diagnostics["missing_loras"] == ["stsDebbie-10e"]


def test_preflight_reused_for_multiple_renders(tmp_path):
    ForgeOkStub.seen_posts = []
    ForgeOkStub.get_counts = {"/sdapi/v1/options": 0, "/sdapi/v1/sd-models": 0, "/sdapi/v1/loras": 0}
    server = _serve(ForgeOkStub)
    try:
        renderer = A1111Renderer(base_url=_url(server))
        first = renderer.render(_prompt_package(), tmp_path / "one")
        second = renderer.render(_prompt_package(), tmp_path / "two")
    finally:
        server.shutdown()

    assert first.status == "complete"
    assert second.status == "complete"
    assert ForgeOkStub.get_counts == {
        "/sdapi/v1/options": 1,
        "/sdapi/v1/sd-models": 1,
        "/sdapi/v1/loras": 1,
    }
    assert len(ForgeOkStub.seen_posts) == 2


def test_comfy_renderer_still_selectable(monkeypatch):
    monkeypatch.setenv("EPOS_RENDER_MODE", "comfy")
    assert isinstance(renderer_from_env(), ComfyUIRenderer)
