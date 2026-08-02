"""Shared renderer contracts and result records."""

from __future__ import annotations

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
