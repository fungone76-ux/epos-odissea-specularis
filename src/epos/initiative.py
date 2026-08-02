"""Iniziativa autonoma degli NPC e del mondo.

Un'iniziativa è valida solo se:
- la fonte esiste (NPC presente o fonte mondiale canonica);
- ha uno scopo concreto — le reazioni pure (sguardi, sorrisi, esitazioni)
  non sono iniziative;
- è coerente con la scena (il target, se c'è, è presente).

I contatori misurano il ritmo: troppi turni reattivi di fila segnalano
NPC passivi; il GM vede lo stato nello snapshot e può correggere la regia.
"""

from __future__ import annotations

from .contract import WORLD_SOURCES, InitiativeEvent
from .models import WorldState

PURE_REACTION_TOKENS = (
    "sguardo",
    "sorride",
    "sorrido",
    "esita",
    "sospira",
    "scrollata",
    "osserva in silenzio",
    "annuisce",
    "resta vicina",
    "resta vicino",
    "rimane vicina",
    "rimane vicino",
    "certo",
    "va bene",
    "gaze",
    "smile",
    "sigh",
    "shrug",
)

MAX_RECENT_INITIATIVES = 10


def looks_like_pure_reaction(event: InitiativeEvent) -> bool:
    """Una 'iniziativa' che è solo una reazione emotiva o di sguardo."""

    text = f"{event.summary} {event.reason}".casefold()
    if event.type != "other":
        return False
    return any(token in text for token in PURE_REACTION_TOKENS)


def validate_initiative(
    state: WorldState, event: InitiativeEvent
) -> list[str]:
    problems: list[str] = []

    if event.source in WORLD_SOURCES:
        if event.type not in ("environmental_event", "pressure_advance", "other"):
            problems.append(
                f"fonte mondiale {event.source!r} con tipo non ambientale: {event.type!r}"
            )
    elif event.source in state.npcs:
        if not state.npcs[event.source].present:
            problems.append(f"iniziativa di NPC assente: {event.source!r}")
    else:
        problems.append(f"fonte di iniziativa inesistente: {event.source!r}")

    if event.target is not None and not state.is_present(event.target):
        problems.append(f"target di iniziativa assente: {event.target!r}")

    if looks_like_pure_reaction(event):
        problems.append(
            f"reazione pura spacciata per iniziativa: {event.summary[:50]!r}"
        )

    return problems


def counts_as_autonomous(event: InitiativeEvent) -> bool:
    return not looks_like_pure_reaction(event)


def apply_initiatives(state: WorldState, events: list[InitiativeEvent]) -> None:
    """Aggiorna ritmo e cronologia dell'iniziativa. Chiamato dal commit."""

    autonomous = [e for e in events if counts_as_autonomous(e)]
    if autonomous:
        state.initiative.consecutive_reactive_turns = 0
        state.initiative.last_autonomous_turn = state.turn
    else:
        state.initiative.consecutive_reactive_turns += 1

    for event in events:
        state.initiative.recent.append(
            {
                "turn": state.turn,
                "source": event.source,
                "type": event.type,
                "summary": event.summary,
            }
        )
    state.initiative.recent = state.initiative.recent[-MAX_RECENT_INITIATIVES:]


def initiative_context(state: WorldState) -> dict:
    """Vista compatta per lo snapshot del GM."""

    consecutive = state.initiative.consecutive_reactive_turns
    if consecutive >= 5:
        pressure = "mandatory"
        hint = (
            "Gli NPC restano passivi da 5 o piu turni: se non ci sono eccezioni "
            "canoniche, includi una iniziativa autonoma concreta di una NPC presente."
        )
    elif consecutive >= 3:
        pressure = "strong"
        hint = (
            "Gli NPC restano reattivi da diversi turni: valuta fortemente una "
            "iniziativa autonoma coerente con obiettivi, luogo e stato canonico."
        )
    else:
        pressure = "none"
        hint = ""

    return {
        "consecutive_reactive_turns": consecutive,
        "recent": state.initiative.recent[-3:],
        "hint": hint,
    }
