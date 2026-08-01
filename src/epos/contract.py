"""Contratto di comunicazione con il Game Master LLM.

Un solo formato, nessuna ereditÃ  legacy:

Fase 1 â€” il GM risponde all'input del giocatore con:
    {"mode": "no_check", "scene": {...}}                    una sola chiamata
    {"mode": "check_proposal", "check": {...}}              poi si tira e si ripassa

Fase 2 â€” solo dopo la risoluzione Python, il GM riceve esito autorevole
e restituisce la scena finale nello stesso formato "scene".

La LLM non tira dadi, non sceglie esiti, non applica mutazioni.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .rules import OUTCOME_ORDER, Outcome
from .models import KNOWLEDGE_SOURCES
from .schemas import (
    SchemaError,
    validate_check_proposal_shape,
    validate_final_scene_shape,
    validate_gm_phase_response_shape,
    validate_visual_moment_shape,
)

# Azioni canoniche riconosciute dal runtime.
ACTION_KINDS = (
    "physical",
    "social",
    "stealth",
    "investigate",
    "intimate",
    "power",
)

OPPOSITION_TYPES = ("none", "npc_resistance", "environment", "self")

MUTATION_TYPES = (
    "relationship_delta",
    "knowledge_add",
    "condition_add",
    "condition_remove",
    "item_add",
    "item_remove",
    "outfit_wear",
    "outfit_remove",
    "wound_add",
    "location_change",
    "resource_delta",
    "thread_open",
    "thread_close",
    "discovery_add",
    "emotion_set",
    "intention_set",
    "story_marker_add",
    "mission_complete",
)

# Iniziative autonome degli NPC (e del mondo) durante la scena.
INITIATIVE_TYPES = (
    "interrupt",
    "question",
    "demand",
    "warn",
    "offer",
    "bargain",
    "reveal",
    "conceal",
    "threaten",
    "assist",
    "change_tactic",
    "environmental_event",
    "pressure_advance",
    "other",
)

INITIATIVE_TYPE_ALIASES = {
    "warning": "warn",
    "alert": "warn",
    "deflect": "change_tactic",
    "support_warning": "assist",
}

# Fonti mondiali valide per iniziative non di un NPC specifico.
WORLD_SOURCES = (
    "world",
    "environment",
    "weather",
    "crowd",
    "faction",
)

# Azioni di divulgazione di un segreto o fatto conosciuto.
DISCLOSURE_ACTIONS = (
    "revealed",
    "partial_truth",
    "withheld",
    "lied",
    "deflected",
    "bargained",
    "refused",
)

# Azioni che trasferiscono conoscenza reale al giocatore.
TRUTHFUL_DISCLOSURE_ACTIONS = ("revealed", "partial_truth")


class ContractError(ValueError):
    """Payload del Game Master non conforme al contratto."""


# ---------------------------------------------------------------------------
# Proposta di prova
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckProposal:
    """Proposta narrativa di prova. Non autorevole finchÃ© Python non valida."""

    action_kind: str
    skill: str
    difficulty: int
    target_ids: list[str] = field(default_factory=list)
    opposition: str = "none"
    reason: str = ""
    stakes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_kind": self.action_kind,
            "skill": self.skill,
            "difficulty": self.difficulty,
            "target_ids": list(self.target_ids),
            "opposition": self.opposition,
            "reason": self.reason,
            "stakes": dict(self.stakes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckProposal":
        try:
            validate_check_proposal_shape(data, path="check_proposal")
        except SchemaError as exc:
            raise ContractError(str(exc)) from exc
        if not isinstance(data, dict):
            raise ContractError("check_proposal deve essere un oggetto JSON")
        action_kind = data.get("action_kind")
        if action_kind not in ACTION_KINDS:
            raise ContractError(f"action_kind non canonico: {action_kind!r}")
        opposition = data.get("opposition", "none")
        if opposition not in OPPOSITION_TYPES:
            raise ContractError(f"opposition non canonica: {opposition!r}")
        stakes = data.get("stakes") or {}
        missing = [o.value for o in OUTCOME_ORDER if not str(stakes.get(o.value, "")).strip()]
        if missing:
            raise ContractError(f"stakes mancanti o vuote per gli esiti: {', '.join(missing)}")
        try:
            difficulty = int(data["difficulty"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("difficulty obbligatoria e numerica") from exc
        return cls(
            action_kind=action_kind,
            skill=str(data.get("skill", "")).strip(),
            difficulty=difficulty,
            target_ids=[str(t) for t in data.get("target_ids", [])],
            opposition=opposition,
            reason=str(data.get("reason", "")).strip(),
            stakes={k: str(v) for k, v in stakes.items()},
        )


# ---------------------------------------------------------------------------
# Mutazioni proposte
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mutation:
    """Una conseguenza proposta dal GM. Mai applicata senza validazione."""

    type: str
    target: str
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Mutation":
        if not isinstance(data, dict):
            raise ContractError("ogni mutazione deve essere un oggetto JSON")
        mtype = data.get("type")
        if mtype not in MUTATION_TYPES:
            raise ContractError(f"tipo di mutazione non canonico: {mtype!r}")
        target = str(data.get("target", "")).strip()
        if not target:
            raise ContractError(f"mutazione {mtype} senza target")
        payload = dict(data.get("payload") or {})
        if mtype == "location_change" and "location_id" not in payload and target.startswith("loc_"):
            payload["location_id"] = target
            target = "player"
        elif mtype == "story_marker_add" and "marker_id" not in payload and target.startswith("marker_"):
            payload["marker_id"] = target
            target = "world"
        return cls(
            type=mtype,
            target=target,
            payload=payload,
            reason=str(data.get("reason", "")).strip(),
        )


@dataclass(frozen=True)
class MemoryProposal:
    summary: str
    witnesses: list[str]
    source: str = "observed"
    credibility: float = 1.0
    level: str = "immediate"
    emotional_impact: int = 0
    public: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryProposal":
        summary = str(data.get("summary", "")).strip()
        if not summary:
            raise ContractError("memory_event senza summary")
        # witnesses puÃ² essere vuoto: una scena senza NPC presenti non ha
        # testimoni. L'evento resta registrato ma non si attacca a nessun
        # NPC (commit lo gestisce: nessun testimone, nessuna memoria NPC).
        witnesses = [str(w) for w in data.get("witnesses", [])]
        if not witnesses:
            raise ContractError("memory_event richiede witnesses non vuoto")
        source = str(data.get("source", "observed")).strip()
        if source not in KNOWLEDGE_SOURCES:
            raise ContractError(f"source di memoria non valida: {source!r}")
        try:
            credibility = float(data.get("credibility", 1.0))
        except (TypeError, ValueError) as exc:
            raise ContractError("memory_event.credibility deve essere numerica") from exc
        if not 0.0 <= credibility <= 1.0:
            raise ContractError("memory_event.credibility fuori range 0.0-1.0")
        level = data.get("level", "immediate")
        if level not in ("immediate", "relational", "durable"):
            raise ContractError(f"livello di memoria non valido: {level!r}")
        return cls(
            summary=summary,
            witnesses=witnesses,
            source=source,
            credibility=credibility,
            level=level,
            emotional_impact=int(data.get("emotional_impact", 0)),
            public=bool(data.get("public", True)),
        )


# ---------------------------------------------------------------------------
# Momento visuale
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VisualMoment:
    """Il momento visivo scelto dal GM per l'immagine del turno."""

    summary: str
    focus_character: str
    visible_characters: list[str]
    shared_action: bool
    visual_en: str
    tags_en: list[str] = field(default_factory=list)
    moment_type: str = ""  # speech | action | reaction | intimate | establishing
    speaker_character: str = ""
    actor_character: str = ""
    reactor_character: str = ""
    intimate_shared_moment: bool = False
    multi_character_reason: str = ""
    multi_character_participants: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualMoment":
        try:
            validate_visual_moment_shape(data)
        except SchemaError as exc:
            raise ContractError(str(exc)) from exc
        if not isinstance(data, dict):
            raise ContractError("visual obbligatorio in ogni scena")
        visual_en = str(data.get("visual_en", "")).strip()
        if not visual_en:
            raise ContractError("visual.visual_en obbligatorio: descrizione inglese del momento")
        focus = str(data.get("focus_character", "")).strip()
        visible = [str(v) for v in data.get("visible_characters", [])]
        if not focus:
            raise ContractError("visual.focus_character obbligatorio")
        if not visible:
            raise ContractError("visual.visible_characters obbligatorio")
        if focus not in visible:
            raise ContractError("visual.focus_character deve comparire in visible_characters")
        return cls(
            summary=str(data.get("summary", "")).strip(),
            focus_character=focus,
            visible_characters=visible,
            shared_action=bool(data.get("shared_action", False)),
            visual_en=visual_en,
            tags_en=[str(t) for t in data.get("tags_en", [])],
            moment_type=str(data.get("moment_type", "")).strip(),
            speaker_character=str(
                data.get("speaker_character", data.get("speaker", ""))
            ).strip(),
            actor_character=str(data.get("actor_character", data.get("actor", ""))).strip(),
            reactor_character=str(
                data.get("reactor_character", data.get("reactor", ""))
            ).strip(),
            intimate_shared_moment=bool(data.get("intimate_shared_moment", False)),
            multi_character_reason=str(data.get("multi_character_reason", "")).strip(),
            multi_character_participants=[
                str(c) for c in data.get("multi_character_participants", [])
            ],
        )


# ---------------------------------------------------------------------------
# Scena finale
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DialogueLine:
    """Una battuta. `to` rende esplicito il dialogo NPC â†’ NPC."""

    speaker: str
    text: str
    to: str | None = None  # npc_id | "player" | None (rivolto alla scena)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DialogueLine":
        speaker = str(data.get("speaker", "")).strip()
        text = str(data.get("text", "")).strip()
        if not speaker or not text:
            raise ContractError("ogni linea di dialogo richiede speaker e text")
        to = data.get("to")
        return cls(speaker=speaker, text=text, to=str(to).strip() if to else None)


@dataclass(frozen=True)
class InitiativeEvent:
    """Iniziativa autonoma di un NPC o del mondo durante la scena.

    Non Ã¨ una reazione passiva: deve avere uno scopo concreto e cambiare
    la situazione. Le reazioni pure (sguardi, esitazioni) non contano.
    """

    source: str  # npc_id presente oppure fonte mondiale
    type: str
    summary: str
    reason: str = ""
    target: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InitiativeEvent":
        source = str(data.get("source", "")).strip()
        if not source:
            raise ContractError("initiative senza source")
        itype = str(data.get("type", "")).strip().casefold()
        itype = INITIATIVE_TYPE_ALIASES.get(itype, itype)
        if itype not in INITIATIVE_TYPES:
            raise ContractError(f"tipo di iniziativa non canonico: {itype!r}")
        summary = str(data.get("summary", "")).strip()
        if not summary:
            raise ContractError(f"iniziativa {itype} senza summary")
        target = data.get("target")
        return cls(
            source=source,
            type=itype,
            summary=summary,
            reason=str(data.get("reason", "")).strip(),
            target=str(target).strip() if target else None,
        )


@dataclass(frozen=True)
class DisclosureEvent:
    """Come un NPC gestisce un segreto o un fatto nella scena."""

    npc_id: str
    fact: str
    action: str  # DISCLOSURE_ACTIONS
    tactic: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DisclosureEvent":
        npc_id = str(data.get("npc_id", "")).strip()
        fact = str(data.get("fact", "")).strip()
        action = str(data.get("action", "")).strip().casefold()
        if not npc_id or not fact:
            raise ContractError("disclosure_event richiede npc_id e fact")
        if action not in DISCLOSURE_ACTIONS:
            raise ContractError(f"azione di disclosure non canonica: {action!r}")
        return cls(
            npc_id=npc_id,
            fact=fact,
            action=action,
            tactic=str(data.get("tactic", "")).strip(),
        )


@dataclass(frozen=True)
class FinalScene:
    """L'unico contratto narrativo finale del turno."""

    narration: str
    dialogue: list[DialogueLine] = field(default_factory=list)
    npc_actions: list[dict[str, str]] = field(default_factory=list)
    intentions: list[dict[str, str]] = field(default_factory=list)
    initiatives: list[InitiativeEvent] = field(default_factory=list)
    disclosure_events: list[DisclosureEvent] = field(default_factory=list)
    mutations: list[Mutation] = field(default_factory=list)
    memory_events: list[MemoryProposal] = field(default_factory=list)
    visual: VisualMoment | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FinalScene":
        try:
            validate_final_scene_shape(data)
        except SchemaError as exc:
            raise ContractError(str(exc)) from exc
        if not isinstance(data, dict):
            raise ContractError("scene deve essere un oggetto JSON")
        narration = str(data.get("narration", "")).strip()
        if not narration:
            raise ContractError("scene.narration obbligatoria")
        return cls(
            narration=narration,
            dialogue=[DialogueLine.from_dict(d) for d in data.get("dialogue", [])],
            npc_actions=[dict(a) for a in data.get("npc_actions", [])],
            intentions=[dict(i) for i in data.get("intentions", [])],
            initiatives=[InitiativeEvent.from_dict(i) for i in data.get("initiatives", [])],
            disclosure_events=[
                DisclosureEvent.from_dict(d) for d in data.get("disclosure_events", [])
            ],
            mutations=[Mutation.from_dict(m) for m in data.get("mutations", [])],
            memory_events=[MemoryProposal.from_dict(m) for m in data.get("memory_events", [])],
            visual=VisualMoment.from_dict(data["visual"]) if data.get("visual") else None,
        )


@dataclass(frozen=True)
class ConfrontProposal:
    """Proposta di confronto a due mani con un NPC presente.

    Poste: cosa succede se il giocatore vince, se perde, in stallo."""

    skill: str
    target_id: str
    reason: str = ""
    stakes: dict[str, str] = field(default_factory=dict)  # win | lose | stall

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "target_id": self.target_id,
            "reason": self.reason,
            "stakes": dict(self.stakes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfrontProposal":
        if not isinstance(data, dict):
            raise ContractError("confront_proposal deve essere un oggetto JSON")
        target_id = str(data.get("target_id", "")).strip()
        if not target_id:
            raise ContractError("confront_proposal senza target_id")
        stakes = data.get("stakes") or {}
        missing = [k for k in ("win", "lose", "stall") if not str(stakes.get(k, "")).strip()]
        if missing:
            raise ContractError(f"stakes del confronto mancanti: {', '.join(missing)}")
        return cls(
            skill=str(data.get("skill", "")).strip(),
            target_id=target_id,
            reason=str(data.get("reason", "")).strip(),
            stakes={k: str(v) for k, v in stakes.items()},
        )


# ---------------------------------------------------------------------------
# Risposta di fase 1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GmPhaseResponse:
    """Risposta del GM alla prima fase del turno."""

    mode: str  # "no_check" | "check_proposal" | "confront_proposal" | "clarification"
    scene: FinalScene | None = None
    check: CheckProposal | None = None
    confront: ConfrontProposal | None = None
    clarification: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GmPhaseResponse":
        try:
            validate_gm_phase_response_shape(data)
        except SchemaError as exc:
            message = str(exc)
            if isinstance(data, dict) and data.get("mode") == "check_proposal" and "scene" in data:
                raise ContractError("check_proposal non deve contenere gia la scena finale") from exc
            if isinstance(data, dict) and data.get("mode") == "confront_proposal" and "scene" in data:
                raise ContractError("confront_proposal non deve contenere gia la scena finale") from exc
            raise ContractError(message) from exc
        if not isinstance(data, dict):
            raise ContractError("la risposta del GM deve essere un oggetto JSON")
        mode = data.get("mode")
        if mode == "no_check":
            if not data.get("scene"):
                raise ContractError("mode no_check richiede scene")
            return cls(mode=mode, scene=FinalScene.from_dict(data["scene"]))
        if mode == "check_proposal":
            if not data.get("check"):
                raise ContractError("mode check_proposal richiede check")
            if data.get("scene") is not None:
                raise ContractError("check_proposal non deve contenere giÃ  la scena finale")
            return cls(mode=mode, check=CheckProposal.from_dict(data["check"]))
        if mode == "confront_proposal":
            if not data.get("confront"):
                raise ContractError("mode confront_proposal richiede confront")
            if data.get("scene") is not None:
                raise ContractError("confront_proposal non deve contenere giÃ  la scena finale")
            return cls(mode=mode, confront=ConfrontProposal.from_dict(data["confront"]))
        if mode == "clarification":
            clarification = str(data.get("clarification", "")).strip()
            if not clarification:
                raise ContractError("mode clarification richiede clarification non vuota")
            if data.get("scene") is not None or data.get("check") is not None or data.get("confront") is not None:
                raise ContractError("clarification non deve contenere scene, check o confront")
            return cls(mode=mode, clarification=clarification)
        raise ContractError(
            f"mode non valido: {mode!r} (atteso no_check | check_proposal | confront_proposal | clarification)"
        )


def outcome_stake(proposal: CheckProposal, outcome: Outcome) -> str:
    """La posta in gioco dichiarata per l'esito ottenuto."""

    return proposal.stakes.get(outcome.value, "")
