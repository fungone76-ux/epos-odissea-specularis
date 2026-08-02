"""Servizio finale del Resort: intro, navigazione, convocazione e outfit canonici.

Dopo l'intro, i comandi espliciti di movimento, le richieste di essere
raggiunti da una NPC e le continuazioni outfit chiaramente concordate sono
applicati deterministicamente da Python. Tutte le altre azioni restano
affidate al normale gameplay libero.
"""

from __future__ import annotations

import re
import unicodedata

from .contract import FinalScene
from .resort_intent import interpret_resort_intent, resort_intent_directive
from .resort_presence import reconcile_resort_presence, scene_has_real_npc_participation
from .resort_intro import current_intro_step, initialise_resort_intro
from .resort_intro_turn_service import ResortIntroTurnService
from .resort_turn_service import _speaker_id
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
_HOSIERY_RE = re.compile(
    r"\b(?:pantyhose|collant|calze|calze nere|calzamaglia)\b",
    re.IGNORECASE,
)
_BAREFOOT_RE = re.compile(
    r"\b(?:senza scarpe|togli(?:ere|ersi)? le scarpe|scalza|a piedi nudi|barefoot)\b",
    re.IGNORECASE,
)
_CONTINUE_RE = re.compile(
    r"\b(?:fallo|fallo ora|procedi|mettile|indossale|va bene|si|sì)\b",
    re.IGNORECASE,
)

_BEACH_IDS = {"loc_private_beach", "loc_wild_beach"}
_RELAX_RE = re.compile(
    r"\b(?:mi rilasso|vorrei rilassarmi|voglio rilassarmi|mi riposo|vorrei riposarmi|"
    r"prendo il sole|mi sdraio|mi stendo|relax)\b",
    re.IGNORECASE,
)
_BEACH_OUTFITS: dict[str, tuple[str, ...]] = {
    "victoria": ("black luxury bikini", "sheer black beach sarong", "barefoot"),
    "stella": ("gold micro bikini", "light beach wrap", "barefoot"),
    "maria": ("black bikini", "white lace beach sarong", "barefoot"),
    "luna": ("ivory bikini", "sheer ivory beach sarong", "barefoot"),
}



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


def _field(item, name: str, default=""):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _scene_has_present_npc_action(state, scene) -> bool:
    present = set(state.present_npc_ids())
    for action in getattr(scene, "npc_actions", []):
        raw_id = str(_field(action, "npc_id", ""))
        resolved = raw_id if raw_id in state.npcs else _speaker_id(state, raw_id)
        if resolved in present:
            return True
    return scene_has_real_npc_participation(state, scene)


def _filter_report(report: ValidationReport, blocked_codes: set[str]) -> ValidationReport:
    remaining_errors = [error for error in report.errors if error.code not in blocked_codes]
    return ValidationReport(
        problems=[error.message for error in remaining_errors],
        errors=remaining_errors,
        warnings=list(report.warnings),
    )


def _allow_solo_navigation(report: ValidationReport, scene) -> ValidationReport:
    if not _is_player_location_change(scene):
        return report
    return _filter_report(report, {"resort_npc_response_required"})


def _accept_real_npc_action(report: ValidationReport, state, scene) -> ValidationReport:
    """Rimuove il falso errore Resort quando npc_actions contiene davvero una NPC presente."""

    if not _scene_has_present_npc_action(state, scene):
        return report
    return _filter_report(report, {"resort_npc_response_required"})


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


def _beach_visual(location_id: str, location_name: str, npc_name: str) -> tuple[str, list[str]]:
    if location_id == "loc_wild_beach":
        return (
            f"{npc_name} arrives at a secluded wild Mediterranean beach, standing on natural sand near rocky coves, open sky, blue sea, warm sunlight, looking toward the unseen VIP guest",
            ["NPC arrival", "wild Mediterranean beach", "natural sand", "rocky cove", "open sky", "blue sea"],
        )
    return (
        f"{npc_name} arrives at an exclusive private Mediterranean beach, standing on soft sand near elegant sun loungers, open sky, blue sea, warm sunlight, looking toward the unseen VIP guest",
        ["NPC arrival", "private Mediterranean beach", "soft sand", "elegant sun loungers", "open sky", "blue sea"],
    )


def _manual_outfit_override(npc) -> bool:
    outfit = getattr(npc, "outfit", None)
    return int(getattr(outfit, "revision", 0) or 0) > 0


def _beach_outfit_mutations(npc_id: str, npc) -> list[dict]:
    if _manual_outfit_override(npc):
        return []
    target_items = _BEACH_OUTFITS.get(npc_id)
    if not target_items:
        return []
    worn = [str(item) for item in getattr(getattr(npc, "outfit", None), "worn", [])]
    mutations: list[dict] = [
        {
            "type": "outfit_remove",
            "target": npc_id,
            "payload": {"item": item},
            "reason": "Cambio automatico all'outfit da spiaggia perche non esiste un override manuale.",
        }
        for item in worn
    ]
    mutations.extend(
        {
            "type": "outfit_wear",
            "target": npc_id,
            "payload": {"item": item},
            "reason": "Outfit coerente con la location spiaggia.",
        }
        for item in target_items
    )
    return mutations


def _mentioned_present_npc(state, player_text: str) -> str | None:
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


def _hosiery_request(state, player_text: str) -> tuple[str, str] | None:
    text = _plain(player_text)
    npc_id = _mentioned_present_npc(state, player_text)
    if npc_id is None:
        return None

    explicit = bool(_HOSIERY_RE.search(text))
    continuation = bool(_CONTINUE_RE.search(text)) and bool(
        _HOSIERY_RE.search(_plain(state.last_scene))
    )
    if not (explicit or continuation):
        return None

    item = "black pantyhose" if (
        "nere" in text or "black" in text or "pantyhose" in text
        or "nere" in _plain(state.last_scene) or "black" in _plain(state.last_scene)
    ) else "pantyhose"
    return npc_id, item


def _movement_scene(pack, state, destination_id: str) -> FinalScene:
    destination = pack.locations[destination_id]
    return FinalScene.from_dict(
        {
            "narration": (
                f"Lasci la {pack.locations[state.location_id].name} e raggiungi "
                f"{destination.name}. Qui puoi finalmente prenderti un momento "
                "per ambientarti e rilassarti."
            ),
            "dialogue": [], "npc_actions": [], "intentions": [], "initiatives": [],
            "disclosure_events": [],
            "mutations": [{
                "type": "location_change", "target": "player",
                "payload": {"location_id": destination_id},
                "reason": "Spostamento esplicitamente richiesto dal giocatore.",
            }],
            "memory_events": [], "visual": None,
        }
    )


def _summon_scene(pack, state, npc_id: str) -> FinalScene:
    npc = state.npcs[npc_id]
    location = pack.locations[state.location_id]
    beach = state.location_id in _BEACH_IDS
    if beach:
        visual_en, tags = _beach_visual(state.location_id, location.name, npc.name)
    else:
        visual_en = f"{npc.name}, standing, looking at camera, inside the {location.name}, detailed luxury resort interior"
        tags = ["NPC arrival", f"{location.name} interior"]
    mutations = [{
        "type": "location_change", "target": npc_id,
        "payload": {"location_id": state.location_id},
        "reason": "La NPC accetta la richiesta di raggiungere il giocatore.",
    }]
    if beach:
        mutations.extend(_beach_outfit_mutations(npc_id, npc))
    return FinalScene.from_dict(
        {
            "narration": f"La richiesta viene recapitata a {npc.name}. Poco dopo, {npc.name} ti raggiunge nella {location.name}.",
            "dialogue": [{"speaker": npc.name, "to": "player", "text": "Mi hai fatto chiamare. Eccomi qui: dimmi pure di cosa hai bisogno."}],
            "npc_actions": [{"npc_id": npc_id, "action": f"raggiunge il cliente VIP nella {location.name}"}],
            "intentions": [], "initiatives": [], "disclosure_events": [],
            "mutations": mutations,
            "memory_events": [],
            "visual": {
                "summary": f"{npc.name} raggiunge il cliente VIP nella {location.name}.",
                "focus_character": npc_id, "visible_characters": [npc_id],
                "shared_action": False,
                "visual_en": visual_en,
                "tags_en": tags,
                "moment_type": "speech", "speaker_character": npc_id,
                "actor_character": npc_id, "reactor_character": npc_id,
                "intimate_shared_moment": False, "multi_character_reason": "",
                "multi_character_participants": [npc_id],
            },
        }
    )


def _relax_scene(pack, state, npc_id: str) -> FinalScene:
    npc = state.npcs[npc_id]
    location = pack.locations[state.location_id]
    visual_en, tags = _beach_visual(state.location_id, location.name, npc.name)
    visual_en = visual_en.replace("arrives at", "relaxes at")
    return FinalScene.from_dict({
        "narration": f"Ti concedi finalmente un momento di quiete sulla {location.name}. {npc.name} resta vicino a te senza invadere il silenzio, lasciando che il rumore del mare accompagni il riposo.",
        "dialogue": [{"speaker": npc.name, "to": "player", "text": "Rilassati pure. Resto qui, senza disturbarti."}],
        "npc_actions": [{"npc_id": npc_id, "action": "si sistema poco distante e condivide un momento tranquillo sulla spiaggia"}],
        "intentions": [{"npc_id": npc_id, "intention": "lasciare al cliente VIP uno spazio tranquillo restando disponibile"}],
        "initiatives": [], "disclosure_events": [], "mutations": [], "memory_events": [],
        "visual": {
            "summary": f"{npc.name} condivide un momento tranquillo sulla {location.name}.",
            "focus_character": npc_id,
            "visible_characters": [npc_id],
            "shared_action": False,
            "visual_en": visual_en,
            "tags_en": [*tags, "quiet relaxation"],
            "moment_type": "speech",
            "speaker_character": npc_id,
            "actor_character": npc_id,
            "reactor_character": npc_id,
            "intimate_shared_moment": False,
            "multi_character_reason": "",
            "multi_character_participants": [npc_id],
        },
    })


def _hosiery_scene(pack, state, npc_id: str, item: str) -> FinalScene:
    npc = state.npcs[npc_id]
    location = pack.locations[state.location_id]
    footwear = list(getattr(npc.outfit, "footwear", []) or [])
    mutations = [
        {
            "type": "outfit_remove", "target": npc_id,
            "payload": {"item": shoe},
            "reason": "La richiesta specifica di indossare le pantyhose senza scarpe.",
        }
        for shoe in footwear
    ]
    if item not in list(getattr(npc.outfit, "worn_items", []) or []):
        mutations.append({
            "type": "outfit_wear", "target": npc_id,
            "payload": {"item": item},
            "reason": "La NPC aveva già accettato di indossare le pantyhose.",
        })

    return FinalScene.from_dict(
        {
            "narration": f"{npc.name} si sfila le scarpe e indossa le pantyhose nere come concordato.",
            "dialogue": [{"speaker": npc.name, "to": "player", "text": "Va bene. Le indosso senza scarpe, come mi hai chiesto."}],
            "npc_actions": [{"npc_id": npc_id, "action": "removes footwear and puts on black pantyhose"}],
            "intentions": [], "initiatives": [], "disclosure_events": [],
            "mutations": mutations,
            "memory_events": [],
            "visual": {
                "summary": f"{npc.name} indossa pantyhose nere senza scarpe.",
                "focus_character": npc_id, "visible_characters": [npc_id],
                "shared_action": False,
                "visual_en": f"{npc.name}, black pantyhose, barefoot, no shoes, standing inside the {location.name}, full body",
                "tags_en": ["black pantyhose", "barefoot", "no shoes", "full body", f"{location.name} interior"],
                "moment_type": "action", "speaker_character": "",
                "actor_character": npc_id, "reactor_character": "",
                "intimate_shared_moment": False, "multi_character_reason": "",
                "multi_character_participants": [npc_id],
            },
        }
    )


class ResortPlayableTurnService(ResortIntroTurnService):
    """Servizio di produzione usato dai launcher GUI e CLI del Resort."""

    def play(self, state, player_text: str):
        reconcile_resort_presence(state, player_text)
        hint = interpret_resort_intent(self.pack, state, player_text)
        directive = resort_intent_directive(hint)
        previous = str(getattr(state, "last_scene", "") or "").strip()
        state.last_scene = f"{previous}\n\n{directive}" if previous else directive

        initialise_resort_intro(state)
        if current_intro_step(state) is not None:
            return super().play(state, player_text)

        if state.location_id in _BEACH_IDS and _RELAX_RE.search(str(player_text or "")):
            present = [npc_id for npc_id in state.present_npc_ids() if npc_id in state.npcs]
            if len(present) == 1:
                scene = _relax_scene(self.pack, state, present[0])
                return self._commit_turn(state, state.turn, "no_check", scene, player_text=player_text)

        hosiery = _hosiery_request(state, player_text)
        if hosiery is not None:
            npc_id, item = hosiery
            scene = _hosiery_scene(self.pack, state, npc_id, item)
            return self._commit_turn(state, state.turn, "no_check", scene, player_text=player_text)

        npc_id = _summoned_npc_from_text(state, player_text)
        if npc_id is not None:
            scene = _summon_scene(self.pack, state, npc_id)
            return self._commit_turn(state, state.turn, "no_check", scene, player_text=player_text)

        destination_id = _destination_from_text(self.pack, player_text)
        if destination_id is not None:
            scene = _movement_scene(self.pack, state, destination_id)
            return self._commit_turn(state, state.turn, "no_check", scene, player_text=player_text)

        return super().play(state, player_text)

    def _validate_phase1_response_after_outfit_normalization(self, response, state, player_text: str):
        report = super()._validate_phase1_response_after_outfit_normalization(response, state, player_text)
        if response.mode != "no_check" or response.scene is None:
            return report
        report = _accept_real_npc_action(report, state, response.scene)
        return _allow_solo_navigation(report, response.scene)

    def _validate_scene_after_outfit_normalization(self, scene, state, player_text: str):
        report = super()._validate_scene_after_outfit_normalization(scene, state, player_text)
        report = _accept_real_npc_action(report, state, scene)
        return _allow_solo_navigation(report, scene)
