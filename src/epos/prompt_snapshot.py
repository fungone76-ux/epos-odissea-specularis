"""Canonical prompt snapshot construction."""

from __future__ import annotations

from typing import Any

from .models import WorldState, outfit_state
from .narrative_policy import derive_narrative_policy
from .worldpack import WorldPack


def build_snapshot(
    state: WorldState,
    pack: WorldPack,
    player_text: str,
) -> dict[str, Any]:
    """Snapshot minimo e compatto dello stato per il turno corrente."""

    snapshot = _build_full_snapshot(state, pack, player_text)
    from .context_selector import (
        ContextSelectionRequest,
        context_selector_enabled,
        select_context,
    )

    if not context_selector_enabled():
        return snapshot
    result = select_context(
        ContextSelectionRequest(
            world_state=state,
            world_pack=pack,
            player_input=player_text,
            phase="snapshot",
            full_snapshot=snapshot,
        )
    )
    return result.selected_snapshot


def _build_full_snapshot(
    state: WorldState,
    pack: WorldPack,
    player_text: str,
) -> dict[str, Any]:
    """Build the legacy full snapshot before optional context selection."""

    location = pack.locations.get(state.location_id)
    from .disclosure import disclosure_context
    from .initiative import initiative_context
    from .spine import pressure_context, spine_context

    present_npcs = []
    for npc_id in state.present_npc_ids():
        npc = state.npcs[npc_id]
        canon = pack.npc_canon.get(npc_id)
        present_npcs.append(
            {
                "id": npc.id,
                "name": npc.name,
                "personality": canon.personality if canon else [],
                "speech_style": canon.speech_style if canon else "",
                "goals": canon.goals if canon else [],
                "knowledge": npc.knowledge,
                "knowledge_provenance": [
                    k.to_dict() for k in npc.knowledge_log[-5:]
                ],
                "disclosure": disclosure_context(state, pack, npc_id),
                "current_intention": npc.current_intention,
                "emotional_state": npc.emotional_state,
                "relationship_towards_player": npc.relationships.get("player") and {
                    k: v
                    for k, v in npc.relationships["player"].to_dict().items()
                    if v != 0
                },
                "conditions": npc.conditions,
                "outfit_worn": npc.outfit.worn,
                "outfit_removed": npc.outfit.removed,
                "outfit_state": outfit_state(npc.outfit),
                "wounds": npc.wounds,
                "recent_memories": [m.summary for m in npc.memories[-5:]],
            }
        )

    narrative_policy = derive_narrative_policy(state, pack, player_text, phase="snapshot")

    return {
        "premise": pack.premise,
        "turn": state.turn,
        "time_phase": state.time_phase,
        "world_facts": [
            {
                "statement": f.statement,
                "visibility": f.visibility,
                "does_not_imply": f.does_not_imply,
            }
            for f in pack.world_facts.values()
        ],
        "npc_relationships": [
            {
                "from": r.from_id,
                "to": r.to_id,
                "statement": r.statement,
                "known_by": r.known_by,
                "forbidden_inferences": r.forbidden_inferences,
            }
            for r in pack.relationships
        ],
        "location": {
            "id": state.location_id,
            "name": location.name if location else state.location_id,
            "description": location.description if location else "",
        },
        "visual_style": pack.visual_style_en,
        "visual_policy": pack.visual_policy.__dict__,
        "player": {
            "name": state.player.name,
            "skills": state.player.skills,
            "conditions": state.player.conditions,
            "inventory": state.player.inventory,
            "outfit_worn": state.player.outfit.worn,
            "outfit_removed": state.player.outfit.removed,
            "outfit_state": outfit_state(state.player.outfit),
            "wounds": state.player.wounds,
            "resources": state.player.resources,
        },
        "present_npcs": present_npcs,
        "active_threads": [
            {
                "id": t.id,
                "type": t.type,
                "summary": t.summary,
                "participants": t.participants,
                "opened_turn": t.opened_turn,
                "close_condition": t.close_condition,
            }
            for t in state.active_threads
            if t.status == "open"
        ],
        "story_spine": spine_context(pack, state),
        "pressures": pressure_context(pack, state),
        "missions": _mission_context(pack, state),
        "initiative_rhythm": initiative_context(state),
        "narrative_policy": narrative_policy.to_dict(),
        "player_knowledge": list(state.player.knowledge),
        "player_knowledge_provenance": [
            k.to_dict() for k in state.player.knowledge_log[-8:]
        ],
        "last_scene": state.last_scene,
        "player_input": player_text,
    }


def _mission_context(pack: WorldPack, state: WorldState) -> dict[str, Any]:
    """Missioni rilevanti per il turno, senza serializzare tutto il world-pack."""

    def item(mission) -> dict[str, Any]:
        return {
            "id": mission.id,
            "location_id": mission.location_id,
            "name": mission.name,
            "description": mission.description,
            "prerequisites": list(mission.prerequisites),
            "state": mission.state,
            "objectives": [dict(v) for v in mission.objectives],
            "success_conditions": [dict(v) for v in mission.success_conditions],
            "failure_conditions": [dict(v) for v in mission.failure_conditions],
            "rewards": [dict(v) for v in mission.rewards],
            "consequences": [dict(v) for v in mission.consequences],
            "transitions": [dict(v) for v in mission.transitions],
            "alternative_solutions": [dict(v) for v in mission.alternative_solutions],
        }

    current = [m for m in pack.missions.values() if m.location_id == state.location_id]
    next_locations = {
        str(t.get("location_id", ""))
        for mission in current
        for t in mission.transitions
        if t.get("location_id") and t.get("location_id") != state.location_id
    }
    upcoming = [
        m for m in pack.missions.values()
        if m.location_id in next_locations and m.location_id != state.location_id
    ]
    return {
        "current": [item(m) for m in current],
        "upcoming": [item(m) for m in upcoming],
    }


def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Riduce lo snapshot per provider con limiti di contesto (es. z.ai)."""
    compact: dict[str, Any] = {}
    for key, value in snapshot.items():
        if key in ("npc_relationships", "visual_policy"):
            continue
        if key == "present_npcs":
            compact_npcs: list[dict[str, Any]] = []
            for npc in value:
                cnpc: dict[str, Any] = {}
                for k, v in npc.items():
                    if v in (None, {}, [], ""):
                        continue
                    cnpc[k] = v
                compact_npcs.append(cnpc)
            compact[key] = compact_npcs
            continue
        if key == "player":
            compact_player: dict[str, Any] = {}
            for k, v in value.items():
                if v in (None, {}, [], ""):
                    continue
                compact_player[k] = v
            compact[key] = compact_player
            continue
        if key == "world_facts":
            compact_facts: list[dict[str, Any]] = []
            for fact in value:
                cfact = {k: v for k, v in fact.items() if v not in (None, {}, [], "")}
                compact_facts.append(cfact)
            compact[key] = compact_facts
            continue
        compact[key] = value
    return compact
