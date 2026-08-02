"""ComfyUI renderer backend."""

from __future__ import annotations

import copy
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .renderer_base import RenderRecord
from .renderer_common import (
    _comfy_object_names,
    _comfy_sampler_name,
    _env_first,
    _extract_loras,
    _lora_filename,
    _name_available,
    _safe_url,
)


class ComfyUIRenderer:
    """Invia un workflow API-format a ComfyUI e attende l'immagine.

    Il renderer riceve il prompt package gia' compilato e non modifica
    prompt positivo, negativo, LoRA o ordine dei layer. Il workflow atteso e'
    API-format e contiene i nodi canonici 1-9 e 20-25.
    """

    REQUIRED_NODES = {
        "1": "CheckpointLoaderSimple",
        "2": "CLIPTextEncode",
        "3": "CLIPTextEncode",
        "4": "SamplerCustom",
        "5": "KSamplerSelect",
        "6": "BasicScheduler",
        "7": "EmptyLatentImage",
        "8": "VAEDecode",
        "9": "SaveImage",
        "20": "LoraLoader",
        "21": "LoraLoader",
        "22": "LoraLoader",
        "23": "LoraLoader",
        "24": "LoraLoader",
        "25": "LoraLoader",
    }
    LORA_NODES = ("20", "21", "22", "23", "24", "25")
    FALLBACK_ZERO_LORA = "Expressive_H-000001.safetensors"

    def __init__(
        self,
        base_url: str | None = None,
        workflow_path: str | None = None,
        timeout_seconds: int | None = None,
        poll_seconds: float | None = None,
        checkpoint: str | None = None,
        steps: int | None = None,
        width: int | None = None,
        height: int | None = None,
        cfg_scale: float | None = None,
        sampler: str | None = None,
        scheduler: str | None = None,
        seed: int | None = None,
    ):
        self.base_url = (
            base_url
            or _env_first("COMFYUI_BASE_URL", "EPOS_COMFY_URL")
            or ""
        ).rstrip("/")
        self.workflow_path = workflow_path or os.environ.get("EPOS_COMFY_WORKFLOW", "")
        self.timeout_seconds = timeout_seconds or int(
            _env_first("COMFYUI_TIMEOUT_SECONDS", "EPOS_COMFY_TIMEOUT_SECONDS") or "600"
        )
        self.poll_seconds = poll_seconds or float(os.environ.get("EPOS_COMFY_POLL_SECONDS", "1"))
        self.checkpoint = checkpoint if checkpoint is not None else (
            _env_first("COMFYUI_CHECKPOINT", "EPOS_COMFY_CHECKPOINT")
            or "luna_main_model.safetensors"
        )
        self.steps = steps or int(_env_first("COMFYUI_STEPS", "EPOS_A1111_STEPS") or "24")
        self.width = width or int(_env_first("COMFYUI_WIDTH", "EPOS_COMFY_WIDTH") or "832")
        self.height = height or int(_env_first("COMFYUI_HEIGHT", "EPOS_COMFY_HEIGHT") or "1216")
        self.cfg_scale = cfg_scale or float(_env_first("COMFYUI_CFG", "EPOS_A1111_CFG") or "3.0")
        self.sampler = sampler or _env_first("COMFYUI_SAMPLER", "EPOS_A1111_SAMPLER") or "DPM++ 2M Karras"
        self.scheduler = scheduler or _env_first("COMFYUI_SCHEDULER", "EPOS_A1111_SCHEDULER") or (
            "karras" if "karras" in self.sampler.lower() else "normal"
        )
        self.seed = seed
        self._preflight_done = False
        self._preflight_diagnostics: dict[str, Any] = {}

    def render(self, prompt_package: dict[str, str], out_dir: Path) -> RenderRecord:
        started = time.monotonic()
        endpoint = "/prompt"
        diagnostics = self._base_diagnostics(endpoint)
        try:
            workflow = self._load_workflow()
            positive = prompt_package["positive"]
            loras = _extract_loras(positive)
            diagnostics["requested_loras"] = [dict(lora) for lora in loras]
            self._preflight(loras)
            seed = self._seed_from_package(prompt_package)
            self._configure_workflow(workflow, prompt_package, loras, seed)
            prompt_id = self._submit(workflow)
            diagnostics["prompt_id"] = prompt_id
            image_bytes, ext = self._wait_image(prompt_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            image_path = out_dir / f"image.{ext}"
            image_path.write_bytes(image_bytes)
            diagnostics.update(self._preflight_diagnostics)
            diagnostics.update(
                {
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "image_path": str(image_path),
                    "applied_loras": self._applied_loras(workflow),
                    "seed": seed,
                    "error": "",
                    "cause": "",
                }
            )
            return RenderRecord(
                status="complete",
                image_path=str(image_path),
                backend="comfy",
                diagnostics=diagnostics,
                retryable=False,
            )
        except Exception as exc:  # il turno non viene mai annullato dal render
            self._preflight_done = False
            diagnostics.update(self._preflight_diagnostics)
            diagnostics.update(
                {
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "error": "comfy_render_failed",
                    "cause": str(exc),
                }
            )
            if isinstance(exc, urllib.error.HTTPError):
                diagnostics["status_http"] = exc.code
            return RenderRecord(
                status="failed",
                error=f"ComfyUI render failed: {exc}",
                backend="comfy",
                diagnostics=diagnostics,
                retryable=True,
            )

    def prepare_workflow_for_test(self, prompt_package: dict[str, Any]) -> dict[str, Any]:
        workflow = self._load_workflow()
        loras = _extract_loras(prompt_package["positive"])
        self._configure_workflow(workflow, prompt_package, loras, self._seed_from_package(prompt_package))
        return workflow

    def _base_diagnostics(self, endpoint: str) -> dict[str, Any]:
        return {
            "renderer": "comfy",
            "base_url": _safe_url(self.base_url),
            "workflow_path": self.workflow_path,
            "checkpoint": self.checkpoint,
            "endpoint": endpoint,
            "prompt_id": "",
            "status_http": None,
        }

    def _load_workflow(self) -> dict[str, Any]:
        if not self.workflow_path:
            raise RuntimeError("EPOS_COMFY_WORKFLOW non configurato")
        path = Path(self.workflow_path)
        if not path.is_file():
            raise RuntimeError(f"workflow ComfyUI non trovato: {self.workflow_path}")
        workflow = json.loads(path.read_text(encoding="utf-8"))
        workflow = copy.deepcopy(workflow)
        self._validate_workflow(workflow)
        return workflow

    def _validate_workflow(self, workflow: dict[str, Any]) -> None:
        if not isinstance(workflow, dict) or "nodes" in workflow or "links" in workflow:
            raise RuntimeError("workflow ComfyUI non in API-format")
        for node_id, class_type in self.REQUIRED_NODES.items():
            node = workflow.get(node_id)
            if not isinstance(node, dict):
                raise RuntimeError(f"workflow ComfyUI senza nodo richiesto {node_id}")
            if node.get("class_type") != class_type:
                raise RuntimeError(
                    f"nodo {node_id} ComfyUI atteso {class_type}, trovato {node.get('class_type')}"
                )
            if not isinstance(node.get("inputs"), dict):
                raise RuntimeError(f"nodo {node_id} ComfyUI senza inputs")
        self._require_link(workflow, "2", "clip", "25", 1)
        self._require_link(workflow, "3", "clip", "25", 1)
        self._require_link(workflow, "4", "model", "25", 0)
        self._require_link(workflow, "6", "model", "25", 0)
        previous = "1"
        for node_id in self.LORA_NODES:
            self._require_link(workflow, node_id, "model", previous, 0)
            self._require_link(workflow, node_id, "clip", previous, 1)
            previous = node_id

    def _require_link(
        self, workflow: dict[str, Any], node_id: str, input_name: str, source_id: str, slot: int
    ) -> None:
        value = workflow[node_id]["inputs"].get(input_name)
        if value != [source_id, slot]:
            raise RuntimeError(
                f"nodo {node_id} input {input_name} deve puntare a [{source_id}, {slot}]"
            )

    def _configure_workflow(
        self,
        workflow: dict[str, Any],
        prompt_package: dict[str, Any],
        loras: list[dict[str, Any]],
        seed: int,
    ) -> None:
        if len(loras) > len(self.LORA_NODES):
            raise RuntimeError(f"troppi LoRA per il workflow ComfyUI: {len(loras)} > 6")
        workflow["1"]["inputs"]["ckpt_name"] = self.checkpoint
        workflow["2"]["inputs"]["text"] = prompt_package["positive"]
        workflow["3"]["inputs"]["text"] = prompt_package.get("negative", "")
        workflow["4"]["inputs"]["noise_seed"] = seed
        workflow["4"]["inputs"]["cfg"] = self._cfg_from_package(prompt_package)
        workflow["5"]["inputs"]["sampler_name"] = _comfy_sampler_name(
            str(prompt_package.get("sampler_name") or prompt_package.get("sampler") or self.sampler)
        )
        workflow["6"]["inputs"]["scheduler"] = str(
            prompt_package.get("scheduler") or self.scheduler
        )
        workflow["6"]["inputs"]["steps"] = int(prompt_package.get("steps") or self.steps)
        workflow["7"]["inputs"]["width"] = int(prompt_package.get("width") or self.width)
        workflow["7"]["inputs"]["height"] = int(prompt_package.get("height") or self.height)
        workflow["7"]["inputs"]["batch_size"] = 1
        for index, node_id in enumerate(self.LORA_NODES):
            inputs = workflow[node_id]["inputs"]
            if index < len(loras):
                lora = loras[index]
                inputs["lora_name"] = _lora_filename(str(lora["name"]))
                inputs["strength_model"] = float(lora["weight"])
                inputs["strength_clip"] = float(lora["weight"])
            else:
                inputs["lora_name"] = self.FALLBACK_ZERO_LORA
                inputs["strength_model"] = 0.0
                inputs["strength_clip"] = 0.0

    def _cfg_from_package(self, prompt_package: dict[str, Any]) -> float:
        return float(prompt_package.get("cfg_scale") or prompt_package.get("cfg") or self.cfg_scale)

    def _seed_from_package(self, prompt_package: dict[str, Any]) -> int:
        seed = prompt_package.get("seed", self.seed)
        if seed in (None, "", -1, "-1"):
            return random.SystemRandom().randrange(0, 2**63)
        return max(0, int(seed))

    def _applied_loras(self, workflow: dict[str, Any]) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        for node_id in self.LORA_NODES:
            inputs = workflow[node_id]["inputs"]
            applied.append(
                {
                    "node": node_id,
                    "name": inputs["lora_name"],
                    "strength_model": inputs["strength_model"],
                    "strength_clip": inputs["strength_clip"],
                }
            )
        return applied

    def _preflight(self, loras: list[dict[str, Any]]) -> None:
        if self._preflight_done:
            return
        checks: list[dict[str, Any]] = []
        info = self._get_json("/object_info", checks)
        checkpoints = _comfy_object_names(info, "CheckpointLoaderSimple", "ckpt_name")
        if self.checkpoint and not _name_available(self.checkpoint, checkpoints):
            self._preflight_diagnostics = {
                "preflight": checks,
                "checkpoint_available": False,
                "missing_checkpoint": self.checkpoint,
                "available_checkpoints": checkpoints,
            }
            raise RuntimeError(f"checkpoint ComfyUI non trovato: {self.checkpoint}")
        lora_names = [_lora_filename(str(lora["name"])) for lora in loras]
        if len(loras) < len(self.LORA_NODES):
            lora_names.append(self.FALLBACK_ZERO_LORA)
        available_loras = _comfy_object_names(info, "LoraLoader", "lora_name")
        missing_loras = [
            name for name in lora_names if not _name_available(name, available_loras)
        ]
        if missing_loras:
            self._preflight_diagnostics = {
                "preflight": checks,
                "checkpoint_available": True,
                "requested_loras": [dict(lora) for lora in loras],
                "missing_loras": missing_loras,
                "available_loras": available_loras,
            }
            raise RuntimeError("LoRA non trovati in ComfyUI: " + ", ".join(missing_loras))
        self._preflight_diagnostics = {
            "preflight": checks,
            "checkpoint_available": True,
            "requested_loras": [dict(lora) for lora in loras],
            "missing_loras": [],
        }
        self._preflight_done = True

    def _get_json(self, endpoint: str, checks: list[dict[str, Any]]) -> Any:
        started = time.monotonic()
        try:
            with urllib.request.urlopen(
                f"{self.base_url}{endpoint}", timeout=self.timeout_seconds
            ) as response:
                status = getattr(response, "status", None)
                raw = response.read().decode()
            checks.append(
                {
                    "endpoint": endpoint,
                    "status_http": status,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
            return json.loads(raw)
        except Exception as exc:
            checks.append(
                {
                    "endpoint": endpoint,
                    "status_http": exc.code if isinstance(exc, urllib.error.HTTPError) else None,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "error": str(exc),
                }
            )
            self._preflight_diagnostics = {"preflight": checks}
            raise

    def _submit(self, workflow: dict[str, Any]) -> str:
        body = json.dumps({"prompt": workflow, "client_id": str(uuid.uuid4())}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode())
        if "error" in data:
            raise RuntimeError(f"ComfyUI /prompt error: {data['error']}")
        return data["prompt_id"]

    def _wait_image(self, prompt_id: str) -> tuple[bytes, str]:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            with urllib.request.urlopen(
                f"{self.base_url}/history/{prompt_id}", timeout=self.timeout_seconds
            ) as response:
                history = json.loads(response.read().decode())
            entry = history.get(prompt_id)
            if entry and entry.get("status", {}).get("status_str") == "error":
                messages = entry.get("status", {}).get("messages") or []
                raise RuntimeError(f"ComfyUI history error: {messages}")
            if entry and entry.get("outputs"):
                for node_output in entry["outputs"].values():
                    images = node_output.get("images") or []
                    if images:
                        image = images[0]
                        params = urllib.parse.urlencode(
                            {
                                "filename": image["filename"],
                                "subfolder": image.get("subfolder", ""),
                                "type": image.get("type", "output"),
                            }
                        )
                        with urllib.request.urlopen(
                            f"{self.base_url}/view?{params}", timeout=self.timeout_seconds
                        ) as img_response:
                            raw = img_response.read()
                        ext = Path(image["filename"]).suffix.lstrip(".") or "png"
                        return raw, ext
            time.sleep(self.poll_seconds)
        raise TimeoutError(f"ComfyUI non ha prodotto l'immagine entro {self.timeout_seconds}s")
