"""Optional companion-file persistence for NPC agent registry data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .npc_agent_registry import NpcAgentRegistry

NPC_AGENT_REGISTRY_FILENAME = "npc_agents.json"


def npc_agent_registry_path(root: str | Path, session_id: str) -> Path:
    return Path(root) / str(session_id) / NPC_AGENT_REGISTRY_FILENAME


def save_npc_agent_registry(root: str | Path, session_id: str, registry: NpcAgentRegistry) -> Path:
    path = npc_agent_registry_path(root, session_id)
    _atomic_write_json(path, registry.to_dict())
    return path


def load_npc_agent_registry(root: str | Path, session_id: str) -> NpcAgentRegistry:
    path = npc_agent_registry_path(root, session_id)
    if not path.is_file():
        return NpcAgentRegistry()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("NPC agent registry companion file must contain an object")
    return NpcAgentRegistry.from_dict(data)


def registry_payload_from_legacy(data: dict[str, Any] | None) -> NpcAgentRegistry:
    if not data:
        return NpcAgentRegistry()
    return NpcAgentRegistry.from_dict(data.get("npc_agents"))


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
