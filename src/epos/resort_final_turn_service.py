"""Final Resort runtime fixes for agreed outfit continuations.

This layer is intentionally narrow: it preserves intro, navigation and NPC
summoning while making already-agreed hosiery changes deterministic and
canonical. It also accepts genuine NPC actions that use a natural NPC alias.
"""

from __future__ import annotations

import re
import unicodedata

from .contract import FinalScene
from .models import outfit_state
from .resort_intro import current_intro_step, initialise_resort_intro
from .resort_playable_turn_service import ResortPlayableTurnService
from .resort_turn_service import _speaker_id
from .validators import ValidationReport

_HOSIERY_RE = re.compile(r"\b(?:pantyhose|collant|calze|calzamaglia)\b", re.IGNORECASE)
_CONTINUE_RE = re.compile(r"\b(?:fallo|fallo ora|procedi|mettile|indossale|va bene|si|sì)\b", re.IGNORECASE)


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


def _present_target(state, player_text: str) -> str | None:
    text = _plain(player_text)
    present = [npc_id for npc_id in state.present_npc_ids() if npc_id in state.npcs]
    for npc_id in present:
        npc = state.npcs[npc_id]
        names = {npc_id, str(npc.name or "")}
        full_name = _plain(npc.name)
        if full_name:
            names.add(full_name.split()[0])
        if any(_plain(name) in text for name in names if name):
            return npc_id
    return present[0] if len(present) == 1 else None


def _agreed_hosiery_request(state, player_text: str) -> tuple[str, str] | None:
    target = _present_target(state, player_text)
    if target is None:
        return None

    text = _plain(player_text)
    history = _plain(state.last_scene)
    explicit = bool(_HOSIERY_RE.search(text))
    continuation = bool(_CONTINUE_RE.search(text)) and bool(_HOSIERY_RE.search(history))
    if not (explicit or continuation):
        return None

    black = any(token in f"{text} {history}" for token in ("nere", "black")) or "pantyhose" in text
    return target, "black pantyhose" if black else "pantyhose"


def _outfit_scene(pack, state, npc_id: str, hosiery: str) -> FinalScene:
    npc = state.npcs[npc_id]
    location = pack.locations[state.location_id]
    current = outfit_state(npc.outfit)
    footwear = list(current.get("footwear", []))

    mutations = [
        {
            "type": "outfit_remove",
            "target": npc_id,
            "payload": {"item": item},
            "reason": "La NPC indossa le pantyhose senza scarpe come già concordato.",
        }
        for item in footwear
    ]
    if hosiery not in npc.outfit.worn:
        mutations.append(
            {
                "type": "outfit_wear",
                "target": npc_id,
                "payload": {"item": hosiery},
                "reason": "La NPC completa il cambio outfit già accettato.",
            }
        )

    return FinalScene.from_dict(
        {
            "narration": f"{npc.name} si sfila le scarpe e indossa le pantyhose nere come concordato.",
            "dialogue": [
                {
                    "speaker": npc.name,
                    "to": "player",
                    "text": "Va bene. Le indosso senza scarpe, come mi hai chiesto.",
                }
            ],
            "npc_actions": [
                {
                    "npc_id": npc_id,
                    "action": "removes footwear and puts on black pantyhose",
                }
            ],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": mutations,
            "memory_events": [],
            "visual": {
                "summary": f"{npc.name} indossa pantyhose nere senza scarpe.",
                "focus_character": npc_id,
                "visible_characters": [npc_id],
                "shared_action": False,
                "visual_en": (
                    f"{npc.name}, black pantyhose, barefoot, no shoes, full body, "
                    f"standing inside the {location.name}, detailed luxury interior"
                ),
                "tags_en": [
                    "black pantyhose",
                    "barefoot",
                    "no shoes",
                    "full body",
                    f"{location.name} interior",
                ],
                "moment_type": "action",
                "speaker_character": "",
                "actor_character": npc_id,
                "reactor_character": "",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": [npc_id],
            },
        }
    )


def _has_present_npc_action(state, scene) -> bool:
    present = set(state.present_npc_ids())
    for action in getattr(scene, "npc_actions", []):
        raw = str(getattr(action, "npc_id", ""))
        resolved = raw if raw in state.npcs else _speaker_id(state, raw)
        if resolved in present:
            return True
    return False


def _remove_false_npc_error(report: ValidationReport, state, scene) -> ValidationReport:
    if not _has_present_npc_action(state, scene):
        return report
    errors = [error for error in report.errors if error.code != "resort_npc_response_required"]
    return ValidationReport(
        problems=[error.message for error in errors],
        errors=errors,
        warnings=list(report.warnings),
    )


class ResortFinalTurnService(ResortPlayableTurnService):
    """Production service used by the Resort launcher."""

    def play(self, state, player_text: str):
        initialise_resort_intro(state)
        if current_intro_step(state) is None:
            request = _agreed_hosiery_request(state, player_text)
            if request is not None:
                npc_id, hosiery = request
                scene = _outfit_scene(self.pack, state, npc_id, hosiery)
                return self._commit_turn(
                    state,
                    state.turn,
                    "no_check",
                    scene,
                    player_text=player_text,
                )
        return super().play(state, player_text)

    def _validate_phase1_response_after_outfit_normalization(self, response, state, player_text: str):
        report = super()._validate_phase1_response_after_outfit_normalization(response, state, player_text)
        if response.mode == "no_check" and response.scene is not None:
            return _remove_false_npc_error(report, state, response.scene)
        return report

    def _validate_scene_after_outfit_normalization(self, scene, state, player_text: str):
        report = super()._validate_scene_after_outfit_normalization(scene, state, player_text)
        return _remove_false_npc_error(report, state, scene)
