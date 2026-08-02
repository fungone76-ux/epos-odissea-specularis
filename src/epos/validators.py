"""Validazione: l'arbitro Python tra le proposte della LLM e lo stato.

Principi: adeguatezza, integritÃ , pertinenza, presenza, conoscenza,
persistenza, consenso. Le mutazioni invalide vengono rifiutate con
diagnostica, mai corrette inventando contenuto narrativo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .contract import CheckProposal, ConfrontProposal, FinalScene, Mutation
from .entity_ids import player_aliases_for_state
from .models import (
    KNOWLEDGE_SOURCES,
    RELATIONSHIP_DOMAINS,
    Outfit,
    WorldState,
    outfit_state,
)
from .rules import MAX_DIFFICULTY, MIN_DIFFICULTY
from .validator_proposals import validate_check_proposal, validate_confront_proposal
from .validator_scene import MAX_EMOTIONAL_IMPACT, _character_id_for_name, validate_scene
from .validator_mutations import MAX_RELATIONSHIP_DELTA, MAX_RESOURCE_DELTA, _validate_mutation
from .validator_common import (
    ValidationErrorDetail,
    ValidationReport,
    ValidationWarning,
    _add_problem,
    _code_for_problem,
    _path_for_problem,
)
from .validator_scene_visual import (
    _mentions_unworn_clothing,
    _outfit_after_scene,
    _scene_implies_bottomless,
    _scene_implies_full_nudity,
    _scene_implies_topless,
    _strip_place_owner_mentions,
    _validate_player_outfit_visual_consistency,
    _validate_visible_character_text,
)
from .worldpack import WorldPack
