"""Intro guidata e persistente per Seven Nights at Azure Crown.

Python governa esclusivamente ordine e avanzamento. La LLM continua a
scrivere narrazione e dialoghi reali, ma ogni turno introduttivo deve
presentare una sola NPC e mostrarne l'immagine. Il giocatore fornisce un
nuovo input tra una presentazione e la successiva.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .turn_service import TurnResult

INTRO_ORDER = ("victoria", "luna", "maria", "stella")


@dataclass(frozen=True)
class ResortIntroStep:
    index: int
    npc_id: str
    title: str
    instruction: str


_STEPS = {
    "victoria": ResortIntroStep(
        index=0,
        npc_id="victoria",
        title="Accoglienza di Victoria",
        instruction=(
            "Victoria Hale si presenta personalmente come direttrice dell'Azure Crown, "
            "spiega in modo naturale il proprio ruolo e comunica che accompagnera il "
            "cliente VIP nella presentazione delle altre tre collaboratrici. Deve parlare "
            "direttamente al giocatore. L'immagine mostra soltanto Victoria."
        ),
    ),
    "luna": ResortIntroStep(
        index=1,
        npc_id="luna",
        title="Presentazione di Luna",
        instruction=(
            "Dopo la risposta del giocatore a Victoria, Victoria introduce Luna. Luna viene "
            "descritta brevemente secondo il suo canone e pronuncia almeno una battuta o "
            "reazione personale rivolta al giocatore. L'immagine mostra soltanto Luna. Non "
            "presentare ancora Maria o Stella."
        ),
    ),
    "maria": ResortIntroStep(
        index=2,
        npc_id="maria",
        title="Presentazione di Maria",
        instruction=(
            "Dopo la risposta del giocatore alla presentazione di Luna, viene introdotta "
            "Maria. Descrivila brevemente secondo il suo ruolo e carattere; Maria deve "
            "parlare o reagire personalmente al giocatore. L'immagine mostra soltanto Maria. "
            "Non presentare ancora Stella."
        ),
    ),
    "stella": ResortIntroStep(
        index=3,
        npc_id="stella",
        title="Presentazione di Stella",
        instruction=(
            "Dopo la risposta del giocatore alla presentazione di Maria, viene introdotta "
            "Stella. Descrivila brevemente secondo il suo ruolo e carattere; Stella deve "
            "parlare o reagire personalmente al giocatore. L'immagine mostra soltanto Stella. "
            "Questa e l'ultima presentazione: non anticipare eventi o missioni successive."
        ),
    ),
}


def initialise_resort_intro(state) -> None:
    state.flags.setdefault("resort_intro_active", True)
    state.flags.setdefault("resort_intro_index", 0)
    state.flags.setdefault("resort_intro_completed", False)
    state.flags.setdefault("resort_intro_presented", [])


def intro_active(state) -> bool:
    initialise_resort_intro(state)
    return bool(state.flags.get("resort_intro_active", False)) and not bool(
        state.flags.get("resort_intro_completed", False)
    )


def current_intro_step(state) -> ResortIntroStep | None:
    if not intro_active(state):
        return None
    index = max(0, int(state.flags.get("resort_intro_index", 0)))
    if index >= len(INTRO_ORDER):
        return None
    return _STEPS[INTRO_ORDER[index]]


def intro_context(state) -> dict[str, Any]:
    step = current_intro_step(state)
    if step is None:
        return {
            "active": False,
            "completed": bool(state.flags.get("resort_intro_completed", False)),
        }
    return {
        "active": True,
        "step": step.index + 1,
        "total_steps": len(INTRO_ORDER),
        "target_npc_id": step.npc_id,
        "title": step.title,
        "instruction": step.instruction,
        "hard_rules": [
            "Produci una sola fase di introduzione in questo turno.",
            "La NPC target deve parlare o reagire personalmente al giocatore.",
            "Il player resta fuori campo e non compare nell'immagine.",
            "focus_character e visible_characters devono contenere soltanto la NPC target.",
            "Non passare alla NPC successiva nello stesso turno.",
        ],
    }


def advance_resort_intro(state, result: TurnResult) -> dict[str, Any]:
    """Avanza di un solo step dopo un turno introduttivo riuscito."""

    step = current_intro_step(state)
    if step is None:
        return {}

    presented = list(state.flags.get("resort_intro_presented", []))
    if step.npc_id not in presented:
        presented.append(step.npc_id)
    state.flags["resort_intro_presented"] = presented

    next_index = step.index + 1
    state.flags["resort_intro_index"] = next_index
    completed = next_index >= len(INTRO_ORDER)
    if completed:
        state.flags["resort_intro_active"] = False
        state.flags["resort_intro_completed"] = True
        next_npc = ""
    else:
        state.flags["resort_intro_active"] = True
        next_npc = INTRO_ORDER[next_index]

    changes = {
        "intro_step_completed": step.npc_id,
        "intro_presented": list(presented),
        "intro_completed": completed,
        "intro_next_npc": next_npc,
    }
    result.campaign_changes = {**dict(result.campaign_changes or {}), **changes}
    return changes
