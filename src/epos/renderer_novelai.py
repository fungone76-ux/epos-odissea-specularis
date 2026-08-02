"""NovelAI renderer backend."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from .renderer_base import RenderRecord


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
