"""Persistenza delle sessioni.

Layout:

    saves/<session_id>/
      state.json
      checkpoint.json            — solo durante un turno con prova in corso
      turns/<NNNN>/gm_phase1.json
      turns/<NNNN>/roll.json
      turns/<NNNN>/scene.json
      turns/<NNNN>/visual_contract.json
      turns/<NNNN>/render_record.json
      turns/<NNNN>/image.<ext>
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import WorldState
from .rules import Roll


class StateStoreError(RuntimeError):
    """Salvataggio o caricamento fallito."""


class StateStore:
    def __init__(self, root: str | Path = "saves"):
        self.root = Path(root)

    # -- stato -----------------------------------------------------------------

    def _session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    @staticmethod
    def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def save_state(self, state: WorldState) -> None:
        self._atomic_write_json(
            self._session_dir(state.session_id) / "state.json", state.to_dict()
        )

    def load_state(self, session_id: str) -> WorldState:
        path = self._session_dir(session_id) / "state.json"
        if not path.is_file():
            raise StateStoreError(f"sessione non trovata: {session_id}")
        return WorldState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_sessions(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            d.name for d in self.root.iterdir() if d.is_dir() and (d / "state.json").is_file()
        )

    # -- artefatti di turno ------------------------------------------------------

    def _turn_dir(self, session_id: str, turn: int) -> Path:
        return self._session_dir(session_id) / "turns" / f"{turn:04d}"

    def save_turn_artifact(
        self, session_id: str, turn: int, name: str, data: dict[str, Any]
    ) -> Path:
        path = self._turn_dir(session_id, turn) / f"{name}.json"
        self._atomic_write_json(path, data)
        return path

    def load_turn_artifact(
        self, session_id: str, turn: int, name: str
    ) -> dict[str, Any] | None:
        path = self._turn_dir(session_id, turn) / f"{name}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def turn_dir(self, session_id: str, turn: int) -> Path:
        path = self._turn_dir(session_id, turn)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- checkpoint del turno ---------------------------------------------------

    def save_checkpoint(
        self,
        session_id: str,
        turn: int,
        phase: str,
        proposal: dict[str, Any] | None,
        roll: Roll | None,
    ) -> None:
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": session_id,
            "turn": turn,
            "phase": phase,
            "proposal": proposal,
            "roll": roll.to_dict() if roll else None,
        }
        self._atomic_write_json(session_dir / "checkpoint.json", data)

    def load_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        path = self._session_dir(session_id) / "checkpoint.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def clear_checkpoint(self, session_id: str) -> None:
        path = self._session_dir(session_id) / "checkpoint.json"
        if path.is_file():
            path.unlink()
