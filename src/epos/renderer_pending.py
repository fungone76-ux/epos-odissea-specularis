"""Pending renderer backend."""

from __future__ import annotations

from pathlib import Path

from .renderer_base import RenderRecord


class PendingRenderer:
    """Default: nessuna generazione. Il visual contract resta rigenerabile."""

    def render(self, prompt_package: dict[str, str], out_dir: Path) -> RenderRecord:
        return RenderRecord(status="pending", backend="pending", retryable=True)
