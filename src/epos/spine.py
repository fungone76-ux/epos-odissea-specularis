"""Story spine e pressioni: il progresso narrativo e le minacce incombenti.

Story spine: il world-pack definisce marker canonici (tappe del vertical
slice). Il GM propone marker solo quando la scena li ha davvero guadagnati;
Python accetta solo marker canonici e non duplicati.

Pressioni: minacce definite nel pack che avanzano nel tempo. Il GM può
farle avanzare con un'iniziativa pressure_advance; Python impone un
intervallo minimo tra avanzamenti della stessa pressione.
"""

from __future__ import annotations

from .contract import InitiativeEvent
from .models import PressureState, WorldState
from .worldpack import WorldPack

MIN_TURNS_BETWEEN_PRESSURE_ADVANCES = 2


# ---------------------------------------------------------------------------
# Story spine
# ---------------------------------------------------------------------------


def validate_story_marker(pack: WorldPack, state: WorldState, marker_id: str) -> list[str]:
    problems: list[str] = []
    if marker_id not in pack.story_markers:
        problems.append(f"story marker non canonico: {marker_id!r}")
    elif marker_id in state.story_markers:
        problems.append(f"story marker già confermato: {marker_id!r}")
    return problems


def apply_story_marker(state: WorldState, marker_id: str) -> None:
    if marker_id not in state.story_markers:
        state.story_markers.append(marker_id)


def spine_context(pack: WorldPack, state: WorldState) -> dict:
    """Vista del progresso per lo snapshot del GM."""

    remaining = [
        {"id": m.id, "summary": m.summary}
        for m in pack.story_markers.values()
        if m.id not in state.story_markers
    ]
    return {
        "confirmed": list(state.story_markers),
        "remaining": remaining,
        "slice_concluded": any(
            pack.story_markers[m].concludes_slice for m in state.story_markers
            if m in pack.story_markers
        ),
    }


# ---------------------------------------------------------------------------
# Pressioni
# ---------------------------------------------------------------------------


def validate_pressure_advance(
    pack: WorldPack, state: WorldState, event: InitiativeEvent
) -> list[str]:
    """Un'iniziativa pressure_advance deve citare una pressione del pack
    e rispettare l'intervallo minimo tra avanzamenti."""

    problems: list[str] = []
    pressure_id = _pressure_id_for(pack, event)
    if pressure_id is None:
        problems.append(
            f"pressure_advance senza pressione canonica citata: {event.summary[:50]!r}"
        )
        return problems

    pressure_state = state.pressures.get(pressure_id, PressureState())
    if (
        pressure_state.last_advanced_turn >= 0
        and state.turn - pressure_state.last_advanced_turn
        < MIN_TURNS_BETWEEN_PRESSURE_ADVANCES
    ):
        problems.append(
            f"pressione {pressure_id!r} avanzata troppo presto "
            f"(ultimo avanzamento al turno {pressure_state.last_advanced_turn})"
        )
    return problems


def apply_pressure_advance(pack: WorldPack, state: WorldState, event: InitiativeEvent) -> None:
    pressure_id = _pressure_id_for(pack, event)
    if pressure_id is None:
        return
    pressure_state = state.pressures.setdefault(pressure_id, PressureState())
    pressure_state.level += 1
    pressure_state.last_advanced_turn = state.turn


def _pressure_id_for(pack: WorldPack, event: InitiativeEvent) -> str | None:
    """Identifica la pressione citata dall'iniziativa: per id esplicito
    nel reason (`pressure:<id>`) o per id contenuto nel testo."""

    reason = event.reason
    if reason.startswith("pressure:"):
        candidate = reason.split(":", 1)[1].strip()
        if candidate in pack.pressures:
            return candidate
    text = f"{event.summary} {event.reason}".casefold()
    for pressure_id in pack.pressures:
        if pressure_id.casefold() in text:
            return pressure_id
    return None


def pressure_context(pack: WorldPack, state: WorldState) -> list[dict]:
    """Pressioni attive per lo snapshot del GM."""

    context = []
    for pressure_id, definition in pack.pressures.items():
        pressure_state = state.pressures.get(pressure_id, PressureState())
        due = (
            state.turn - pressure_state.last_advanced_turn
            >= MIN_TURNS_BETWEEN_PRESSURE_ADVANCES
        )
        context.append(
            {
                "id": pressure_id,
                "summary": definition.summary,
                "level": pressure_state.level,
                "escalation_hint": definition.escalation_hint if due else "",
            }
        )
    return context
