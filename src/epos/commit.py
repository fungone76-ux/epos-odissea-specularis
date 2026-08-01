"""Commit: l'unico confine canonico in cui lo stato cambia.

Applica esclusivamente ciò che ha superato la validazione.
Nessuna scrittura della LLM raggiunge lo stato per altre vie.
"""

from __future__ import annotations

import hashlib

from .contract import FinalScene, Mutation
from .models import MemoryEvent, Thread, WorldState, add_knowledge


class CommitError(RuntimeError):
    """Applicazione di una mutazione fallita dopo validazione."""


def _character_for(state: WorldState, target: str):
    if target == "player":
        return state.player
    return state.npcs.get(target)


def apply_mutation(state: WorldState, mutation: Mutation) -> None:
    character = _character_for(state, mutation.target)
    payload = mutation.payload

    if mutation.type == "relationship_delta":
        if mutation.target == "player":
            raise CommitError("relationship_delta richiede un NPC come target")
        npc = state.npcs[mutation.target]
        npc.relationship_towards("player").apply_delta(payload)

    elif mutation.type == "knowledge_add":
        add_knowledge(
            character,
            str(payload["fact"]),
            source=str(payload.get("source", "contextual")),
            turn=state.turn,
            credibility=float(payload.get("credibility", 1.0)),
            origin=str(payload.get("origin", mutation.reason)),
        )

    elif mutation.type == "condition_add":
        condition = str(payload["condition"])
        if condition not in character.conditions:
            character.conditions.append(condition)

    elif mutation.type == "condition_remove":
        condition = str(payload["condition"])
        if condition in character.conditions:
            character.conditions.remove(condition)

    elif mutation.type == "item_add":
        item = str(payload["item"])
        if mutation.target != "player":
            raise CommitError("item_add è supportato solo per il giocatore")
        if item not in state.player.inventory:
            state.player.inventory.append(item)

    elif mutation.type == "item_remove":
        item = str(payload["item"])
        state.player.inventory.remove(item)

    elif mutation.type == "outfit_wear":
        character.outfit.wear(str(payload["item"]))

    elif mutation.type == "outfit_remove":
        character.outfit.remove_item(str(payload["item"]))

    elif mutation.type == "wound_add":
        wound = str(payload["wound"])
        if wound not in character.wounds:
            character.wounds.append(wound)

    elif mutation.type == "location_change":
        destination = str(payload["location_id"])
        if mutation.target == "player":
            state.player.location_id = destination
            state.location_id = destination
            # la presenza degli NPC si aggiorna rispetto alla nuova scena
            for npc in state.npcs.values():
                npc.present = npc.location_id == destination
        else:
            state.npcs[mutation.target].location_id = destination

    elif mutation.type == "resource_delta":
        for key, delta in payload.items():
            state.player.resources[key] = state.player.resources.get(key, 0) + int(delta)

    elif mutation.type == "thread_open":
        thread_id = str(
            payload.get("thread_id")
            or hashlib.sha1(str(payload["summary"]).encode()).hexdigest()[:12]
        )
        state.open_thread(
            Thread(
                id=thread_id,
                type=str(payload.get("type", "question")),
                participants=[str(p) for p in payload.get("participants", ["player"])],
                summary=str(payload["summary"]),
                opened_turn=state.turn,
                close_condition=str(payload.get("close_condition", "")),
            )
        )

    elif mutation.type == "thread_close":
        state.close_thread(
            str(payload["thread_id"]),
            turn=state.turn,
            reason=str(payload.get("reason", mutation.reason)),
        )

    elif mutation.type == "discovery_add":
        evidence = str(payload["evidence"])
        if evidence not in state.discovered_evidence:
            state.discovered_evidence.append(evidence)

    elif mutation.type == "emotion_set":
        if mutation.target in state.npcs:
            state.npcs[mutation.target].emotional_state.update(
                {str(k): str(v) for k, v in payload.items()}
            )

    elif mutation.type == "intention_set":
        if mutation.target in state.npcs:
            state.npcs[mutation.target].current_intention = str(payload.get("intention", ""))

    elif mutation.type == "story_marker_add":
        from .spine import apply_story_marker

        apply_story_marker(state, str(payload["marker_id"]))

    elif mutation.type == "mission_complete":
        completed = state.flags.setdefault("mission_transitions", [])
        completed.append(
            {
                "mission_id": str(mutation.target),
                "completed_objectives": list(payload.get("completed_objectives", [])),
            }
        )

    else:  # pragma: no cover - il contratto impedisce tipi sconosciuti
        raise CommitError(f"mutazione non gestita: {mutation.type}")


def apply_scene(state: WorldState, scene: FinalScene, pack=None) -> None:
    """Applica scena validata: mutazioni, memoria, intenzioni, iniziative,
    pressioni, disclosure e scena corrente.

    `pack` è necessario per le pressioni (definite nel world-pack)."""

    for mutation in scene.mutations:
        apply_mutation(state, mutation)

    for memory in scene.memory_events:
        event = MemoryEvent(
            summary=memory.summary,
            witnesses=list(memory.witnesses),
            source=memory.source,
            turn=state.turn,
            level=memory.level,
            credibility=memory.credibility,
            emotional_impact=memory.emotional_impact,
            public=memory.public,
        )
        for witness_id in memory.witnesses:
            if witness_id in state.npcs:
                state.npcs[witness_id].memories.append(event)

    for intention in scene.intentions:
        npc_id = intention.get("npc_id", "")
        if npc_id in state.npcs:
            state.npcs[npc_id].current_intention = intention.get("intention", "")

    # iniziative autonome e pressioni
    from .initiative import apply_initiatives
    from .spine import apply_pressure_advance

    apply_initiatives(state, scene.initiatives)
    if pack is not None:
        for event in scene.initiatives:
            if event.type == "pressure_advance":
                apply_pressure_advance(pack, state, event)

    # disclosure di segreti e conoscenze
    from .disclosure import apply_disclosure

    for event in scene.disclosure_events:
        apply_disclosure(state, event)

    state.last_scene = scene.narration
