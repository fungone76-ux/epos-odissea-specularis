"""Per-NPC context contracts for passive NPC coordination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from epos.npc_agent_models import NpcAgentState, validate_canonical_npc_id
from epos.npc_memory_long import NpcLongMemory
from epos.npc_memory_short import NpcShortMemory


def _refs(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        iterable = (values,)
    else:
        iterable = values
    result: list[str] = []
    seen: set[str] = set()
    for value in iterable:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)


def _short_memories(values: Any) -> tuple[NpcShortMemory, ...]:
    if values is None:
        return ()
    result: list[NpcShortMemory] = []
    for value in values:
        if isinstance(value, NpcShortMemory):
            result.append(value)
        elif isinstance(value, dict):
            result.append(NpcShortMemory.from_dict(value))
        else:
            raise ValueError("selected_short_memories must contain short memories or dictionaries")
    return tuple(result)


def _long_memories(values: Any) -> tuple[NpcLongMemory, ...]:
    if values is None:
        return ()
    result: list[NpcLongMemory] = []
    for value in values:
        if isinstance(value, NpcLongMemory):
            result.append(value)
        elif isinstance(value, dict):
            result.append(NpcLongMemory.from_dict(value))
        else:
            raise ValueError("selected_long_memories must contain long memories or dictionaries")
    return tuple(result)


@dataclass(frozen=True)
class NpcAgentContext:
    npc_id: str
    persona_summary: str = ""
    current_goal: str = ""
    current_intention: str = ""
    emotion: str = ""
    relationship_refs: tuple[str, ...] = ()
    knowledge_refs: tuple[str, ...] = ()
    open_thread_ids: tuple[str, ...] = ()
    mission_refs: tuple[str, ...] = ()
    selected_short_memories: tuple[NpcShortMemory, ...] = ()
    selected_long_memories: tuple[NpcLongMemory, ...] = ()
    initiative_priority: int = 0
    next_evaluation_turn: int = 0
    selection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "npc_id", validate_canonical_npc_id(self.npc_id))
        object.__setattr__(self, "persona_summary", str(self.persona_summary or "").strip())
        object.__setattr__(self, "current_goal", str(self.current_goal or "").strip())
        object.__setattr__(self, "current_intention", str(self.current_intention or "").strip())
        object.__setattr__(self, "emotion", str(self.emotion or "").strip())
        object.__setattr__(self, "relationship_refs", _refs(self.relationship_refs))
        object.__setattr__(self, "knowledge_refs", _refs(self.knowledge_refs))
        object.__setattr__(self, "open_thread_ids", _refs(self.open_thread_ids))
        object.__setattr__(self, "mission_refs", _refs(self.mission_refs))
        object.__setattr__(self, "selected_short_memories", _short_memories(self.selected_short_memories))
        object.__setattr__(self, "selected_long_memories", _long_memories(self.selected_long_memories))
        priority = int(self.initiative_priority)
        if priority < 0 or priority > 100:
            raise ValueError("initiative_priority must be between 0 and 100")
        object.__setattr__(self, "initiative_priority", priority)
        next_turn = int(self.next_evaluation_turn)
        if next_turn < 0:
            raise ValueError("next_evaluation_turn must be non-negative")
        object.__setattr__(self, "next_evaluation_turn", next_turn)
        object.__setattr__(self, "selection_reasons", _refs(self.selection_reasons))

    def to_dict(self) -> dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "persona_summary": self.persona_summary,
            "current_goal": self.current_goal,
            "current_intention": self.current_intention,
            "emotion": self.emotion,
            "relationship_refs": list(self.relationship_refs),
            "knowledge_refs": list(self.knowledge_refs),
            "open_thread_ids": list(self.open_thread_ids),
            "mission_refs": list(self.mission_refs),
            "selected_short_memories": [memory.to_dict() for memory in self.selected_short_memories],
            "selected_long_memories": [memory.to_dict() for memory in self.selected_long_memories],
            "initiative_priority": self.initiative_priority,
            "next_evaluation_turn": self.next_evaluation_turn,
            "selection_reasons": list(self.selection_reasons),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NpcAgentContext":
        return cls(
            npc_id=data.get("npc_id", ""),
            persona_summary=data.get("persona_summary", ""),
            current_goal=data.get("current_goal", ""),
            current_intention=data.get("current_intention", ""),
            emotion=data.get("emotion", ""),
            relationship_refs=tuple(data.get("relationship_refs", ())),
            knowledge_refs=tuple(data.get("knowledge_refs", ())),
            open_thread_ids=tuple(data.get("open_thread_ids", ())),
            mission_refs=tuple(data.get("mission_refs", ())),
            selected_short_memories=tuple(data.get("selected_short_memories", ())),
            selected_long_memories=tuple(data.get("selected_long_memories", ())),
            initiative_priority=int(data.get("initiative_priority", 0)),
            next_evaluation_turn=int(data.get("next_evaluation_turn", 0)),
            selection_reasons=tuple(data.get("selection_reasons", ())),
        )

    @classmethod
    def from_agent_state(
        cls,
        state: NpcAgentState,
        *,
        selected_short_memories: tuple[NpcShortMemory, ...] = (),
        selected_long_memories: tuple[NpcLongMemory, ...] = (),
        selection_reasons: tuple[str, ...] = (),
    ) -> "NpcAgentContext":
        return cls(
            npc_id=state.npc_id,
            persona_summary=state.persona_summary,
            current_goal=state.current_goal,
            current_intention=state.current_intention,
            emotion=state.emotion,
            relationship_refs=state.relationship_refs,
            knowledge_refs=state.knowledge_refs,
            open_thread_ids=state.open_thread_ids,
            mission_refs=state.mission_refs,
            selected_short_memories=selected_short_memories,
            selected_long_memories=selected_long_memories,
            initiative_priority=state.initiative_priority,
            next_evaluation_turn=state.next_evaluation_turn,
            selection_reasons=selection_reasons,
        )

    def to_llm_context_dict(self) -> dict[str, Any]:
        """Structural payload for a future single multi-agent LLM call."""

        return {
            "npc_id": self.npc_id,
            "goal": self.current_goal,
            "intention": self.current_intention,
            "emotion": self.emotion,
            "relationships": list(self.relationship_refs),
            "knowledge_refs": list(self.knowledge_refs),
            "open_threads": list(self.open_thread_ids),
            "missions": list(self.mission_refs),
            "short_memories": [memory.to_dict() for memory in self.selected_short_memories],
            "long_memories": [memory.to_dict() for memory in self.selected_long_memories],
        }
