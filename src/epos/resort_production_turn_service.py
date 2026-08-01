"""Production Resort service with concrete creative-outfit enforcement.

A generic request such as ``indossa qualcosa di sexy`` remains a narrative
choice for the NPC. The NPC may refuse without any outfit mutation. When the
scene accepts or performs the request, however, the LLM must name at least one
concrete garment and emit canonical ``outfit_wear`` mutations. Vague values
such as ``sexy outfit`` are rejected so the authoritative outfit state and the
visual prompt never depend on an abstract adjective.
"""

from __future__ import annotations

import re
import unicodedata

from .resort_final_turn_service import ResortFinalTurnService, _present_target
from .resort_intro import current_intro_step, initialise_resort_intro
from .resort_playable_turn_service import _movement_scene
from .validators import ValidationErrorDetail, ValidationReport

_GENERIC_SEXY_REQUEST_RE = re.compile(
    r"\b(?:qualcosa|un\s+outfit|un\s+abito|dei\s+vestiti|vestiti|abbigliamento)\s+"
    r"(?:di\s+)?(?:sexy|sensuale|provocante|seducente)\b|"
    r"\b(?:indossa|mettiti|metti|scegli|vestiti\s+con)\b[^.!?]{0,50}"
    r"\b(?:sexy|sensuale|provocante|seducente)\b",
    re.IGNORECASE,
)
_REFUSAL_RE = re.compile(
    r"\b(?:rifiuta|rifiuto|non\s+voglio|non\s+me\s+la\s+sento|preferisco\s+di\s+no|"
    r"non\s+accetto|declina|refuses?|declines?|won't|will\s+not|doesn't\s+want)\b",
    re.IGNORECASE,
)
_GENERIC_ITEM_RE = re.compile(
    r"^(?:qualcosa(?:\s+di)?\s+)?(?:sexy|sensuale|provocante|seducente)|"
    r"^(?:sexy|sensual|provocative|seductive)\s+(?:outfit|clothes?|clothing|look|attire)$|"
    r"^(?:outfit|abito|vestito|vestiti|abbigliamento|clothes?|clothing|attire)$",
    re.IGNORECASE,
)
_GENERIC_BEACH_MOVE_RE = re.compile(
    r"\b(?:vado|andrei|andiamo|voglio\s+andare|vorrei\s+andare|mi\s+reco|"
    r"raggiungo|torno|ritorno|spostiamoci|portami|accompagnami)\b[^.!?]{0,60}"
    r"\bspiaggia\b",
    re.IGNORECASE,
)
_SPECIFIC_BEACH_RE = re.compile(r"\b(?:spiaggia\s+privata|spiaggia\s+selvaggia|cala)\b", re.IGNORECASE)


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


def _scene_text(scene) -> str:
    parts = [str(getattr(scene, "narration", "") or "")]
    for line in getattr(scene, "dialogue", []):
        parts.append(str(getattr(line, "text", "") or ""))
    for action in getattr(scene, "npc_actions", []):
        parts.append(str(getattr(action, "action", "") or ""))
    return " ".join(parts)


def _is_generic_sexy_request(player_text: str) -> bool:
    return bool(_GENERIC_SEXY_REQUEST_RE.search(_plain(player_text)))


def _is_refusal_scene(scene) -> bool:
    return bool(_REFUSAL_RE.search(_plain(_scene_text(scene))))


def _generic_beach_destination(pack, player_text: str) -> str | None:
    """Resolve plain 'spiaggia' to the Resort private beach.

    Specific requests remain handled by the canonical navigation layer. This
    repair exists because the generic word previously fell through to the LLM,
    which could turn a simple movement into an unrelated social check.
    """

    text = _plain(player_text)
    if not _GENERIC_BEACH_MOVE_RE.search(text):
        return None
    if _SPECIFIC_BEACH_RE.search(text):
        return None
    return "loc_private_beach" if "loc_private_beach" in pack.locations else None


def _concrete_wear_items(scene, npc_id: str) -> tuple[list[str], list[str]]:
    concrete: list[str] = []
    vague: list[str] = []
    for mutation in getattr(scene, "mutations", []):
        if str(getattr(mutation, "type", "")) != "outfit_wear":
            continue
        if str(getattr(mutation, "target", "")) != npc_id:
            continue
        item = str((getattr(mutation, "payload", {}) or {}).get("item", "")).strip()
        if not item or _GENERIC_ITEM_RE.search(_plain(item)):
            vague.append(item)
        else:
            concrete.append(item)
    return concrete, vague


def validate_concrete_sexy_outfit(
    report: ValidationReport,
    state,
    player_text: str,
    scene,
) -> ValidationReport:
    """Require concrete canonical garments only when the NPC accepts.

    Refusals remain valid and need no mutation. Accepted/performed generic
    outfit requests require at least one concrete ``outfit_wear`` item.
    """

    if not _is_generic_sexy_request(player_text):
        return report
    npc_id = _present_target(state, player_text)
    if npc_id is None or _is_refusal_scene(scene):
        return report

    concrete, vague = _concrete_wear_items(scene, npc_id)
    if concrete and not vague:
        return report

    errors = list(report.errors)
    if vague:
        message = (
            "Resort outfit: la NPC ha accettato, ma i capi proposti sono generici; "
            "usa nomi visivi concreti come 'black lace lingerie' o 'red satin dress'."
        )
        code = "resort_concrete_outfit_items_required"
        details = {"target_npc_id": npc_id, "vague_items": vague}
    else:
        message = (
            "Resort outfit: la NPC ha accettato una richiesta di abbigliamento creativo, "
            "ma manca almeno una mutazione outfit_wear con un capo concreto."
        )
        code = "resort_outfit_wear_mutation_required"
        details = {"target_npc_id": npc_id}

    errors.append(
        ValidationErrorDetail(
            code=code,
            path="mutations[outfit_wear].payload.item",
            message=message,
            details=details,
        )
    )
    return ValidationReport(
        problems=[error.message for error in errors],
        errors=errors,
        warnings=list(report.warnings),
    )


class ResortProductionTurnService(ResortFinalTurnService):
    """Final launcher service including deterministic movement repairs."""

    def play(self, state, player_text: str):
        initialise_resort_intro(state)
        if current_intro_step(state) is None:
            destination = _generic_beach_destination(self.pack, player_text)
            if destination is not None and destination != state.location_id:
                scene = _movement_scene(self.pack, state, destination)
                return self._commit_turn(
                    state,
                    state.turn,
                    "no_check",
                    scene,
                    player_text=player_text,
                )
        return super().play(state, player_text)

    def _validate_phase1_response_after_outfit_normalization(
        self, response, state, player_text: str
    ):
        report = super()._validate_phase1_response_after_outfit_normalization(
            response, state, player_text
        )
        if response.mode == "no_check" and response.scene is not None:
            return validate_concrete_sexy_outfit(
                report, state, player_text, response.scene
            )
        return report

    def _validate_scene_after_outfit_normalization(
        self, scene, state, player_text: str
    ):
        report = super()._validate_scene_after_outfit_normalization(
            scene, state, player_text
        )
        return validate_concrete_sexy_outfit(report, state, player_text, scene)
