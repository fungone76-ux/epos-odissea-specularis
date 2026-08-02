"""Contracts for optional dedicated NPC LLM calls.

These structures are passive data contracts. They do not call providers and
cannot represent authoritative world mutations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from epos.npc_agent_context import NpcAgentContext
from epos.npc_agent_models import validate_canonical_npc_id


MAX_TEXT_LENGTH = 500


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


def _text(value: Any, *, max_length: int = MAX_TEXT_LENGTH) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise ValueError(f"text field exceeds {max_length} characters")
    return text


@dataclass(frozen=True)
class NpcDedicatedLlmBudget:
    max_calls_per_turn: int = 1
    max_agents_per_call: int = 3

    def __post_init__(self) -> None:
        calls = int(self.max_calls_per_turn)
        agents = int(self.max_agents_per_call)
        if calls < 0:
            raise ValueError("max_calls_per_turn must be non-negative")
        if calls > 1:
            raise ValueError("max_calls_per_turn cannot exceed 1")
        if agents < 0:
            raise ValueError("max_agents_per_call must be non-negative")
        object.__setattr__(self, "max_calls_per_turn", calls)
        object.__setattr__(self, "max_agents_per_call", agents)

    def to_dict(self) -> dict[str, int]:
        return {
            "max_calls_per_turn": self.max_calls_per_turn,
            "max_agents_per_call": self.max_agents_per_call,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NpcDedicatedLlmBudget":
        if not data:
            return cls()
        return cls(
            max_calls_per_turn=int(data.get("max_calls_per_turn", 1)),
            max_agents_per_call=int(data.get("max_agents_per_call", 3)),
        )


@dataclass(frozen=True)
class NpcDedicatedLlmRequest:
    turn: int
    location_id: str
    player_input: str
    agents: tuple[NpcAgentContext, ...] = ()

    def __post_init__(self) -> None:
        turn = int(self.turn)
        if turn < 0:
            raise ValueError("turn must be non-negative")
        object.__setattr__(self, "turn", turn)
        object.__setattr__(self, "location_id", str(self.location_id or "").strip())
        object.__setattr__(self, "player_input", _text(self.player_input, max_length=1000))
        agents: list[NpcAgentContext] = []
        for agent in self.agents:
            if not isinstance(agent, NpcAgentContext):
                agent = NpcAgentContext.from_dict(agent)  # type: ignore[arg-type]
            agents.append(agent)
        object.__setattr__(self, "agents", tuple(agents))

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "location_id": self.location_id,
            "player_input": self.player_input,
            "agents": [agent.to_dict() for agent in self.agents],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NpcDedicatedLlmRequest":
        return cls(
            turn=int(data.get("turn", 0)),
            location_id=data.get("location_id", ""),
            player_input=data.get("player_input", ""),
            agents=tuple(NpcAgentContext.from_dict(agent) for agent in data.get("agents", ())),
        )


@dataclass(frozen=True)
class NpcLlmProposal:
    npc_id: str
    stance: str = ""
    intention_hint: str = ""
    emotional_reaction: str = ""
    response_priority: int = 0
    referenced_memory_ids: tuple[str, ...] = ()
    dialogue_hint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "npc_id", validate_canonical_npc_id(self.npc_id))
        object.__setattr__(self, "stance", _text(self.stance))
        object.__setattr__(self, "intention_hint", _text(self.intention_hint))
        object.__setattr__(self, "emotional_reaction", _text(self.emotional_reaction))
        priority = int(self.response_priority)
        if priority < 0 or priority > 100:
            raise ValueError("response_priority must be between 0 and 100")
        object.__setattr__(self, "response_priority", priority)
        object.__setattr__(self, "referenced_memory_ids", _refs(self.referenced_memory_ids))
        object.__setattr__(self, "dialogue_hint", _text(self.dialogue_hint))

    def to_dict(self) -> dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "stance": self.stance,
            "intention_hint": self.intention_hint,
            "emotional_reaction": self.emotional_reaction,
            "response_priority": self.response_priority,
            "referenced_memory_ids": list(self.referenced_memory_ids),
            "dialogue_hint": self.dialogue_hint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NpcLlmProposal":
        return cls(
            npc_id=data.get("npc_id", ""),
            stance=data.get("stance", ""),
            intention_hint=data.get("intention_hint", ""),
            emotional_reaction=data.get("emotional_reaction", ""),
            response_priority=int(data.get("response_priority", 0)),
            referenced_memory_ids=tuple(data.get("referenced_memory_ids", ())),
            dialogue_hint=data.get("dialogue_hint", ""),
        )


@dataclass(frozen=True)
class NpcDedicatedLlmResponse:
    proposals: tuple[NpcLlmProposal, ...] = ()

    def __post_init__(self) -> None:
        proposals: list[NpcLlmProposal] = []
        for proposal in self.proposals:
            if not isinstance(proposal, NpcLlmProposal):
                proposal = NpcLlmProposal.from_dict(proposal)  # type: ignore[arg-type]
            proposals.append(proposal)
        object.__setattr__(self, "proposals", tuple(proposals))

    def to_dict(self) -> dict[str, Any]:
        return {"proposals": [proposal.to_dict() for proposal in self.proposals]}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NpcDedicatedLlmResponse":
        if not data:
            return cls()
        return cls(tuple(NpcLlmProposal.from_dict(item) for item in data.get("proposals", ())))


@dataclass(frozen=True)
class NpcDedicatedLlmRunResult:
    status: str
    response: NpcDedicatedLlmResponse = field(default_factory=NpcDedicatedLlmResponse)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "response": self.response.to_dict(),
            "diagnostics": dict(self.diagnostics),
        }

