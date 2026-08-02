"""Mutation validation helpers for final scenes."""

from __future__ import annotations

from .contract import Mutation
from .models import KNOWLEDGE_SOURCES, RELATIONSHIP_DOMAINS, WorldState
from .worldpack import WorldPack

# Limiti di proporzionalitÃ  per singola mutazione in un turno.
MAX_RELATIONSHIP_DELTA = 15
MAX_RESOURCE_DELTA = 3


def _validate_mutation(
    state: WorldState,
    pack: WorldPack,
    mutation: Mutation,
    present_ids: set[str],
) -> list[str]:
    problems: list[str] = []
    target = mutation.target
    target_exists = target == "player" or target in state.npcs or target == "world"

    if mutation.type in (
        "relationship_delta",
        "knowledge_add",
        "condition_add",
        "condition_remove",
        "item_add",
        "item_remove",
        "outfit_wear",
        "outfit_remove",
        "wound_add",
        "resource_delta",
        "emotion_set",
        "intention_set",
    ):
        if not target_exists or target == "world":
            problems.append(f"{mutation.type}: target inesistente {target!r}")
        elif target not in present_ids and mutation.type not in ("intention_set",):
            # presenza: si puÃ² mutare solo chi Ã¨ nella scena (le intenzioni degli
            # NPC presenti sono l'eccezione gestita sopra)
            if not (target in state.npcs and state.npcs[target].present):
                problems.append(f"{mutation.type}: target assente dalla scena {target!r}")

    if mutation.type == "relationship_delta":
        for domain, delta in (mutation.payload or {}).items():
            if domain not in RELATIONSHIP_DOMAINS:
                problems.append(f"relationship_delta: dominio sconosciuto {domain!r}")
            elif abs(int(delta)) > MAX_RELATIONSHIP_DELTA:
                problems.append(
                    f"relationship_delta: delta {delta} oltre il limite Â±{MAX_RELATIONSHIP_DELTA}"
                )

    if mutation.type == "resource_delta":
        for key, delta in (mutation.payload or {}).items():
            if abs(int(delta)) > MAX_RESOURCE_DELTA:
                problems.append(
                    f"resource_delta ({key}): delta {delta} oltre il limite Â±{MAX_RESOURCE_DELTA}"
                )

    if mutation.type == "location_change":
        destination = str(mutation.payload.get("location_id", ""))
        if destination not in pack.locations:
            problems.append(f"location_change: destinazione sconosciuta {destination!r}")

    if mutation.type == "item_remove":
        item = str(mutation.payload.get("item", ""))
        if target == "player" and item not in state.player.inventory:
            problems.append(f"item_remove: {item!r} non nell'inventario del giocatore")

    if mutation.type == "outfit_remove":
        item = str(mutation.payload.get("item", ""))
        character = state.player if target == "player" else state.npcs.get(target, None)
        worn = character.outfit.worn if character is not None else []
        if item not in worn:
            problems.append(
                f"outfit_remove: {item!r} non indossato da {target!r} "
                'â€” usa payload {"item": "<capo esatto da outfit_worn>"}, '
                "una mutazione per capo (mai liste)"
            )

    if mutation.type == "thread_close":
        thread_id = str(mutation.payload.get("thread_id", ""))
        thread = next((t for t in state.active_threads if t.id == thread_id and t.status == "open"), None)
        if thread is None:
            problems.append(f"thread_close: thread {thread_id!r} non aperto")
        elif not str(mutation.payload.get("reason", mutation.reason)).strip():
            problems.append("thread_close: reason obbligatoria")

    if mutation.type == "thread_open":
        if not str(mutation.payload.get("summary", "")).strip():
            problems.append("thread_open: summary obbligatoria")
        if not str(mutation.payload.get("close_condition", "")).strip():
            problems.append("thread_open: close_condition obbligatoria")
        participants = mutation.payload.get("participants", ["player"])
        if not isinstance(participants, list) or not participants:
            problems.append("thread_open: participants obbligatorio")
        else:
            for participant in participants:
                if str(participant) not in present_ids:
                    problems.append(f"thread_open: partecipante assente {participant!r}")

    if mutation.type == "knowledge_add":
        fact = str(mutation.payload.get("fact", "")).strip()
        if not fact:
            problems.append("knowledge_add: fact obbligatorio")
        source = str(mutation.payload.get("source", "contextual")).strip()
        if source not in KNOWLEDGE_SOURCES:
            problems.append(f"knowledge_add: source non valida {source!r}")
        try:
            credibility = float(mutation.payload.get("credibility", 1.0))
        except (TypeError, ValueError):
            problems.append("knowledge_add: credibility deve essere numerica")
        else:
            if not 0.0 <= credibility <= 1.0:
                problems.append("knowledge_add: credibility fuori range 0.0-1.0")

    if mutation.type == "story_marker_add":
        from .spine import validate_story_marker

        marker_id = str(mutation.payload.get("marker_id", ""))
        problems.extend(validate_story_marker(pack, state, marker_id))

    if mutation.type == "mission_complete":
        if not str(mutation.target).strip():
            problems.append("mission_complete: target mission_id obbligatorio")
        objectives = mutation.payload.get("completed_objectives", [])
        if not isinstance(objectives, list) or not objectives:
            problems.append("mission_complete: completed_objectives obbligatorio")

    return problems
