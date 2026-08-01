"""Campaign runtime for Seven Nights at Azure Crown.

Python owns calendar, event eligibility, mission gates and disclosure limits.
The LLM receives only a filtered interpretation context and cannot advance the
campaign by narration alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from .models import WorldState
from .resort_relationships import (
    RESORT_NPC_IDS,
    initialise_resort_relationships,
    relationship_snapshot,
)
from .worldpack import WorldPack, WorldPackError, load_pack

RESORT_WORLD_ID = "resort_world"
RESORT_PHASES = ("mattina", "pomeriggio", "sera", "notte")
MAX_DAY = 7


@dataclass(frozen=True)
class ResortEvent:
    id: str
    title: str
    day_range: tuple[int, int]
    phases: tuple[str, ...]
    location_id: str
    npc_ids: tuple[str, ...]
    trigger: dict[str, Any]
    adult_component: str
    consent_exit_required: bool
    choices: tuple[str, ...]
    completion_flag: str = ""
    visual_outfit: str = ""


@dataclass(frozen=True)
class ResortMissionPolicy:
    id: str
    reveal: str
    unlock_when: dict[str, Any]
    required_flags: tuple[str, ...]
    terminal_success_flags: tuple[str, ...]
    terminal_failure_flags: tuple[str, ...]
    reveal_gates: dict[str, str]


@dataclass(frozen=True)
class ResortPack:
    world: WorldPack
    events: dict[str, ResortEvent]
    mission_policies: dict[str, ResortMissionPolicy]


def _yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise WorldPackError(f"file resort mancante: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise WorldPackError(f"YAML resort non valido: {path}")
    if int(data.get("schema_version", 0)) != 1:
        raise WorldPackError(f"schema_version non supportata in {path}")
    if str(data.get("world_id", "")) != RESORT_WORLD_ID:
        raise WorldPackError(f"world_id errato in {path}")
    return data


def load_resort_pack(pack_dir: str | Path) -> ResortPack:
    """Load generic pack plus strict resort mission/event extensions."""

    pack_dir = Path(pack_dir)
    world = load_pack(pack_dir)
    if world.id != RESORT_WORLD_ID:
        raise WorldPackError(f"pack resort atteso, trovato {world.id!r}")

    mission_data = _yaml(pack_dir / "missions.yaml")
    event_data = _yaml(pack_dir / "events.yaml")

    policies: dict[str, ResortMissionPolicy] = {}
    for index, raw in enumerate(mission_data.get("missions", [])):
        mission_id = str(raw.get("id", "")).strip()
        if not mission_id:
            raise WorldPackError(f"missions.yaml missions[{index}]: id mancante")
        if mission_id in policies:
            raise WorldPackError(f"mission policy duplicata: {mission_id}")
        if mission_id not in world.missions:
            raise WorldPackError(f"mission policy senza missione in world.yaml: {mission_id}")
        policies[mission_id] = ResortMissionPolicy(
            id=mission_id,
            reveal=str(raw.get("reveal", "progressive")),
            unlock_when=dict(raw.get("unlock_when") or {}),
            required_flags=tuple(str(v) for v in raw.get("required_flags", [])),
            terminal_success_flags=tuple(str(v) for v in raw.get("terminal_success_flags", [])),
            terminal_failure_flags=tuple(str(v) for v in raw.get("terminal_failure_flags", [])),
            reveal_gates={str(k): str(v) for k, v in dict(raw.get("reveal_gates") or {}).items()},
        )
    if set(policies) != set(world.missions):
        missing = sorted(set(world.missions) - set(policies))
        raise WorldPackError(f"mission policies mancanti: {missing}")

    events: dict[str, ResortEvent] = {}
    known_locations = set(world.locations)
    known_npcs = set(world.npc_canon)
    for index, raw in enumerate(event_data.get("events", [])):
        event_id = str(raw.get("id", "")).strip()
        if not event_id:
            raise WorldPackError(f"events.yaml events[{index}]: id mancante")
        if event_id in events:
            raise WorldPackError(f"evento duplicato: {event_id}")
        location_id = str(raw.get("location_id", ""))
        if location_id not in known_locations:
            raise WorldPackError(f"evento {event_id}: location sconosciuta {location_id!r}")
        npc_ids = tuple(str(v) for v in raw.get("npc_ids", []))
        unknown = sorted(set(npc_ids) - known_npcs)
        if unknown:
            raise WorldPackError(f"evento {event_id}: NPC sconosciuti {unknown}")
        phases = tuple(str(v) for v in raw.get("phases", []))
        if not phases or any(phase not in RESORT_PHASES for phase in phases):
            raise WorldPackError(f"evento {event_id}: fasi non valide {phases}")
        day_range_raw = list(raw.get("day_range", []))
        if len(day_range_raw) != 2:
            raise WorldPackError(f"evento {event_id}: day_range deve avere due valori")
        day_range = (int(day_range_raw[0]), int(day_range_raw[1]))
        if day_range[0] < 1 or day_range[1] > MAX_DAY or day_range[0] > day_range[1]:
            raise WorldPackError(f"evento {event_id}: day_range non valido {day_range}")
        choices = tuple(str(v) for v in raw.get("choices", []))
        if bool(raw.get("consent_exit_required", False)) and not any(
            token in choice for choice in choices for token in ("decline", "cancel", "skip", "leave", "alone", "postpone", "end")
        ):
            raise WorldPackError(f"evento {event_id}: manca una scelta di rifiuto/uscita")
        adult_component = str(raw.get("adult_component", "")).strip()
        if not adult_component:
            raise WorldPackError(f"evento {event_id}: adult_component mancante")
        events[event_id] = ResortEvent(
            id=event_id,
            title=str(raw.get("title", event_id)),
            day_range=day_range,
            phases=phases,
            location_id=location_id,
            npc_ids=npc_ids,
            trigger=dict(raw.get("trigger") or {}),
            adult_component=adult_component,
            consent_exit_required=bool(raw.get("consent_exit_required", False)),
            choices=choices,
            completion_flag=str(raw.get("completion_flag", "")),
            visual_outfit=str(raw.get("visual_outfit", "")),
        )

    return ResortPack(world=world, events=events, mission_policies=policies)


def initialise_resort_state(state: WorldState) -> WorldState:
    """Initialise persistent campaign flags without changing core models."""

    state.flags.setdefault("resort_day", 1)
    state.flags.setdefault("resort_phase_turns", 0)
    state.flags.setdefault("resort_completed_events", [])
    state.flags.setdefault("resort_active_missions", ["mission_resort_future"])
    state.flags.setdefault("resort_revealed_missions", ["mission_resort_future"])
    state.flags.setdefault("resort_debt_due_day", 7)
    state.flags.setdefault("resort_debt_due_phase", "sera")
    state.flags.setdefault("resort_final_decision", False)
    state.flags.setdefault("bank_debt_disclosed", False)
    state.flags.setdefault("luna_letter_mention_unlocked", False)
    state.flags.setdefault("luna_letter_reveal_unlocked", False)
    state.flags.setdefault("luna_letter_truth_unlocked", False)
    initialise_resort_relationships(state)
    return state


def new_resort_world(pack: ResortPack, session_id: str | None = None) -> WorldState:
    state = pack.world.new_world(session_id)
    return initialise_resort_state(state)


def current_day(state: WorldState) -> int:
    return int(state.flags.get("resort_day", 1))


def advance_resort_time(state: WorldState, *, force: bool = False, turn_limit: int = 4) -> bool:
    """Advance one phase when forced or after enough turns in the same phase."""

    initialise_resort_state(state)
    phase_turns = int(state.flags.get("resort_phase_turns", 0)) + 1
    state.flags["resort_phase_turns"] = phase_turns
    if not force and phase_turns < turn_limit:
        return False
    index = RESORT_PHASES.index(state.time_phase)
    if index == len(RESORT_PHASES) - 1:
        state.flags["resort_day"] = min(MAX_DAY, current_day(state) + 1)
        state.time_phase = RESORT_PHASES[0]
    else:
        state.time_phase = RESORT_PHASES[index + 1]
    state.flags["resort_phase_turns"] = 0
    if current_day(state) == 7 and state.time_phase == "sera":
        state.flags["resort_debt_due"] = True
    return True


def _trigger_matches(state: WorldState, trigger: dict[str, Any]) -> bool:
    if not trigger:
        return True
    if "flag" in trigger:
        return state.flags.get(str(trigger["flag"])) == trigger.get("expected", True)
    if "flag_missing" in trigger:
        return not bool(state.flags.get(str(trigger["flag_missing"]), False))
    if "day" in trigger:
        return current_day(state) == int(trigger["day"]) and (
            "phase" not in trigger or state.time_phase == str(trigger["phase"])
        )
    if "mission_active" in trigger:
        return str(trigger["mission_active"]) in state.flags.get("resort_active_missions", [])
    if "relationship_field" in trigger:
        field = str(trigger["relationship_field"])
        minimum = int(trigger.get("minimum", 0))
        if field == "jealousy":
            return any(int(state.flags.get(f"resort_jealousy_{npc_id}", 0)) >= minimum for npc_id in RESORT_NPC_IDS)
    if "player_request" in trigger:
        return bool(trigger["player_request"])
    if "random_weight" in trigger:
        return True
    return False


def eligible_events(state: WorldState, pack: ResortPack) -> list[ResortEvent]:
    initialise_resort_state(state)
    completed = set(state.flags.get("resort_completed_events", []))
    day = current_day(state)
    return [
        event
        for event in pack.events.values()
        if event.id not in completed
        and event.day_range[0] <= day <= event.day_range[1]
        and state.time_phase in event.phases
        and state.location_id == event.location_id
        and _trigger_matches(state, event.trigger)
    ]


def complete_event(state: WorldState, event: ResortEvent) -> None:
    initialise_resort_state(state)
    completed = list(state.flags.get("resort_completed_events", []))
    if event.id not in completed:
        completed.append(event.id)
    state.flags["resort_completed_events"] = completed
    if event.completion_flag:
        state.flags[event.completion_flag] = True


def update_mission_unlocks(state: WorldState, pack: ResortPack) -> list[str]:
    """Unlock mission visibility from authoritative state only."""

    initialise_resort_state(state)
    active = set(state.flags.get("resort_active_missions", []))
    revealed = set(state.flags.get("resort_revealed_missions", []))
    newly_unlocked: list[str] = []
    for policy in pack.mission_policies.values():
        if policy.id in active or policy.reveal == "initial":
            continue
        rule = policy.unlock_when
        unlocked = False
        if "flag" in rule:
            unlocked = state.flags.get(str(rule["flag"])) == rule.get("expected", True)
        elif "event_completed" in rule:
            unlocked = str(rule["event_completed"]) in state.flags.get("resort_completed_events", [])
        elif "relationship" in rule:
            npc_id = str(rule["relationship"])
            field = str(rule.get("field", "trust"))
            minimum = int(rule.get("minimum", 0))
            if npc_id in state.npcs:
                unlocked = int(getattr(state.npcs[npc_id].relationship_towards("player"), field)) >= minimum
        if unlocked:
            active.add(policy.id)
            revealed.add(policy.id)
            newly_unlocked.append(policy.id)
    state.flags["resort_active_missions"] = sorted(active)
    state.flags["resort_revealed_missions"] = sorted(revealed)
    return newly_unlocked


def update_luna_disclosure_gates(state: WorldState) -> None:
    """Derive Luna's disclosure gates from trust and prior canonical steps."""

    initialise_resort_state(state)
    luna = state.npcs.get("luna")
    if luna is None:
        return
    trust = luna.relationship_towards("player").trust
    if trust >= 2:
        state.flags["luna_letter_mention_unlocked"] = True
    if trust >= 4 and bool(state.flags.get("luna_letter_mentioned", False)):
        state.flags["luna_letter_reveal_unlocked"] = True
    if bool(state.flags.get("luna_letter_revealed", False)) and bool(state.flags.get("luna_letter_author_confirmed", False)):
        state.flags["luna_letter_truth_unlocked"] = True


def llm_context_for_npc(state: WorldState, pack: ResortPack, npc_id: str) -> dict[str, Any]:
    """Build filtered NPC context, excluding locked secrets and other minds."""

    initialise_resort_state(state)
    update_luna_disclosure_gates(state)
    if npc_id not in pack.world.npc_canon or npc_id not in state.npcs:
        raise ValueError(f"NPC resort sconosciuto: {npc_id!r}")
    canon = pack.world.npc_canon[npc_id]
    npc = state.npcs[npc_id]
    secrets: list[str] = []
    if npc_id == "luna":
        if state.flags.get("luna_letter_mention_unlocked"):
            secrets.append("Luna conserva una vecchia lettera legata al padre del protagonista.")
        if state.flags.get("luna_letter_truth_unlocked"):
            secrets.extend(canon.secrets)
    elif npc_id == "victoria":
        secrets = list(canon.secrets)
    active_missions = [
        mission_id
        for mission_id in state.flags.get("resort_active_missions", [])
        if mission_id.endswith(npc_id) or npc_id in mission_id or (npc_id == "victoria" and mission_id == "mission_victoria_save_resort")
    ]
    return {
        "world_id": RESORT_WORLD_ID,
        "day": current_day(state),
        "phase": state.time_phase,
        "location_id": state.location_id,
        "npc_id": npc_id,
        "identity": {"name": canon.name, "age": canon.age, "personality": list(canon.personality)},
        "speech_style": canon.speech_style,
        "goals": list(canon.goals),
        "knowledge": list(npc.knowledge),
        "unlocked_secrets": secrets,
        "active_missions": active_missions,
        "relationship": relationship_snapshot(state, npc_id),
        "outfit": {"worn": list(npc.outfit.worn), "removed": list(npc.outfit.removed)},
        "disclosure_policy": canon.disclosure_policy,
        "red_lines": list(canon.red_lines),
        "rules": [
            "Non inventare avanzamenti, flag, cambi di luogo o outfit.",
            "Non rivelare segreti assenti da unlocked_secrets.",
            "Non dichiarare il consenso o i desideri interni di altri personaggi.",
            "Interpreta soltanto la scena già validata da Python.",
        ],
    }
