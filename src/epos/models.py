"""Modelli di stato canonici di epos.

Autorità: questi dataclasses sono l'unica fonte di verità persistente.
La LLM non li modifica mai direttamente: propone mutazioni che il runtime
valida e applica.

Layer 0 del motore: nessuna dipendenza da altri moduli epos.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, AbstractSet

MEMORY_LEVELS = ("immediate", "relational", "durable")
KNOWLEDGE_SOURCES = ("observed", "told", "deduced", "public", "secret", "contextual")


@dataclass
class KnowledgeEntry:
    fact: str
    source: str
    turn: int
    credibility: float = 1.0
    origin: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeEntry":
        return cls(
            fact=str(data.get("fact", "")),
            source=str(data.get("source", "contextual")),
            turn=int(data.get("turn", 0)),
            credibility=float(data.get("credibility", 1.0)),
            origin=str(data.get("origin", "")),
        )


def add_knowledge(character, fact: str, *, source: str, turn: int, credibility: float = 1.0, origin: str = "") -> None:
    fact = str(fact).strip()
    if not fact or not hasattr(character, "knowledge"):
        return
    if fact not in character.knowledge:
        character.knowledge.append(fact)
    if hasattr(character, "knowledge_log") and not any(entry.fact == fact for entry in character.knowledge_log):
        character.knowledge_log.append(
            KnowledgeEntry(
                fact=fact,
                source=source if source in KNOWLEDGE_SOURCES else "contextual",
                turn=int(turn),
                credibility=max(0.0, min(1.0, float(credibility))),
                origin=str(origin),
            )
        )


@dataclass
class MemoryEvent:
    summary: str
    witnesses: list[str]
    source: str
    turn: int
    level: str = "immediate"
    credibility: float = 1.0
    emotional_impact: int = 0
    public: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEvent":
        return cls(**data)


RELATIONSHIP_DOMAINS = (
    "trust",
    "fear",
    "attraction",
    "resentment",
    "dependency",
    "respect",
    "suspicion",
)


@dataclass
class Relationship:
    trust: int = 0
    fear: int = 0
    attraction: int = 0
    resentment: int = 0
    dependency: int = 0
    respect: int = 0
    suspicion: int = 0

    def apply_delta(self, deltas: dict[str, int]) -> None:
        for domain, delta in deltas.items():
            if domain not in RELATIONSHIP_DOMAINS:
                raise ValueError(f"Dominio di relazione sconosciuto: {domain}")
            value = getattr(self, domain) + int(delta)
            setattr(self, domain, max(-100, min(100, value)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relationship":
        return cls(**data)


@dataclass
class Thread:
    id: str
    type: str
    participants: list[str]
    summary: str
    opened_turn: int
    status: str = "open"
    close_condition: str = ""
    closed_turn: int | None = None
    close_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Thread":
        data = dict(data)
        data.setdefault("close_condition", "")
        data.setdefault("closed_turn", None)
        data.setdefault("close_reason", "")
        return cls(**data)


@dataclass
class Outfit:
    worn: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    revision: int = 0

    def wear(self, item: str) -> None:
        if item in self.removed:
            self.removed.remove(item)
        if item not in self.worn:
            self.worn.append(item)
        self.revision += 1

    def remove_item(self, item: str) -> None:
        if item in self.worn:
            self.worn.remove(item)
        if item not in self.removed:
            self.removed.append(item)
        self.revision += 1

    def to_dict(self) -> dict[str, Any]:
        state = outfit_state(self)
        return {
            "worn": list(self.worn),
            "removed": list(self.removed),
            "revision": self.revision,
            "torso_slot": list(state["torso_slot"]),
            "lower_body_slot": list(state["lower_body_slot"]),
            "footwear": list(state["footwear"]),
            "nudity_mode": state["nudity_mode"],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Outfit":
        return cls(
            worn=[str(item) for item in data.get("worn", [])],
            removed=[str(item) for item in data.get("removed", [])],
            revision=int(data.get("revision", 0)),
        )


TORSO_CLOTHING_TERMS = frozenset({
    "armor", "breastplate", "chest wrap", "chiton", "cloak", "corselet", "dress",
    "himation", "leather armor", "peplos", "pelt", "pelts", "robe", "shirt", "top",
    "tunic", "wrap", "armatura", "chitone", "mantello", "tunica", "bikini", "blazer",
    "bodysuit", "bra", "camisole", "corset", "lingerie", "one piece", "slip", "suit",
    "swimsuit", "swimwear", "uniform",
})

LOWER_CLOTHING_TERMS = frozenset({
    "chiton", "dress", "himation", "kilt", "loincloth", "pants", "peplos", "pelt",
    "pelts", "robe", "shorts", "skirt", "tunic", "chitone", "tunica", "vestito",
    "bikini", "bottoms", "briefs", "lingerie", "micro dress", "mini dress", "one piece",
    "panties", "sarong", "slip", "suit", "swimsuit", "swimwear", "uniform",
})

FOOTWEAR_TERMS = frozenset({
    "boots", "greaves", "sandals", "shoes", "sandali", "scarpe", "stivali",
    "heels", "loafers", "pumps", "stilettos", "wedges",
})


def _contains_clothing_term(text: str, terms: AbstractSet[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def outfit_state(outfit: Outfit) -> dict[str, Any]:
    worn = [str(item) for item in outfit.worn]
    torso = [item for item in worn if _contains_clothing_term(item, TORSO_CLOTHING_TERMS)]
    lower = [item for item in worn if _contains_clothing_term(item, LOWER_CLOTHING_TERMS)]
    footwear = [item for item in worn if _contains_clothing_term(item, FOOTWEAR_TERMS)]
    if not torso and not lower:
        nudity_mode = "fully_nude"
    elif not torso:
        nudity_mode = "topless"
    elif not lower:
        nudity_mode = "bottomless"
    else:
        nudity_mode = "clothed"
    return {
        "worn_items": worn,
        "removed_items": [str(item) for item in outfit.removed],
        "torso_slot": torso,
        "lower_body_slot": lower,
        "footwear": footwear,
        "nudity_mode": nudity_mode,
        "revision": outfit.revision,
        "source_of_truth": "character.outfit",
    }


MAX_SKILL_RATING = 5
CREATION_SKILL_BUDGET = 6


@dataclass
class PlayerState:
    name: str | None
    location_id: str
    adult_age: bool = True
    skills: dict[str, int] = field(default_factory=dict)
    talent: str | None = None
    trigger: str | None = None
    identity: str = ""
    appearance: str = ""
    inventory: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    outfit: Outfit = field(default_factory=Outfit)
    wounds: list[str] = field(default_factory=list)
    resources: dict[str, int] = field(default_factory=dict)
    knowledge: list[str] = field(default_factory=list)
    knowledge_log: list[KnowledgeEntry] = field(default_factory=list)

    def skill_rating(self, skill: str) -> int:
        return max(0, min(MAX_SKILL_RATING, int(self.skills.get(skill, 0))))

    def best_skill_rating(self, candidates: list[str]) -> tuple[str | None, int]:
        rated = [(s, self.skill_rating(s)) for s in candidates if self.skill_rating(s) > 0]
        if not rated:
            return None, 0
        return max(rated, key=lambda item: item[1])

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "location_id": self.location_id,
            "adult_age": self.adult_age,
            "skills": dict(self.skills),
            "talent": self.talent,
            "trigger": self.trigger,
            "identity": self.identity,
            "appearance": self.appearance,
            "inventory": list(self.inventory),
            "conditions": list(self.conditions),
            "outfit": self.outfit.to_dict(),
            "wounds": list(self.wounds),
            "resources": dict(self.resources),
            "knowledge": list(self.knowledge),
            "knowledge_log": [k.to_dict() for k in self.knowledge_log],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayerState":
        data = dict(data)
        data["outfit"] = Outfit.from_dict(data.get("outfit", {}))
        data["knowledge_log"] = [KnowledgeEntry.from_dict(k) for k in data.get("knowledge_log", [])]
        return cls(**data)


@dataclass
class NpcState:
    id: str
    name: str
    age: int
    location_id: str
    present: bool = False
    knowledge: list[str] = field(default_factory=list)
    knowledge_log: list[KnowledgeEntry] = field(default_factory=list)
    memories: list[MemoryEvent] = field(default_factory=list)
    relationships: dict[str, Relationship] = field(default_factory=dict)
    emotional_state: dict[str, str] = field(default_factory=dict)
    current_intention: str = ""
    conditions: list[str] = field(default_factory=list)
    outfit: Outfit = field(default_factory=Outfit)
    wounds: list[str] = field(default_factory=list)
    disclosed_facts: list[str] = field(default_factory=list)

    def relationship_towards(self, character_id: str) -> Relationship:
        return self.relationships.setdefault(character_id, Relationship())

    def knows(self, fact: str) -> bool:
        return fact in self.knowledge

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "location_id": self.location_id,
            "present": self.present,
            "knowledge": list(self.knowledge),
            "knowledge_log": [k.to_dict() for k in self.knowledge_log],
            "memories": [m.to_dict() for m in self.memories],
            "relationships": {k: v.to_dict() for k, v in self.relationships.items()},
            "emotional_state": dict(self.emotional_state),
            "current_intention": self.current_intention,
            "conditions": list(self.conditions),
            "outfit": self.outfit.to_dict(),
            "wounds": list(self.wounds),
            "disclosed_facts": list(self.disclosed_facts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NpcState":
        data = dict(data)
        data["knowledge_log"] = [KnowledgeEntry.from_dict(k) for k in data.get("knowledge_log", [])]
        data["memories"] = [MemoryEvent.from_dict(m) for m in data.get("memories", [])]
        data["relationships"] = {k: Relationship.from_dict(v) for k, v in data.get("relationships", {}).items()}
        data["outfit"] = Outfit.from_dict(data.get("outfit", {}))
        return cls(**data)


@dataclass
class InitiativeState:
    consecutive_reactive_turns: int = 0
    last_autonomous_turn: int = -1
    recent: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InitiativeState":
        return cls(**data)


@dataclass
class PressureState:
    level: int = 0
    last_advanced_turn: int = -1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PressureState":
        return cls(**data)


@dataclass
class WorldState:
    session_id: str
    turn: int
    time_phase: str
    location_id: str
    player: PlayerState
    npcs: dict[str, NpcState] = field(default_factory=dict)
    active_threads: list[Thread] = field(default_factory=list)
    discovered_evidence: list[str] = field(default_factory=list)
    story_markers: list[str] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    initiative: InitiativeState = field(default_factory=InitiativeState)
    pressures: dict[str, PressureState] = field(default_factory=dict)
    riserva: int = 0
    last_scene: str = ""

    def present_npc_ids(self) -> list[str]:
        return [npc.id for npc in self.npcs.values() if npc.present]

    def present_character_ids(self) -> list[str]:
        return ["player", *self.present_npc_ids()]

    def is_present(self, character_id: str) -> bool:
        if character_id == "player":
            return True
        npc = self.npcs.get(character_id)
        return bool(npc and npc.present)

    def open_thread(self, thread: Thread) -> None:
        if any(t.id == thread.id for t in self.active_threads):
            return
        self.active_threads.append(thread)

    def close_thread(self, thread_id: str, *, turn: int | None = None, reason: str = "") -> None:
        for thread in self.active_threads:
            if thread.id == thread_id:
                thread.status = "closed"
                thread.closed_turn = self.turn if turn is None else int(turn)
                thread.close_reason = str(reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn": self.turn,
            "time_phase": self.time_phase,
            "location_id": self.location_id,
            "player": self.player.to_dict(),
            "npcs": {k: v.to_dict() for k, v in self.npcs.items()},
            "active_threads": [t.to_dict() for t in self.active_threads],
            "discovered_evidence": list(self.discovered_evidence),
            "story_markers": list(self.story_markers),
            "flags": dict(self.flags),
            "initiative": self.initiative.to_dict(),
            "pressures": {k: v.to_dict() for k, v in self.pressures.items()},
            "riserva": self.riserva,
            "last_scene": self.last_scene,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldState":
        return cls(
            session_id=data["session_id"],
            turn=data["turn"],
            time_phase=data["time_phase"],
            location_id=data["location_id"],
            player=PlayerState.from_dict(data["player"]),
            npcs={k: NpcState.from_dict(v) for k, v in data.get("npcs", {}).items()},
            active_threads=[Thread.from_dict(t) for t in data.get("active_threads", [])],
            discovered_evidence=list(data.get("discovered_evidence", [])),
            story_markers=list(data.get("story_markers", [])),
            flags=dict(data.get("flags", {})),
            initiative=InitiativeState.from_dict(data.get("initiative", {})),
            pressures={k: PressureState.from_dict(v) for k, v in data.get("pressures", {}).items()},
            riserva=int(data.get("riserva", 0)),
            last_scene=data.get("last_scene", ""),
        )
