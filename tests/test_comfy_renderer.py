import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from epos.renderers import ComfyUIRenderer


WORKFLOW = Path(__file__).resolve().parents[1] / "comfy_workflow_image.json"
FAKE_PNG = b"\x89PNGcomfy"


def _serve(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _url(server):
    return f"http://127.0.0.1:{server.server_address[1]}"


def _object_info(
    checkpoints=None,
    loras=None,
):
    checkpoints = checkpoints or ["luna_main_model.safetensors"]
    loras = loras or [
        "stsDebbie-10e.safetensors",
        "Expressive_H-000001.safetensors",
        "FantasyWorldPonyV2.safetensors",
    ]
    return {
        "CheckpointLoaderSimple": {
            "input": {"required": {"ckpt_name": [checkpoints]}}
        },
        "LoraLoader": {
            "input": {"required": {"lora_name": [loras]}}
        },
    }


def _prompt_package():
    return {
        "positive": (
            "base prompt, <lora:stsDebbie-10e:0.7>, scene, "
            "<lora:FantasyWorldPonyV2:0.40>"
        ),
        "negative": "bad image, watermark",
        "seed": 12345,
        "steps": 24,
        "width": 832,
        "height": 1216,
        "cfg_scale": 3.0,
    }


class ComfyOkStub(BaseHTTPRequestHandler):
    seen_prompt = {}
    get_counts = {"/object_info": 0}

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        type(self).get_counts[path] = type(self).get_counts.get(path, 0) + 1
        if path == "/object_info":
            body = json.dumps(_object_info()).encode()
        elif path.startswith("/history/"):
            prompt_id = path.rsplit("/", 1)[-1]
            body = json.dumps(
                {
                    prompt_id: {
                        "status": {"status_str": "success"},
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "image.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        },
                    }
                }
            ).encode()
        elif path == "/view":
            body = FAKE_PNG
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/prompt":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers["Content-Length"])
        type(self).seen_prompt = json.loads(self.rfile.read(length))
        body = json.dumps({"prompt_id": "prompt-123"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_comfy_uses_primary_url_and_fallback(monkeypatch):
    monkeypatch.setenv("COMFYUI_BASE_URL", "http://127.0.0.1:18188/")
    monkeypatch.setenv("EPOS_COMFY_URL", "http://127.0.0.1:8188")
    renderer = ComfyUIRenderer(workflow_path=str(WORKFLOW))
    assert renderer.base_url == "http://127.0.0.1:18188"

    monkeypatch.delenv("COMFYUI_BASE_URL")
    renderer = ComfyUIRenderer(workflow_path=str(WORKFLOW))
    assert renderer.base_url == "http://127.0.0.1:8188"


def test_comfy_timeout_priority(monkeypatch):
    monkeypatch.setenv("COMFYUI_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("EPOS_COMFY_TIMEOUT_SECONDS", "180")
    renderer = ComfyUIRenderer(workflow_path=str(WORKFLOW))
    assert renderer.timeout_seconds == 600

    monkeypatch.delenv("COMFYUI_TIMEOUT_SECONDS")
    renderer = ComfyUIRenderer(workflow_path=str(WORKFLOW))
    assert renderer.timeout_seconds == 180


def test_comfy_workflow_injection_preserves_prompts_and_params():
    renderer = ComfyUIRenderer(
        base_url="http://127.0.0.1:18188",
        workflow_path=str(WORKFLOW),
        checkpoint="custom_model.safetensors",
        sampler="DPM++ 2M Karras",
        scheduler="karras",
    )
    workflow = renderer.prepare_workflow_for_test(_prompt_package())

    assert workflow["1"]["inputs"]["ckpt_name"] == "custom_model.safetensors"
    assert workflow["2"]["inputs"]["text"] == _prompt_package()["positive"]
    assert workflow["3"]["inputs"]["text"] == _prompt_package()["negative"]
    assert workflow["4"]["inputs"]["noise_seed"] == 12345
    assert workflow["4"]["inputs"]["cfg"] == 3.0
    assert workflow["5"]["inputs"]["sampler_name"] == "dpmpp_2m"
    assert workflow["6"]["inputs"]["scheduler"] == "karras"
    assert workflow["6"]["inputs"]["steps"] == 24
    assert workflow["7"]["inputs"]["width"] == 832
    assert workflow["7"]["inputs"]["height"] == 1216
    assert workflow["7"]["inputs"]["batch_size"] == 1


def test_comfy_loras_order_weights_and_unused_nodes_zeroed():
    workflow = ComfyUIRenderer(
        base_url="http://127.0.0.1:18188", workflow_path=str(WORKFLOW)
    ).prepare_workflow_for_test(_prompt_package())

    assert workflow["20"]["inputs"]["lora_name"] == "stsDebbie-10e.safetensors"
    assert workflow["20"]["inputs"]["strength_model"] == 0.7
    assert workflow["20"]["inputs"]["strength_clip"] == 0.7
    assert workflow["21"]["inputs"]["lora_name"] == "FantasyWorldPonyV2.safetensors"
    assert workflow["21"]["inputs"]["strength_model"] == 0.4
    assert workflow["21"]["inputs"]["strength_clip"] == 0.4
    for node_id in ("22", "23", "24", "25"):
        assert workflow[node_id]["inputs"]["lora_name"] == "Expressive_H-000001.safetensors"
        assert workflow[node_id]["inputs"]["strength_model"] == 0.0
        assert workflow[node_id]["inputs"]["strength_clip"] == 0.0


def test_comfy_submit_history_view_saves_image(tmp_path):
    ComfyOkStub.seen_prompt = {}
    ComfyOkStub.get_counts = {"/object_info": 0}
    server = _serve(ComfyOkStub)
    try:
        renderer = ComfyUIRenderer(
            base_url=_url(server),
            workflow_path=str(WORKFLOW),
            timeout_seconds=2,
            poll_seconds=0.01,
        )
        record = renderer.render(_prompt_package(), tmp_path)
    finally:
        server.shutdown()

    assert record.status == "complete"
    assert (tmp_path / "image.png").read_bytes() == FAKE_PNG
    workflow = ComfyOkStub.seen_prompt["prompt"]
    assert workflow["2"]["inputs"]["text"] == _prompt_package()["positive"]
    assert workflow["3"]["inputs"]["text"] == _prompt_package()["negative"]
    assert record.diagnostics["renderer"] == "comfy"
    assert record.diagnostics["prompt_id"] == "prompt-123"
    assert record.diagnostics["image_path"] == str(tmp_path / "image.png")
    assert record.diagnostics["requested_loras"][0]["name"] == "stsDebbie-10e"


def test_comfy_missing_checkpoint_blocks_before_submit(tmp_path):
    class MissingCheckpoint(ComfyOkStub):
        seen_prompt = {}

        def do_GET(self):
            if self.path == "/object_info":
                body = json.dumps(_object_info(checkpoints=["other.safetensors"])).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    server = _serve(MissingCheckpoint)
    try:
        record = ComfyUIRenderer(
            base_url=_url(server), workflow_path=str(WORKFLOW), timeout_seconds=2
        ).render(_prompt_package(), tmp_path)
    finally:
        server.shutdown()

    assert record.status == "failed"
    assert "checkpoint ComfyUI non trovato" in (record.error or "")
    assert MissingCheckpoint.seen_prompt == {}
    assert record.diagnostics["missing_checkpoint"] == "luna_main_model.safetensors"


def test_comfy_missing_lora_blocks_before_submit(tmp_path):
    class MissingLora(ComfyOkStub):
        seen_prompt = {}

        def do_GET(self):
            if self.path == "/object_info":
                body = json.dumps(
                    _object_info(loras=["Expressive_H-000001.safetensors"])
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    server = _serve(MissingLora)
    try:
        record = ComfyUIRenderer(
            base_url=_url(server), workflow_path=str(WORKFLOW), timeout_seconds=2
        ).render(_prompt_package(), tmp_path)
    finally:
        server.shutdown()

    assert record.status == "failed"
    assert "LoRA non trovati in ComfyUI" in (record.error or "")
    assert MissingLora.seen_prompt == {}
    assert record.diagnostics["missing_loras"] == [
        "stsDebbie-10e.safetensors",
        "FantasyWorldPonyV2.safetensors",
    ]


def test_comfy_timeout_reports_failure(tmp_path):
    class NoOutput(ComfyOkStub):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path.startswith("/history/"):
                prompt_id = path.rsplit("/", 1)[-1]
                body = json.dumps({prompt_id: {"status": {"status_str": "running"}}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    server = _serve(NoOutput)
    try:
        record = ComfyUIRenderer(
            base_url=_url(server),
            workflow_path=str(WORKFLOW),
            timeout_seconds=0.05,
            poll_seconds=0.01,
        ).render(_prompt_package(), tmp_path)
    finally:
        server.shutdown()

    assert record.status == "failed"
    assert not (tmp_path / "image.png").exists()
    assert "ComfyUI non ha prodotto" in (record.error or "")


def test_comfy_preserves_explicit_nudity_prompt_terms():
    package = {
        "positive": "base prompt, completely nude, fully naked, no clothing, no armor",
        "negative": "bad image, bikini, swimsuit, clothing",
        "seed": 7,
    }
    workflow = ComfyUIRenderer(
        base_url="http://127.0.0.1:18188",
        workflow_path=str(WORKFLOW),
    ).prepare_workflow_for_test(package)

    assert workflow["2"]["inputs"]["text"] == package["positive"]
    assert workflow["3"]["inputs"]["text"] == package["negative"]
