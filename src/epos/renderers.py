"""Renderer facade: public compatibility layer for image backends.

Implementazioni:
- PendingRenderer  - default: non genera nulla, segna il turno come pending
- ComfyUIRenderer  - workflow locale/remoto via API /prompt
- A1111Renderer    - Automatic1111 WebUI locale via /sdapi/v1/txt2img
- NovelAIRenderer  - API cloud NovelAI (nessuna GPU richiesta)

Un fallimento di rendering non annulla mai il turno: il record viene
salvato e :rerender puo riprovare senza richiamare il Game Master.
"""

from __future__ import annotations

import os

from .renderer_a1111 import A1111Renderer
from .renderer_base import RenderRecord, Renderer
from .renderer_comfyui import ComfyUIRenderer
from .renderer_common import (
    _checkpoint_available,
    _comfy_object_names,
    _comfy_sampler_name,
    _env_first,
    _extract_loras,
    _lora_filename,
    _missing_loras,
    _name_available,
    _safe_url,
)
from .renderer_novelai import NovelAIRenderer
from .renderer_pending import PendingRenderer


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


__all__ = [
    "A1111Renderer",
    "ComfyUIRenderer",
    "NovelAIRenderer",
    "PendingRenderer",
    "RenderRecord",
    "Renderer",
    "_checkpoint_available",
    "_comfy_object_names",
    "_comfy_sampler_name",
    "_env_first",
    "_extract_loras",
    "_lora_filename",
    "_missing_loras",
    "_name_available",
    "_safe_url",
    "renderer_from_env",
]
