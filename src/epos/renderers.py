"""Renderer: il visual contract Ã¨ indipendente dal motore di immagini.

Implementazioni:
- PendingRenderer  â€” default: non genera nulla, segna il turno come pending
- ComfyUIRenderer  â€” workflow locale/remoto via API /prompt
- A1111Renderer    â€” Automatic1111 WebUI locale via /sdapi/v1/txt2img
- NovelAIRenderer  â€” API cloud NovelAI (nessuna GPU richiesta)

Un fallimento di rendering non annulla mai il turno: il record viene
salvato e :rerender puÃ² riprovare senza richiamare il Game Master.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class RenderRecord:
    status: str  # pending | complete | failed
    image_path: str | None = None
    error: str | None = None
    backend: str = "pending"
    warning: str | None = None  # es. LoRA mancanti: il render riesce comunque
    diagnostics: dict[str, Any] = field(default_factory=dict)
    retryable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "image_path": self.image_path,
            "error": self.error,
            "backend": self.backend,
            "warning": self.warning,
            "diagnostics": dict(self.diagnostics),
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RenderRecord":
        return cls(
            status=data["status"],
            image_path=data.get("image_path"),
            error=data.get("error"),
            backend=data.get("backend", "pending"),
            warning=data.get("warning"),
            diagnostics=dict(data.get("diagnostics", {})),
            retryable=bool(data.get("retryable", data.get("status") != "complete")),
        )


class Renderer(Protocol):
    def render(self, prompt_package: dict[str, str], out_dir: Path) -> RenderRecord: ...


class PendingRenderer:
    """Default: nessuna generazione. Il visual contract resta rigenerabile."""

    def render(self, prompt_package: dict[str, str], out_dir: Path) -> RenderRecord:
        return RenderRecord(status="pending", backend="pending", retryable=True)


# ---------------------------------------------------------------------------
# ComfyUI
# ---------------------------------------------------------------------------


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
        self.width = width or int(_env_first("COMFYUI_WIDTH", "EPOS_A1111_WIDTH") or "832")
        self.height = height or int(_env_first("COMFYUI_HEIGHT", "EPOS_A1111_HEIGHT") or "1216")
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


# ---------------------------------------------------------------------------
# NovelAI
# ---------------------------------------------------------------------------


class NovelAIRenderer:
    """Renderer cloud NovelAI. Config: EPOS_NOVELAI_API_KEY, EPOS_NOVELAI_MODEL."""

    API_URL = "https://image.novelai.net/ai/generate-image"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 120,
    ):
        self.api_key = api_key or os.environ.get("EPOS_NOVELAI_API_KEY", "")
        self.model = model or os.environ.get("EPOS_NOVELAI_MODEL", "nai-diffusion-4-5-full")
        self.timeout_seconds = timeout_seconds

    def render(self, prompt_package: dict[str, str], out_dir: Path) -> RenderRecord:
        try:
            if not self.api_key:
                raise RuntimeError("EPOS_NOVELAI_API_KEY non configurata")
            body = json.dumps(
                {
                    "input": prompt_package["positive"],
                    "model": self.model,
                    "action": "generate",
                    "parameters": {
                        "width": 832,
                        "height": 1216,
                        "scale": 6,
                        "sampler": "k_euler_ancestral",
                        "steps": 28,
                        "n_samples": 1,
                        "negative_prompt": prompt_package.get("negative", ""),
                    },
                }
            ).encode()
            request = urllib.request.Request(
                self.API_URL,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
            out_dir.mkdir(parents=True, exist_ok=True)
            image_path = out_dir / "image.zip"  # NovelAI risponde con uno zip
            image_path.write_bytes(raw)
            return RenderRecord(
                status="complete", image_path=str(image_path), backend="novelai", retryable=False
            )
        except Exception as exc:
            return RenderRecord(status="failed", error=str(exc), backend="novelai", retryable=True)


# ---------------------------------------------------------------------------
# Automatic1111 (Stable Diffusion WebUI, --api)
# ---------------------------------------------------------------------------


class A1111Renderer:
    """Renderer per AUTOMATIC1111/Forge WebUI via API /sdapi/v1.

    Il renderer riceve il prompt package gia' compilato e non modifica
    prompt positivo, negativo, LoRA o ordine dei layer.
    """

    def __init__(
        self,
        base_url: str | None = None,
        steps: int | None = None,
        width: int | None = None,
        height: int | None = None,
        cfg_scale: float | None = None,
        sampler: str | None = None,
        scheduler: str | None = None,
        timeout_seconds: int | None = None,
        checkpoint: str | None = None,
    ):
        self.base_url = (
            base_url
            or _env_first("A1111_BASE_URL", "EPOS_A1111_URL")
            or "http://127.0.0.1:17860"
        ).rstrip("/")
        self.steps = steps or int(_env_first("A1111_STEPS", "EPOS_A1111_STEPS") or "28")
        self.width = width or int(_env_first("A1111_WIDTH", "EPOS_A1111_WIDTH") or "832")
        self.height = height or int(_env_first("A1111_HEIGHT", "EPOS_A1111_HEIGHT") or "1216")
        self.cfg_scale = cfg_scale or float(_env_first("A1111_CFG", "EPOS_A1111_CFG") or "6.0")
        self.sampler = sampler or _env_first("A1111_SAMPLER", "EPOS_A1111_SAMPLER") or "DPM++ 2M Karras"
        self.scheduler = scheduler or _env_first("A1111_SCHEDULER", "EPOS_A1111_SCHEDULER")
        self.timeout_seconds = timeout_seconds or int(
            _env_first("A1111_TIMEOUT_SECONDS", "EPOS_A1111_TIMEOUT_SECONDS") or "600"
        )
        self.checkpoint = checkpoint if checkpoint is not None else (
            _env_first("A1111_CHECKPOINT", "EPOS_A1111_CHECKPOINT")
            or "luna_main_model.safetensors"
        )
        self._preflight_done = False
        self._preflight_warning: str | None = None
        self._preflight_diagnostics: dict[str, Any] = {}

    def render(self, prompt_package: dict[str, str], out_dir: Path) -> RenderRecord:
        started = time.monotonic()
        endpoint = "/sdapi/v1/txt2img"
        diagnostics = self._base_diagnostics(endpoint)
        try:
            warning = self._preflight(prompt_package["positive"])
            payload: dict[str, Any] = {
                "prompt": prompt_package["positive"],
                "negative_prompt": prompt_package.get("negative", ""),
                "seed": prompt_package.get("seed", -1),
                "steps": self.steps,
                "width": self.width,
                "height": self.height,
                "cfg_scale": self.cfg_scale,
                "sampler_name": self.sampler,
                "batch_size": 1,
                "n_iter": 1,
                "send_images": True,
                "save_images": False,
                "override_settings": (
                    {"sd_model_checkpoint": self.checkpoint} if self.checkpoint else {}
                ),
                "override_settings_restore_afterwards": True,
            }
            if self.scheduler:
                payload["scheduler"] = self.scheduler
            body = json.dumps(payload).encode()
            request = urllib.request.Request(
                f"{self.base_url}{endpoint}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                diagnostics["status_http"] = getattr(response, "status", None)
                data = json.loads(response.read().decode())
            images = data.get("images") or []
            if not images:
                raise RuntimeError("A1111 non ha restituito immagini")
            out_dir.mkdir(parents=True, exist_ok=True)
            image_path = out_dir / "image.png"
            image_path.write_bytes(base64.b64decode(images[0]))
            diagnostics.update(self._preflight_diagnostics)
            diagnostics.update(
                {
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "image_path": str(image_path),
                    "error": "",
                    "cause": "",
                }
            )
            return RenderRecord(
                status="complete",
                image_path=str(image_path),
                backend="a1111",
                warning=warning,
                diagnostics=diagnostics,
                retryable=False,
            )
        except Exception as exc:  # il turno non viene mai annullato dal render
            self._preflight_done = False
            diagnostics.update(self._preflight_diagnostics)
            diagnostics.update(
                {
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "error": "a1111_render_failed",
                    "cause": str(exc),
                }
            )
            if isinstance(exc, urllib.error.HTTPError):
                diagnostics["status_http"] = exc.code
            return RenderRecord(
                status="failed",
                error=f"A1111 render failed: {exc}",
                backend="a1111",
                diagnostics=diagnostics,
                retryable=True,
            )

    def invalidate_preflight(self) -> None:
        self._preflight_done = False

    def _base_diagnostics(self, endpoint: str) -> dict[str, Any]:
        return {
            "renderer": "a1111",
            "base_url": _safe_url(self.base_url),
            "endpoint": endpoint,
            "checkpoint": self.checkpoint,
            "status_http": None,
        }

    def _preflight(self, positive: str) -> str | None:
        if self._preflight_done:
            return self._preflight_warning
        checks: list[dict[str, Any]] = []
        self._get_json("/sdapi/v1/options", checks)
        models = self._get_json("/sdapi/v1/sd-models", checks)
        if self.checkpoint and not _checkpoint_available(models, self.checkpoint):
            self._preflight_diagnostics = {
                "preflight": checks,
                "checkpoint_available": False,
                "missing_checkpoint": self.checkpoint,
            }
            raise RuntimeError(f"checkpoint A1111 non trovato: {self.checkpoint}")
        loras = self._get_json("/sdapi/v1/loras", checks)
        wanted = re.findall(r"<lora:([^:>]+)", positive)
        missing = _missing_loras(wanted, loras)
        warning = None
        if missing:
            self._preflight_diagnostics = {
                "preflight": checks,
                "checkpoint_available": True,
                "requested_loras": wanted,
                "missing_loras": missing,
            }
            raise RuntimeError(
                "LoRA non trovati in A1111 (cartella models/Lora): "
                + ", ".join(missing)
            )
        self._preflight_warning = warning
        self._preflight_diagnostics = {
            "preflight": checks,
            "checkpoint_available": True,
            "requested_loras": wanted,
            "missing_loras": missing,
        }
        self._preflight_done = True
        return warning

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


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _safe_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    netloc = host
    if parsed.port is not None:
        netloc += f":{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _extract_loras(positive: str) -> list[dict[str, Any]]:
    loras: list[dict[str, Any]] = []
    pattern = re.compile(r"<lora:([^:>]+):([+-]?(?:\d+(?:\.\d*)?|\.\d+))>", re.IGNORECASE)
    for match in pattern.finditer(positive):
        loras.append({"name": match.group(1), "weight": float(match.group(2))})
    return loras


def _lora_filename(name: str) -> str:
    return name if name.lower().endswith(".safetensors") else f"{name}.safetensors"


def _name_available(name: str, available: list[str]) -> bool:
    target = name.replace("\\", "/").split("/")[-1].lower()
    target_stem = target.removesuffix(".safetensors").removesuffix(".ckpt")
    for item in available:
        clean = str(item).replace("\\", "/").split("/")[-1].lower()
        stem = clean.removesuffix(".safetensors").removesuffix(".ckpt")
        if target == clean or target_stem == stem:
            return True
    return False


def _comfy_object_names(info: Any, class_type: str, input_name: str) -> list[str]:
    node_info = info.get(class_type, {}) if isinstance(info, dict) else {}
    inputs = node_info.get("input", {}) if isinstance(node_info, dict) else {}
    required = inputs.get("required", {}) if isinstance(inputs, dict) else {}
    optional = inputs.get("optional", {}) if isinstance(inputs, dict) else {}
    spec = required.get(input_name, optional.get(input_name, []))
    if isinstance(spec, list) and spec and isinstance(spec[0], list):
        return [str(item) for item in spec[0]]
    if isinstance(spec, tuple) and spec and isinstance(spec[0], list):
        return [str(item) for item in spec[0]]
    return []


def _comfy_sampler_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    aliases = {
        "dpm 2m karras": "dpmpp_2m",
        "dpmpp 2m karras": "dpmpp_2m",
        "dpm 2m": "dpmpp_2m",
        "dpmpp 2m": "dpmpp_2m",
        "euler a": "euler_ancestral",
        "euler ancestral": "euler_ancestral",
    }
    if normalized in aliases:
        return aliases[normalized]
    return normalized.replace(" ", "_")


def _checkpoint_available(models: Any, checkpoint: str) -> bool:
    target = checkpoint.lower()
    target_stem = target.removesuffix(".safetensors").removesuffix(".ckpt")
    for model in models or []:
        values = {
            str(model.get("title", "")),
            str(model.get("model_name", "")),
            str(model.get("filename", "")),
            str(model.get("name", "")),
        }
        lowered = {value.replace("\\", "/").split("/")[-1].lower() for value in values}
        stems = {value.removesuffix(".safetensors").removesuffix(".ckpt") for value in lowered}
        if target in lowered or target_stem in stems:
            return True
    return False


def _missing_loras(wanted: list[str], entries: Any) -> list[str]:
    available: set[str] = set()
    for entry in entries or []:
        for key in ("name", "alias", "path"):
            value = str(entry.get(key, "")).replace("\\", "/").split("/")[-1].lower()
            if value:
                available.add(value)
                available.add(value.removesuffix(".safetensors"))
    missing: list[str] = []
    for lora in wanted:
        norm = lora.lower().removesuffix(".safetensors")
        if norm not in available:
            missing.append(lora)
    return missing


def renderer_from_env() -> Renderer:
    """Selezione del backend via EPOS_RENDER_MODE: pending | comfy | a1111 | novelai."""

    mode = (
        os.environ.get("EPOS_RENDER_MODE")
        or os.environ.get("RENDER_MODE")
        or os.environ.get("EVENT_RENDER_MODE")
        or os.environ.get("IMAGE_PROVIDER")
        or "pending"
    ).strip().lower()
    if mode == "comfy":
        return ComfyUIRenderer()
    if mode == "a1111":
        return A1111Renderer()
    if mode == "novelai":
        return NovelAIRenderer()
    return PendingRenderer()

