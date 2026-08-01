"""OpenAI-compatible LLM provider chain with primary/secondary fallback."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar


T = TypeVar("T")


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip().lower())
    return safe or "provider"


def _sanitize_sensitive_text(text: str) -> str:
    sanitized = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s\"']+",
        r"\1[REDACTED]",
        text,
    )
    sanitized = re.sub(
        r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,\"']+",
        r"\1[REDACTED]",
        sanitized,
    )
    return sanitized


def _sanitize_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"authorization", "api_key", "apikey", "token"}:
                clean[key] = "[REDACTED]"
            else:
                clean[key] = _sanitize_sensitive_data(item)
        return clean
    if isinstance(value, list):
        return [_sanitize_sensitive_data(item) for item in value]
    if isinstance(value, str):
        return _sanitize_sensitive_text(value)
    return value


def _validation_error(
    code: str,
    path: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "path": path,
        "message": message,
        "details": details or {},
    }


def _validation_report(
    valid: bool,
    *,
    phase: str,
    stage: str = "semantic",
    errors: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    problems: list[str] | None = None,
) -> dict[str, Any]:
    errors = errors or []
    problems = problems if problems is not None else [str(e.get("message", "")) for e in errors]
    return {
        "valid": valid,
        "phase": phase,
        "validation_stage": stage,
        "validation_reason": "" if valid else (errors[0].get("code", "semantic_contract_rejected") if errors else "semantic_contract_rejected"),
        "errors": errors,
        "warnings": warnings or [],
        "problems": problems,
    }


def _normalize_validation_result(result: Any, *, phase: str) -> dict[str, Any]:
    if result is None:
        return _validation_report(True, phase=phase)
    if hasattr(result, "to_dict"):
        data = result.to_dict(stage="semantic", phase=phase)
        errors = list(data.get("errors", []))
        return _validation_report(
            bool(data.get("valid", not errors)),
            phase=phase,
            stage=str(data.get("validation_stage", "semantic")),
            errors=errors,
            warnings=list(data.get("warnings", [])),
            problems=list(data.get("problems", [])),
        )
    if isinstance(result, dict) and "valid" in result:
        errors = list(result.get("errors", []))
        return _validation_report(
            bool(result.get("valid")),
            phase=phase,
            stage=str(result.get("validation_stage", "semantic")),
            errors=errors,
            warnings=list(result.get("warnings", [])),
            problems=list(result.get("problems", [])),
        )
    problems = [str(problem) for problem in result] if isinstance(result, list) else [str(result)]
    if not problems:
        return _validation_report(True, phase=phase)
    errors = [
        _validation_error(_code_for_problem(problem), _path_for_problem(problem), problem)
        for problem in problems
    ]
    return _validation_report(False, phase=phase, errors=errors, problems=problems)


def _semantic_retry_messages(
    messages: list[dict[str, str]], report: dict[str, Any]
) -> list[dict[str, str]]:
    problems = [str(problem) for problem in report.get("problems", [])]
    text = " ".join(problems).casefold()
    note = (
        "\n\nCORREZIONE OBBLIGATORIA PER IL RETRY:\n"
        "- Mantieni narrative_policy, consenso, outfit e stato relazionale "
        "dello snapshot; non cambiare tono casualmente fra tentativi.\n"
        "- Non parlare per il player e non inventare dialogue speaker=player.\n"
        "- Non inventare una nuova azione, strategia, intenzione o obiettivo "
        "del player.\n"
        "- Non trasformare risveglio, osservazione, ascolto, attesa o immobilita "
        "in prova sociale, seduzione, attacco, esplorazione o inganno.\n"
        "- Mantieni il momento visuale esatto richiesto dal player e le sue "
        "conseguenze immediate.\n"
        "- Nudita da sola non equivale a sensualita, intimacy_detected o consenso.\n"
        "Errori validazione precedenti:\n- "
        + "\n- ".join(problems)
    )
    if any(alias in text for alias in ("ulisse", "odysseus", "odisseo")):
        note += (
            '\n- Nei campi strutturali che rappresentano entity ID usa sempre "player" '
            "per il protagonista.\n"
            '- Non usare "ulisse", "odysseus" o "odisseo" come ID interno.\n'
            '- Lascia "Ulisse" solo nella prosa narrativa, nei testi liberi e nei '
            "dialoghi naturali."
        )
    retry_messages = list(messages)
    if retry_messages and retry_messages[-1].get("role") == "user":
        retry_messages[-1] = {
            **retry_messages[-1],
            "content": retry_messages[-1].get("content", "") + note,
        }
    else:
        retry_messages.append({"role": "user", "content": note})
    return retry_messages


def _code_for_problem(problem: str) -> str:
    text = problem.lower()
    if "testimone assente" in text:
        return "invalid_memory_witness"
    if "personaggio visibile ma assente" in text:
        return "visible_character_not_present"
    if "target inesistente" in text or "npc inesistente" in text:
        return "unknown_npc_id"
    if "destinazione sconosciuta" in text:
        return "invalid_location_reference"
    if "visual obbligatorio" in text or "senza" in text or "mancant" in text:
        return "missing_required_field"
    return "semantic_contract_rejected"


def _path_for_problem(problem: str) -> str:
    text = problem.lower()
    if "memory_event" in text:
        return "memory_events"
    if "visual:" in text:
        return "visual.visible_characters"
    if "target" in text:
        return "target_ids"
    return ""


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


def provider_chain_from_env(
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    timeout_seconds: int | None = None,
    omit_temperature: bool = False,
) -> "LlmProviderChain":
    timeout = timeout_seconds or int(os.environ.get("EPOS_LLM_TIMEOUT_SECONDS", "120"))
    has_primary = any(name in os.environ for name in (
        "EPOS_PRIMARY_LLM_PROVIDER",
        "EPOS_PRIMARY_LLM_BASE_URL",
        "EPOS_PRIMARY_LLM_MODEL",
        "EPOS_PRIMARY_LLM_KEY_ENV",
    ))
    if has_primary:
        primary = LlmProviderConfig(
            provider_id=os.environ.get("EPOS_PRIMARY_LLM_PROVIDER", "zai"),
            base_url=(base_url or os.environ.get("EPOS_PRIMARY_LLM_BASE_URL", "")).rstrip("/"),
            model=model or os.environ.get("EPOS_PRIMARY_LLM_MODEL", ""),
            key_env=os.environ.get("EPOS_PRIMARY_LLM_KEY_ENV", "ZAI_API_KEY"),
            timeout_seconds=timeout,
            max_attempts=int(os.environ.get("EPOS_PRIMARY_LLM_MAX_ATTEMPTS", "2")),
            omit_temperature=omit_temperature,
        )
    else:
        key_env = os.environ.get("EPOS_LLM_KEY_ENV", "EPOS_LLM_API_KEY")
        if api_key is not None:
            os.environ.setdefault(key_env, api_key)
        primary = LlmProviderConfig(
            provider_id=os.environ.get("EPOS_LLM_PROVIDER", "legacy"),
            base_url=(base_url or os.environ.get("EPOS_LLM_BASE_URL", "")).rstrip("/"),
            model=model or os.environ.get("EPOS_LLM_MODEL", ""),
            key_env=key_env,
            timeout_seconds=timeout,
            max_attempts=int(os.environ.get("EPOS_LLM_MAX_ATTEMPTS", "2")),
            omit_temperature=omit_temperature,
        )

    if not primary.base_url or not primary.model:
        raise LlmProviderError(
            "Configurazione live mancante: EPOS_LLM_BASE_URL e EPOS_LLM_MODEL richieste",
            status="incomplete_primary_config",
        )
    primary.api_key()

    secondary: LlmProviderConfig | None = None
    fallback_enabled = os.environ.get("EPOS_LLM_FALLBACK_ENABLED", "true").lower()
    if fallback_enabled not in ("0", "false", "no"):
        candidate = LlmProviderConfig(
            provider_id=os.environ.get("EPOS_SECONDARY_LLM_PROVIDER", "gemini"),
            base_url=os.environ.get("EPOS_SECONDARY_LLM_BASE_URL", "").rstrip("/"),
            model=os.environ.get("EPOS_SECONDARY_LLM_MODEL", ""),
            key_env=os.environ.get("EPOS_SECONDARY_LLM_KEY_ENV", "GEMINI_API_KEY"),
            timeout_seconds=timeout,
            max_attempts=int(os.environ.get("EPOS_SECONDARY_LLM_MAX_ATTEMPTS", "1")),
            omit_temperature=omit_temperature,
        )
        if candidate.complete:
            secondary = candidate

    return LlmProviderChain(primary=primary, secondary=secondary, fallback_enabled=fallback_enabled not in ("0", "false", "no"))


class LlmProviderChain:
    def __init__(
        self,
        primary: LlmProviderConfig,
        secondary: LlmProviderConfig | None = None,
        fallback_enabled: bool = True,
        opener: Callable[..., Any] | None = None,
    ):
        self.primary = primary
        self.secondary = secondary
        self.fallback_enabled = fallback_enabled
        self.opener = opener or urllib.request.urlopen
        self.last_diagnostics: dict[str, Any] = {}

    def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        phase: str,
        parse: Callable[[dict[str, Any]], T],
        validate: Callable[[T], Any] | None = None,
        diagnostics_dir: str | Path | None = None,
    ) -> LlmCallResult[T]:
        attempts: list[dict[str, Any]] = []
        fallback_reason = ""
        first_failure = ""

        primary_result = self._try_provider(
            self.primary, messages, phase, parse, validate, attempts, diagnostics_dir
        )
        if primary_result is not None:
            diagnostics = self._diagnostics(primary_result, attempts, False, "")
            self.last_diagnostics = diagnostics
            return LlmCallResult(primary_result[0], primary_result[1], diagnostics)

        first_failure = attempts[-1]["status"] if attempts else "primary_failed"
        fallback_reason = f"primary_{first_failure}"
        if not self.fallback_enabled:
            self.last_diagnostics = self._failure_diagnostics(attempts, False, fallback_reason)
            raise LlmProviderError("Primary provider failed and fallback is disabled", status=first_failure)
        if self.secondary is None:
            self.last_diagnostics = self._failure_diagnostics(attempts, True, fallback_reason)
            raise LlmProviderError(
                "Primary provider failed and fallback is not available",
                status="fallback_unavailable",
            )

        secondary_result = self._try_provider(
            self.secondary, messages, phase, parse, validate, attempts, diagnostics_dir
        )
        if secondary_result is not None:
            diagnostics = self._diagnostics(secondary_result, attempts, True, fallback_reason)
            self.last_diagnostics = diagnostics
            return LlmCallResult(secondary_result[0], secondary_result[1], diagnostics)

        self.last_diagnostics = self._failure_diagnostics(attempts, True, fallback_reason)
        raise LlmProviderError("All LLM providers failed", status=attempts[-1]["status"])

    def _try_provider(
        self,
        config: LlmProviderConfig,
        messages: list[dict[str, str]],
        phase: str,
        parse: Callable[[dict[str, Any]], T],
        validate: Callable[[T], Any] | None,
        attempts: list[dict[str, Any]],
        diagnostics_dir: str | Path | None,
    ) -> tuple[T, dict[str, Any]] | None:
        try:
            api_key = config.api_key()
        except LlmProviderError as exc:
            attempts.append(self._attempt(config, 1, exc.status, phase=phase, error_type=exc.status))
            return None
        for attempt in range(1, max(1, config.max_attempts) + 1):
            started = time.perf_counter()
            http_status: int | None = None
            raw_content = ""
            payload: dict[str, Any] | None = None
            token_usage: dict[str, Any] | None = None
            try:
                payload, raw_content, token_usage = self._call_once(config, api_key, messages)
                value = parse(payload)
                if validate is not None:
                    report = _normalize_validation_result(validate(value), phase=phase)
                    if not report["valid"]:
                        attempt_item = self._attempt(
                            config,
                            attempt,
                            "semantic_validation_failed",
                            phase=phase,
                            started=started,
                            http_status=http_status,
                            error_type="semantic_validation_failed",
                            validation_report=report,
                            token_usage=token_usage,
                        )
                        self._attach_attempt_files(
                            attempt_item,
                            diagnostics_dir,
                            raw_content=raw_content,
                            parsed_response=payload,
                            validation_report=report,
                        )
                        attempts.append(attempt_item)
                        if attempt < max(1, config.max_attempts):
                            messages = _semantic_retry_messages(messages, report)
                        raise LlmProviderError(
                            "; ".join(report["problems"]),
                            status="semantic_validation_failed",
                            diagnostics={"already_recorded": True},
                        )
                else:
                    report = _validation_report(True, phase=phase)
                attempt_item = self._attempt(
                    config,
                    attempt,
                    "success",
                    phase=phase,
                    started=started,
                    http_status=http_status,
                    validation_report=report,
                    token_usage=token_usage,
                )
                self._attach_attempt_files(
                    attempt_item,
                    diagnostics_dir,
                    raw_content=raw_content,
                    parsed_response=payload,
                    validation_report=report,
                )
                attempts.append(attempt_item)
                return value, payload
            except urllib.error.HTTPError as exc:
                http_status = exc.code
                status = "rate_limited" if exc.code == 429 else "http_error"
                attempts.append(self._attempt(config, attempt, status, phase=phase, started=started, http_status=http_status, error_type=status))
            except TimeoutError:
                attempts.append(self._attempt(config, attempt, "timeout", phase=phase, started=started, error_type="timeout"))
            except urllib.error.URLError as exc:
                reason = str(getattr(exc, "reason", exc))
                status = "dns_error" if "name" in reason.lower() or "dns" in reason.lower() else "connection_error"
                attempts.append(self._attempt(config, attempt, status, phase=phase, started=started, error_type=status))
            except json.JSONDecodeError:
                report = _validation_report(
                    False,
                    phase=phase,
                    stage="parsing",
                    errors=[_validation_error("invalid_json", "", "JSON non valido")],
                )
                attempt_item = self._attempt(config, attempt, "invalid_json", phase=phase, started=started, error_type="invalid_json", validation_report=report, token_usage=token_usage)
                self._attach_attempt_files(attempt_item, diagnostics_dir, raw_content=raw_content, parsed_response=payload, validation_report=report)
                attempts.append(attempt_item)
            except LlmProviderError as exc:
                if exc.diagnostics.get("already_recorded"):
                    continue
                report = exc.diagnostics.get("validation_report")
                attempt_item = self._attempt(
                    config,
                    attempt,
                    exc.status,
                    phase=phase,
                    started=started,
                    http_status=exc.http_status,
                    error_type=exc.status,
                    validation_report=report,
                    token_usage=token_usage,
                )
                self._attach_attempt_files(
                    attempt_item,
                    diagnostics_dir,
                    raw_content=str(exc.diagnostics.get("raw_content", raw_content)),
                    parsed_response=exc.diagnostics.get("parsed_response", payload),
                    validation_report=report,
                )
                attempts.append(attempt_item)
            except Exception as exc:
                status = "contract_invalid"
                if exc.__class__.__name__.lower().endswith("error"):
                    status = "contract_invalid"
                report = _validation_report(
                    False,
                    phase=phase,
                    stage="schema",
                    errors=[_validation_error("schema_validation_failed", "", str(exc))],
                )
                attempt_item = self._attempt(config, attempt, status, phase=phase, started=started, error_type=exc.__class__.__name__, validation_report=report, token_usage=token_usage)
                self._attach_attempt_files(attempt_item, diagnostics_dir, raw_content=raw_content, parsed_response=payload, validation_report=report)
                attempts.append(attempt_item)
        return None

    def _call_once(
        self, config: LlmProviderConfig, api_key: str, messages: list[dict[str, str]]
    ) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
        body: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if not config.omit_temperature:
            body["temperature"] = 0.8
        request = urllib.request.Request(
            f"{config.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with self.opener(request, timeout=config.timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as exc:
            report = _validation_report(
                False,
                phase="",
                stage="parsing",
                errors=[_validation_error("invalid_json", "", str(exc))],
            )
            raise LlmProviderError(
                "provider response is not valid JSON",
                status="invalid_json",
                diagnostics={"raw_content": response_text, "validation_report": report},
            ) from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            report = _validation_report(
                False,
                phase="",
                stage="extraction",
                errors=[_validation_error("missing_content", "choices[0].message.content", "response missing content")],
            )
            raise LlmProviderError(
                "response missing content",
                status="missing_content",
                diagnostics={"raw_content": response_text, "parsed_response": data, "validation_report": report},
            ) from exc
        if not str(content).strip():
            report = _validation_report(
                False,
                phase="",
                stage="extraction",
                errors=[_validation_error("empty_response", "choices[0].message.content", "empty response content")],
            )
            raise LlmProviderError(
                "empty response content",
                status="empty_response",
                diagnostics={"raw_content": "", "parsed_response": data, "validation_report": report},
            )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            report = _validation_report(
                False,
                phase="",
                stage="parsing",
                errors=[_validation_error("invalid_json", "", str(exc))],
            )
            raise LlmProviderError(
                "content is not valid JSON",
                status="invalid_json",
                diagnostics={"raw_content": content, "validation_report": report},
            ) from exc
        if not isinstance(parsed, dict):
            report = _validation_report(
                False,
                phase="",
                stage="schema",
                errors=[_validation_error("schema_validation_failed", "", "content is not a JSON object")],
            )
            raise LlmProviderError(
                "content is not a JSON object",
                status="contract_invalid",
                diagnostics={"raw_content": content, "parsed_response": parsed, "validation_report": report},
            )
        usage = data.get("usage")
        return parsed, str(content), dict(usage) if isinstance(usage, dict) else None

    @staticmethod
    def _attempt(
        config: LlmProviderConfig,
        attempt: int,
        status: str,
        *,
        phase: str = "",
        started: float | None = None,
        http_status: int | None = None,
        error_type: str | None = None,
        validation_report: dict[str, Any] | None = None,
        token_usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "provider": config.provider_id,
            "model": config.model,
            "attempt": attempt,
            "status": status,
            "phase": phase,
        }
        if error_type:
            item["error_type"] = error_type
        if http_status is not None:
            item["http_status"] = http_status
        if started is not None:
            item["duration_ms"] = int((time.perf_counter() - started) * 1000)
        if validation_report:
            item["validation_stage"] = validation_report.get("validation_stage", "")
            item["validation_reason"] = validation_report.get("validation_reason", "")
            item["validation_errors"] = validation_report.get("errors", [])
        if token_usage:
            item["token_usage"] = _sanitize_sensitive_data(token_usage)
        return item

    def _attach_attempt_files(
        self,
        item: dict[str, Any],
        diagnostics_dir: str | Path | None,
        *,
        raw_content: str,
        parsed_response: Any,
        validation_report: dict[str, Any] | None,
    ) -> None:
        if diagnostics_dir is None:
            return
        base_dir = Path(diagnostics_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"{_safe_filename(item['provider'])}_attempt_{item['attempt']}"
        if raw_content:
            raw_path = base_dir / f"{prefix}_raw.txt"
            raw_path.write_text(_sanitize_sensitive_text(raw_content), encoding="utf-8")
            item["raw_response_path"] = f"llm_attempts/{raw_path.name}"
        if parsed_response is not None:
            parsed_path = base_dir / f"{prefix}_parsed.json"
            parsed_path.write_text(
                json.dumps(_sanitize_sensitive_data(parsed_response), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            item["parsed_response_path"] = f"llm_attempts/{parsed_path.name}"
        if validation_report is not None:
            if not validation_report.get("phase") and item.get("phase"):
                validation_report = {**validation_report, "phase": item["phase"]}
            report_path = base_dir / f"{prefix}_validation.json"
            report_path.write_text(
                json.dumps(_sanitize_sensitive_data(validation_report), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            item["validation_report_path"] = f"llm_attempts/{report_path.name}"

    def _diagnostics(
        self,
        result: tuple[T, dict[str, Any]],
        attempts: list[dict[str, Any]],
        fallback_triggered: bool,
        fallback_reason: str,
    ) -> dict[str, Any]:
        selected = attempts[-1]
        return {
            "selected_provider": selected["provider"],
            "selected_model": selected["model"],
            "fallback_triggered": fallback_triggered,
            "fallback_reason": fallback_reason,
            "token_usage": selected.get("token_usage", {}),
            "provider_attempts": attempts,
        }

    def _failure_diagnostics(
        self, attempts: list[dict[str, Any]], fallback_triggered: bool, fallback_reason: str
    ) -> dict[str, Any]:
        return {
            "selected_provider": "",
            "selected_model": "",
            "fallback_triggered": fallback_triggered,
            "fallback_reason": fallback_reason,
            "provider_attempts": attempts,
        }
