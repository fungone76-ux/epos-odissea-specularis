"""Final Resort runtime fixes for agreed NPC outfit continuations.

This layer preserves intro, navigation and NPC summoning while applying an
already accepted outfit change deterministically. A new request is still left
to the LLM so the NPC may accept, hesitate or refuse. Once the previous scene
records acceptance, a continuation such as ``fallo ora`` becomes a canonical
no-check scene and updates the authoritative Outfit state before rendering.
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
_COMPLETE_UNDRESS_RE = re.compile(
    r"\b(?:completamente nud[aoie]|tutt[aoie] nud[aoie]|senza vestiti|senza abiti|"
    r"spogli(?:arsi|ati|ata|ato|arsi completamente)|svest(?:irsi|iti|ita|ito)|"
    r"fully nude|completely nude|naked|remove all clothes)\b",
    re.IGNORECASE,
)
_CONTINUE_RE = re.compile(
    r"\b(?:fallo|fallo ora|procedi|vai pure|continua|mettile|indossale|va bene|si|sì)\b",
    re.IGNORECASE,
)
_ACCEPTANCE_RE = re.compile(
    r"\b(?:accetta|accettato|d'accordo|concordato|annuisce|acconsente|è pronta|e pronta|"
    r"decide di|promette di|says yes|agrees|agreed|accepts|nods|ready to)\b",
    re.IGNORECASE,
)


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


def _history_records_acceptance(history: str) -> bool:
    return bool(_ACCEPTANCE_RE.search(_plain(history)))


def _agreed_hosiery_request(state, player_text: str) -> tuple[str, str] | None:
    target = _present_target(state, player_text)
    if target is None:
        return None

    text = _plain(player_text)
    history = _plain(state.last_scene)
    explicit = bool(_HOSIERY_RE.search(text))
    continuation = (
        bool(_CONTINUE_RE.search(text))
        and bool(_HOSIERY_RE.search(history))
        and _history_records_acceptance(history)
    )
    if not (explicit or continuation):
        return None

    black = any(token in f"{text} {history}" for token in ("nere", "black")) or "pantyhose" in text
    return target, "black pantyhose" if black else "pantyhose"


def _agreed_complete_undress_request(state, player_text: str) -> str | None:
    """Resolve only a continuation of an NPC action already accepted.

    A fresh command such as ``Luna, spogliati completamente`` deliberately
    returns ``None`` and reaches the normal LLM pipeline. Only a continuation
    (for example ``fallo ora``) is deterministic after the prior scene both
    mentions complete nudity and records the NPC's acceptance.
    """

    target = _present_target(state, player_text)
    if target is None:
        return None

    text = _plain(player_text)
    history = _plain(state.last_scene)
    if not _CONTINUE_RE.search(text):
        return None
    if not _COMPLETE_UNDRESS_RE.search(history):
        return None
    if not _history_records_acceptance(history):
        return None
    return target


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


def _complete_undress_scene(pack, state, npc_id: str) -> FinalScene:
    """Remove every authoritative worn item from an agreeing adult NPC."""

    npc = state.npcs[npc_id]
    location = pack.locations[state.location_id]
    worn = [str(item).strip() for item in npc.outfit.worn if str(item).strip()]
    mutations = [
        {
            "type": "outfit_remove",
            "target": npc_id,
            "payload": {"item": item},
            "reason": "La NPC completa lo spogliarsi integrale già accettato.",
        }
        for item in worn
    ]

    return FinalScene.from_dict(
        {
            "narration": (
                f"{npc.name} mantiene quanto appena concordato e si spoglia completamente, "
                "lasciando da parte ogni capo che indossava."
            ),
            "dialogue": [
                {
                    "speaker": npc.name,
                    "to": "player",
                    "text": "Va bene. Lo faccio ora, come abbiamo concordato.",
                }
            ],
            "npc_actions": [
                {
                    "npc_id": npc_id,
                    "action": "removes every worn garment and remains fully nude",
                }
            ],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": mutations,
            "memory_events": [],
            "visual": {
                "summary": f"{npc.name} è completamente nuda dopo essersi spogliata.",
                "focus_character": npc_id,
                "visible_characters": [npc_id],
                "shared_action": False,
                "visual_en": (
                    f"{npc.name}, fully nude, barefoot, no clothes, no shoes, full body, "
                    f"standing inside the {location.name}, detailed luxury interior"
                ),
                "tags_en": [
                    "fully nude",
                    "barefoot",
                    "no clothes",
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
            undress_target = _agreed_complete_undress_request(state, player_text)
            if undress_target is not None:
                scene = _complete_undress_scene(self.pack, state, undress_target)
                return self._commit_turn(
                    state,
                    state.turn,
                    "no_check",
                    scene,
                    player_text=player_text,
                )

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
