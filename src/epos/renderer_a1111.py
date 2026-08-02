"""Automatic1111 renderer backend."""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .renderer_base import RenderRecord
from .renderer_common import (
    _checkpoint_available,
    _env_first,
    _missing_loras,
    _safe_url,
)


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
