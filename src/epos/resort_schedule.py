"""Authoritative seven-day NPC schedule and wardrobe runtime for the Resort.

Python owns scheduled locations and outfits. Events, explicit summons and
player-agreed outfit changes may temporarily override the ordinary schedule.
The ordinary schedule is applied only when the day/phase changes, so it never
rewrites an outfit in the middle of a scene.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import Outfit, WorldState
from .worldpack import WorldPack, WorldPackError

PHASES = ("mattina", "pomeriggio", "sera", "notte")
NPC_IDS = ("victoria", "stella", "maria", "luna")


@dataclass(frozen=True)
class ResortScheduleConfig:
    schedules: dict[str, dict[int, dict[str, str]]]
    wardrobes: dict[str, dict[int, dict[str, tuple[str, ...]]]]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise WorldPackError(f"configurazione Resort mancante: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise WorldPackError(f"YAML Resort non valido: {path}")
    if int(data.get("schema_version", 0)) != 1:
        raise WorldPackError(f"schema_version non supportata: {path}")
    if str(data.get("world_id", "")) != "resort_world":
        raise WorldPackError(f"world_id errato: {path}")
    return data


def load_resort_schedule_config(pack_dir: str | Path, world: WorldPack) -> ResortScheduleConfig:
    pack_dir = Path(pack_dir)
    schedule_data = _read_yaml(pack_dir / "npc_schedules.yaml")
    wardrobe_data = _read_yaml(pack_dir / "npc_wardrobes.yaml")

    schedules: dict[str, dict[int, dict[str, str]]] = {}
    raw_schedules = dict(schedule_data.get("schedules") or {})
    raw_wardrobes = dict(wardrobe_data.get("wardrobes") or {})

    if set(raw_schedules) != set(NPC_IDS):
        raise WorldPackError("npc_schedules.yaml deve contenere esattamente le quattro NPC Resort")
    if set(raw_wardrobes) != set(NPC_IDS):
        raise WorldPackError("npc_wardrobes.yaml deve contenere esattamente le quattro NPC Resort")

    wardrobes: dict[str, dict[int, dict[str, tuple[str, ...]]]] = {}
    for npc_id in NPC_IDS:
        npc_schedule: dict[int, dict[str, str]] = {}
        npc_wardrobe: dict[int, dict[str, tuple[str, ...]]] = {}
        for day in range(1, 8):
            raw_day_schedule = dict(raw_schedules[npc_id].get(day) or raw_schedules[npc_id].get(str(day)) or {})
            raw_day_wardrobe = dict(raw_wardrobes[npc_id].get(day) or raw_wardrobes[npc_id].get(str(day)) or {})
            if set(raw_day_schedule) != set(PHASES):
                raise WorldPackError(f"schedule incompleto: {npc_id}, giorno {day}")
            if set(raw_day_wardrobe) != set(PHASES):
                raise WorldPackError(f"guardaroba incompleto: {npc_id}, giorno {day}")

            phase_locations: dict[str, str] = {}
            phase_outfits: dict[str, tuple[str, ...]] = {}
            for phase in PHASES:
                location_id = str(raw_day_schedule[phase])
                if location_id not in world.locations:
                    raise WorldPackError(
                        f"schedule {npc_id} giorno {day} {phase}: location sconosciuta {location_id!r}"
                    )
                outfit = tuple(str(item).strip() for item in raw_day_wardrobe[phase] if str(item).strip())
                if not outfit:
                    raise WorldPackError(f"guardaroba vuoto: {npc_id}, giorno {day}, {phase}")
                phase_locations[phase] = location_id
                phase_outfits[phase] = outfit
            npc_schedule[day] = phase_locations
            npc_wardrobe[day] = phase_outfits
        schedules[npc_id] = npc_schedule
        wardrobes[npc_id] = npc_wardrobe

    return ResortScheduleConfig(schedules=schedules, wardrobes=wardrobes)


def schedule_key(state: WorldState) -> str:
    day = max(1, min(7, int(state.flags.get("resort_day", 1))))
    return f"{day}:{state.time_phase}"


def record_outfit_overrides_from_turn(state: WorldState, result: Any) -> None:
    """Keep an NPC outfit chosen in a scene until the current phase ends."""

    scene = getattr(result, "scene", None)
    if scene is None:
        return
    targets = {
        str(mutation.target)
        for mutation in getattr(scene, "mutations", [])
        if str(getattr(mutation, "type", "")) in {"outfit_wear", "outfit_remove"}
        and str(getattr(mutation, "target", "")) in state.npcs
    }
    if not targets:
        return
    locks = dict(state.flags.get("resort_outfit_override_until", {}))
    for npc_id in targets:
        locks[npc_id] = schedule_key(state)
    state.flags["resort_outfit_override_until"] = locks


def record_location_override(state: WorldState, npc_id: str) -> None:
    """Keep an explicitly summoned NPC at that location for the current phase."""

    if npc_id not in state.npcs:
        return
    locks = dict(state.flags.get("resort_location_override_until", {}))
    locks[npc_id] = schedule_key(state)
    state.flags["resort_location_override_until"] = locks


def _replace_scheduled_outfit(npc, scheduled: tuple[str, ...]) -> None:
    current = list(npc.outfit.worn)
    if current == list(scheduled):
        return
    removed = list(npc.outfit.removed)
    for item in current:
        if item not in removed:
            removed.append(item)
    for item in scheduled:
        if item in removed:
            removed.remove(item)
    npc.outfit = Outfit(
        worn=list(scheduled),
        removed=removed,
        revision=npc.outfit.revision + 1,
    )


def apply_resort_schedule(
    state: WorldState,
    config: ResortScheduleConfig,
    *,
    previous_key: str | None = None,
) -> list[dict[str, Any]]:
    """Apply locations and outfits for the current day/phase.

    Overrides are valid only for the key in which they were created. Therefore
    an explicit summon or outfit request survives the rest of the current phase
    but naturally expires at the following phase.
    """

    current_key = schedule_key(state)
    if previous_key is not None and previous_key == current_key:
        return []

    day = max(1, min(7, int(state.flags.get("resort_day", 1))))
    phase = state.time_phase
    outfit_locks = dict(state.flags.get("resort_outfit_override_until", {}))
    location_locks = dict(state.flags.get("resort_location_override_until", {}))
    changes: list[dict[str, Any]] = []

    for npc_id in NPC_IDS:
        npc = state.npcs[npc_id]
        old_location = npc.location_id
        old_outfit = list(npc.outfit.worn)

        if location_locks.get(npc_id) != current_key:
            npc.location_id = config.schedules[npc_id][day][phase]

        if outfit_locks.get(npc_id) != current_key:
            _replace_scheduled_outfit(npc, config.wardrobes[npc_id][day][phase])

        npc.present = npc.location_id == state.location_id
        if npc.location_id != old_location or list(npc.outfit.worn) != old_outfit:
            changes.append(
                {
                    "npc_id": npc_id,
                    "day": day,
                    "phase": phase,
                    "from_location": old_location,
                    "to_location": npc.location_id,
                    "outfit": list(npc.outfit.worn),
                }
            )

    state.flags["resort_schedule_applied"] = current_key
    state.flags["resort_schedule_changes"] = changes
    return changes
