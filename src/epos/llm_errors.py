"""LLM provider exceptions."""

from __future__ import annotations

from typing import Any


class LlmProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        status: str = "error",
        http_status: int | None = None,
        diagnostics: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.http_status = http_status
        self.diagnostics = diagnostics or {}
