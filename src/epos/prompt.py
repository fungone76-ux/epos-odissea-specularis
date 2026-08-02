"""Costruzione del prompt e dello snapshot compatto per il Game Master.

Lo snapshot contiene solo cio che serve al turno corrente: mai l'intero
salvataggio, mai la storia completa, mai i prompt visivi precedenti.
"""

from __future__ import annotations

from .prompt_phase1 import phase1_messages
from .prompt_phase2 import _extras_block, phase2_messages
from .prompt_rules import (
    CONFRONT_BLOCK,
    NARRATIVE_INTENSITY_RULES,
    ODYSSEY_VISUAL_RULES,
    OUTFIT_MUTATION_RULES,
    PHASE1_INSTRUCTIONS,
    PHASE2_INSTRUCTIONS,
    PLAYER_NARRATION_BLOCK,
    SCENE_FORMAT_RULES,
    SYSTEM_PROMPT,
    TEMERARIO_PRICE_BLOCK,
    VISUAL_LAYER_RULES,
)
from .prompt_snapshot import _compact_snapshot, _mission_context, build_snapshot

__all__ = [
    "CONFRONT_BLOCK",
    "NARRATIVE_INTENSITY_RULES",
    "ODYSSEY_VISUAL_RULES",
    "OUTFIT_MUTATION_RULES",
    "PHASE1_INSTRUCTIONS",
    "PHASE2_INSTRUCTIONS",
    "PLAYER_NARRATION_BLOCK",
    "SCENE_FORMAT_RULES",
    "SYSTEM_PROMPT",
    "TEMERARIO_PRICE_BLOCK",
    "VISUAL_LAYER_RULES",
    "_compact_snapshot",
    "_extras_block",
    "_mission_context",
    "build_snapshot",
    "phase1_messages",
    "phase2_messages",
]
