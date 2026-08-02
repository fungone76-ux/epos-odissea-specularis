"""Shared TurnService data contracts and default providers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .contract import CheckProposal, ConfrontProposal
from .models import WorldState
from .renderers import RenderRecord
from .rules import ConfrontResult, Roll
from .visual import VisualContract


@dataclass
class PlayerDecision:
    """Decisione completa alla proposta di prova."""

    choice: str = "roll"  # roll | safe
    use_riserva: bool = False  # -1 dado riserva, +1 pool
    dado_temerario_price: str | None = None  # se valorizzato: +1 pool, prezzo scommesso
    use_trigger: bool = False  # attiva l'innesco pre-scritto


DecisionProvider = Callable[[CheckProposal, int, int, WorldState], PlayerDecision]
NarrationProvider = Callable[[str], str]  # contesto -> descrizione del giocatore
SplitProvider = Callable[[ConfrontProposal, int, int], int]  # -> dadi in mano sinistra
TemerarioProvider = Callable[[Roll], str | None]  # -> prezzo per ritirare, oppure None
PostTurnProcessor = Callable[[WorldState, "TurnResult"], dict[str, Any] | None]


def default_decision(_proposal, _rating, _difficulty, _state) -> PlayerDecision:
    return PlayerDecision()


def default_narration(_context: str) -> str:
    return ""


def default_split(_proposal, player_pool, _npc_pool) -> int:
    return player_pool  # tutto nella mano della vittoria


def default_temerario(_roll) -> str | None:
    return None


def default_post_turn_processor(_state: WorldState, _result: "TurnResult") -> dict[str, Any] | None:
    return None


@dataclass
class TurnResult:
    turn: int
    mode: str  # "no_check" | "check" | "confront"
    narration: str
    dialogue: list[dict[str, str]] = field(default_factory=list)
    proposal: CheckProposal | None = None
    roll: Roll | None = None
    confront_result: ConfrontResult | None = None
    player_narration: str = ""
    temerario_price: str | None = None
    stake: str = ""
    visual_contract: VisualContract | None = None
    render_record: RenderRecord | None = None
    scene_mutations: list[dict[str, Any]] = field(default_factory=list)
    campaign_changes: dict[str, Any] = field(default_factory=dict)
    resumed: bool = False
