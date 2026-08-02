"""Deterministic registry and bootstrap for NPC agent states."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .models import WorldState
from .npc_agent_models import NpcAgentState, validate_canonical_npc_id
from .worldpack import WorldPack


@dataclass(frozen=True)
class NpcAgentRegistry:
    _agents: tuple[NpcAgentState, ...] = ()

    def __post_init__(self) -> None:
        seen: set[str] = set()
        agents: list[NpcAgentState] = []
        for state in self._agents:
            if not isinstance(state, NpcAgentState):
                state = NpcAgentState.from_dict(state)  # type: ignore[arg-type]
            if state.npc_id in seen:
                raise ValueError(f"duplicate NPC agent id: {state.npc_id}")
            seen.add(state.npc_id)
            agents.append(state)
        object.__setattr__(self, "_agents", tuple(agents))

    def get(self, npc_id: str) -> NpcAgentState | None:
        canonical = validate_canonical_npc_id(npc_id)
        for state in self._agents:
            if state.npc_id == canonical:
                return state
        return None

    def contains(self, npc_id: str) -> bool:
        return self.get(npc_id) is not None

    def upsert(self, state: NpcAgentState) -> "NpcAgentRegistry":
        updated: list[NpcAgentState] = []
        replaced = False
        for existing in self._agents:
            if existing.npc_id == state.npc_id:
                updated.append(state)
                replaced = True
            else:
                updated.append(existing)
        if not replaced:
            updated.append(state)
        return NpcAgentRegistry(tuple(updated))

    def remove(self, npc_id: str) -> "NpcAgentRegistry":
        canonical = validate_canonical_npc_id(npc_id)
        return NpcAgentRegistry(tuple(state for state in self._agents if state.npc_id != canonical))

    def all(self) -> tuple[NpcAgentState, ...]:
        return self._agents

    def enabled(self) -> tuple[NpcAgentState, ...]:
        return tuple(state for state in self._agents if state.enabled)


    def upsert_short_memory(self, memory, *, current_turn: int, policy=None) -> "NpcAgentRegistry":
        agent = self.get(memory.npc_id)
        if agent is None:
            raise ValueError(f"unknown NPC agent id: {memory.npc_id}")
        from .npc_memory_policy import NpcShortMemoryPolicy
        from .npc_memory_short import prune_short_memories

        effective_policy = policy or NpcShortMemoryPolicy()
        memories = prune_short_memories(
            tuple(agent.short_memories) + (memory,),
            current_turn=int(current_turn),
            policy=effective_policy,
        )
        return self.upsert(replace(agent, short_memories=memories))

    def remove_short_memory(self, npc_id: str, memory_id: str) -> "NpcAgentRegistry":
        agent = self.get(npc_id)
        if agent is None:
            raise ValueError(f"unknown NPC agent id: {npc_id}")
        target = str(memory_id or "").strip()
        memories = tuple(memory for memory in agent.short_memories if memory.memory_id != target)
        return self.upsert(replace(agent, short_memories=memories))
    def to_dict(self) -> dict[str, Any]:
        return {"agents": [state.to_dict() for state in self._agents]}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NpcAgentRegistry":
        if not data:
            return cls()
        return cls(tuple(NpcAgentState.from_dict(item) for item in data.get("agents", [])))


def build_npc_agent_state(world_state: WorldState, npc_id: str, world_pack: WorldPack | None = None) -> NpcAgentState:
    canonical = validate_canonical_npc_id(npc_id)
    npc = world_state.npcs.get(canonical)
    if npc is None:
        raise ValueError(f"unknown NPC id: {canonical}")
    canon = world_pack.npc_canon.get(canonical) if world_pack is not None else None
    persona_summary = "; ".join(canon.personality) if canon is not None else ""
    current_goal = canon.goals[0] if canon is not None and canon.goals else ""
    emotion = str(npc.emotional_state.get("mood", "") or npc.emotional_state.get("primary", ""))
    relationship_refs = tuple(f"{canonical}:{target_id}" for target_id in npc.relationships)
    knowledge_refs = tuple(f"{canonical}:knowledge:{index}" for index, _entry in enumerate(npc.knowledge_log or npc.knowledge))
    open_thread_ids = tuple(
        thread.id
        for thread in world_state.active_threads
        if thread.status == "open" and canonical in thread.participants
    )
    mission_refs = _mission_refs_for_npc(canonical, world_state, world_pack)
    return NpcAgentState(
        npc_id=canonical,
        persona_summary=persona_summary,
        current_goal=current_goal,
        current_intention=npc.current_intention,
        emotion=emotion,
        relationship_refs=relationship_refs,
        knowledge_refs=knowledge_refs,
        open_thread_ids=open_thread_ids,
        mission_refs=mission_refs,
        next_evaluation_turn=world_state.turn,
    )


def bootstrap_npc_agent_registry(world_state: WorldState, world_pack: WorldPack | None = None) -> NpcAgentRegistry:
    registry = NpcAgentRegistry()
    for npc_id in world_state.npcs:
        registry = registry.upsert(build_npc_agent_state(world_state, npc_id, world_pack))
    return registry


def _mission_refs_for_npc(npc_id: str, world_state: WorldState, world_pack: WorldPack | None) -> tuple[str, ...]:
    if world_pack is None:
        return ()
    refs: list[str] = []
    for mission in world_pack.missions.values():
        if mission.location_id != world_state.npcs[npc_id].location_id:
            continue
        if _mission_mentions_npc_id(mission.to_dict() if hasattr(mission, "to_dict") else mission.__dict__, npc_id):
            refs.append(mission.id)
    return tuple(refs)


def _mission_mentions_npc_id(data: Any, npc_id: str) -> bool:
    if isinstance(data, dict):
        return any(_mission_mentions_npc_id(value, npc_id) for value in data.values())
    if isinstance(data, (list, tuple)):
        return any(_mission_mentions_npc_id(value, npc_id) for value in data)
    return data == npc_id
