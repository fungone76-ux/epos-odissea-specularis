"""Shared renderer helpers with no network or import-time side effects."""

from __future__ import annotations

import os
import re
import urllib.parse
from typing import Any


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
