"""LLM provider data contracts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from .llm_errors import LlmProviderError


T = TypeVar("T")


@dataclass(frozen=True)
class LlmProviderConfig:
    provider_id: str
    base_url: str
    model: str
    key_env: str
    timeout_seconds: int = 120
    max_attempts: int = 1
    omit_temperature: bool = False

    @property
    def complete(self) -> bool:
        return bool(self.provider_id and self.base_url and self.model and self.key_env)

    def api_key(self) -> str:
        value = os.environ.get(self.key_env, "")
        if not value:
            raise LlmProviderError(
                f"Missing API key environment variable: {self.key_env}",
                status="missing_api_key",
            )
        return value


@dataclass
class LlmCallResult(Generic[T]):
    value: T
    raw_payload: dict[str, Any]
    diagnostics: dict[str, Any] = field(default_factory=dict)
