"""Servizio finale del Resort: intro, navigazione e convocazione NPC.

Dopo l'intro, i comandi espliciti di movimento e le richieste di essere
raggiunti da una NPC sono applicati deterministicamente da Python. In questo
modo non dipendono dalla forma del JSON prodotto dalla LLM. Tutte le altre
azioni restano affidate al normale gameplay libero.
"""

from __future__ import annotations

import re
import unicodedata

from .contract import FinalScene
from .resort_intro import current_intro_step, initialise_resort_intro
from .resort_intro_turn_service import ResortIntroTurnService
from .validators import ValidationReport


_LOCATION_ALIASES: dict[str, tuple[str, ...]] = {
    "loc_suite": (
        "camera", "stanza", "mia stanza", "mia camera", "suite",
        "suite presidenziale", "appartamento",
    ),
    "loc_lobby": ("lobby", "reception", "ingresso", "atrio"),
    "loc_restaurant": ("ristorante", "sala ristorante"),
    "loc_pool": ("piscina", "piscina infinity", "infinity pool"),
    "loc_spa": ("spa", "centro benessere", "sauna", "bagno turco"),
    "loc_private_beach": ("spiaggia privata",),
    "loc_wild_beach": ("spiaggia selvaggia", "cala", "cala rocciosa"),
    "loc_lounge": ("lounge", "lounge bar", "bar", "cocktail bar"),
    "loc_victoria_office": (
        "ufficio di victoria", "ufficio victoria", "ufficio della direttrice",
    ),
}

_MOVE_RE = re.compile(
    r"\b(?:vado|andrei|andiamo|voglio andare|vorrei andare|mi reco|raggiungo|"
    r"torno|ritorno|spostarmi|spostiamoci|portami|accompagnami)\b",
    re.IGNORECASE,
)
_SUMMON_RE = re.compile(
    r"\b(?:raggiung|venga|venire|vieni|chiam|mandat|fate venire|fai venire|"
    r"portat|accompagnat)\w*\b",
    re.IGNORECASE,
)


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


def _is_player_location_change(scene) -> bool:
    return any(
        str(getattr(mutation, "type", "")) == "location_change"
        and str(getattr(mutation, "target", "")) == "player"
        and bool(str(getattr(mutation, "payload", {}).get("location_id", "")).strip())
        for mutation in getattr(scene, "mutations", [])
    )


def _allow_solo_navigation(report: ValidationReport, scene) -> ValidationReport:
    if not _is_player_location_change(scene):
        return report
    blocked_codes = {"resort_npc_response_required"}
    remaining_errors = [
        error for error in report.errors if error.code not in blocked_codes
    ]
    return ValidationReport(
        problems=[error.message for error in remaining_errors],
        errors=remaining_errors,
        warnings=list(report.warnings),
    )


def _destination_from_text(pack, player_text: str) -> str | None:
    text = _plain(player_text)
    if not _MOVE_RE.search(text):
        return None
    for location_id, aliases in _LOCATION_ALIASES.items():
        if location_id not in pack.locations:
            continue
        if any(_plain(alias) in text for alias in aliases):
            return location_id
    return None


def _summoned_npc_from_text(state, player_text: str) -> str | None:
    text = _plain(player_text)
    if not _SUMMON_RE.search(text):
        return None
    for npc_id, npc in state.npcs.items():
        names = {npc_id, str(npc.name or "")}
        full_name = _plain(npc.name)
        if full_name:
            names.add(full_name.split()[0])
        if any(_plain(name) in text for name in names if name):
            return npc_id
    return None


def _movement_scene(pack, state, destination_id: str) -> FinalScene:
    destination = pack.locations[destination_id]
    return FinalScene.from_dict(
        {
            "narration": (
                f"Lasci la {pack.locations[state.location_id].name} e raggiungi "
                f"{destination.name}. Qui puoi finalmente prenderti un momento "
                "per ambientarti e rilassarti."
            ),
            "dialogue": [],
            "npc_actions": [],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [
                {
                    "type": "location_change",
                    "target": "player",
                    "payload": {"location_id": destination_id},
                    "reason": "Spostamento esplicitamente richiesto dal giocatore.",
                }
            ],
            "memory_events": [],
            "visual": None,
        }
    )


def _summon_scene(pack, state, npc_id: str) -> FinalScene:
    npc = state.npcs[npc_id]
    location = pack.locations[state.location_id]
    return FinalScene.from_dict(
        {
            "narration": (
                f"La richiesta viene recapitata a {npc.name}. Poco dopo, "
                f"{npc.name} ti raggiunge nella {location.name}."
            ),
            "dialogue": [
                {
                    "speaker": npc.name,
                    "to": "player",
                    "text": "Mi hai fatto chiamare. Eccomi qui: dimmi pure di cosa hai bisogno.",
                }
            ],
            "npc_actions": [
                {
                    "npc_id": npc_id,
                    "action": f"raggiunge il cliente VIP nella {location.name}",
                }
            ],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [
                {
                    "type": "location_change",
                    "target": npc_id,
                    "payload": {"location_id": state.location_id},
                    "reason": "La NPC accetta la richiesta di raggiungere il giocatore.",
                }
            ],
            "memory_events": [],
            "visual": {
                "summary": f"{npc.name} raggiunge il cliente VIP nella {location.name}.",
                "focus_character": npc_id,
                "visible_characters": [npc_id],
                "shared_action": False,
                "visual_en": (
                    f"{npc.name} arrives inside the {location.name} and addresses "
                    "the unseen VIP guest, detailed luxury resort interior, "
                    "elegant cinematic composition"
                ),
                "tags_en": [
                    "NPC arrival",
                    "unseen guest POV",
                    f"{location.name} interior",
                ],
                "moment_type": "speech",
                "speaker_character": npc_id,
                "actor_character": npc_id,
                "reactor_character": npc_id,
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": [npc_id],
            },
        }
    )


class ResortPlayableTurnService(ResortIntroTurnService):
    """Servizio di produzione usato dai launcher GUI e CLI del Resort."""

    def play(self, state, player_text: str):
        initialise_resort_intro(state)
        if current_intro_step(state) is not None:
            return super().play(state, player_text)

        npc_id = _summoned_npc_from_text(state, player_text)
        if npc_id is not None:
            scene = _summon_scene(self.pack, state, npc_id)
            return self._commit_turn(
                state, state.turn, "no_check", scene, player_text=player_text
            )

        destination_id = _destination_from_text(self.pack, player_text)
        if destination_id is not None:
            scene = _movement_scene(self.pack, state, destination_id)
            return self._commit_turn(
                state, state.turn, "no_check", scene, player_text=player_text
            )

        return super().play(state, player_text)

    def _validate_phase1_response_after_outfit_normalization(
        self, response, state, player_text: str
    ):
        report = super()._validate_phase1_response_after_outfit_normalization(
            response, state, player_text
        )
        if response.mode != "no_check" or response.scene is None:
            return report
        return _allow_solo_navigation(report, response.scene)

    def _validate_scene_after_outfit_normalization(
        self, scene, state, player_text: str
    ):
        report = super()._validate_scene_after_outfit_normalization(
            scene, state, player_text
        )
        return _allow_solo_navigation(report, scene)
