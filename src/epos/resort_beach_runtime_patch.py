"""Runtime fixes for Resort beach summons and quiet relaxation turns."""

from __future__ import annotations

import re
from typing import Any

from .contract import FinalScene

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


def _manual_outfit_override(npc: Any) -> bool:
    outfit = getattr(npc, "outfit", None)
    return int(getattr(outfit, "revision", 0) or 0) > 0


def _beach_outfit_mutations(npc_id: str, npc: Any) -> list[dict[str, Any]]:
    if _manual_outfit_override(npc):
        return []
    target_items = _BEACH_OUTFITS.get(npc_id)
    if not target_items:
        return []
    worn = [str(item) for item in getattr(getattr(npc, "outfit", None), "worn", [])]
    mutations: list[dict[str, Any]] = [
        {
            "type": "outfit_remove",
            "target": npc_id,
            "payload": {"item": item},
            "reason": "Cambio automatico all'outfit da spiaggia perché non esiste un override manuale.",
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


def _patched_summon_scene(pack, state, npc_id: str) -> FinalScene:
    npc = state.npcs[npc_id]
    location = pack.locations[state.location_id]
    beach = state.location_id in _BEACH_IDS
    if beach:
        visual_en, tags = _beach_visual(state.location_id, location.name, npc.name)
    else:
        visual_en = f"{npc.name}, standing, looking at camera, inside the {location.name}, detailed luxury resort interior"
        tags = ["NPC arrival", f"{location.name} interior"]

    mutations = [{
        "type": "location_change",
        "target": npc_id,
        "payload": {"location_id": state.location_id},
        "reason": "La NPC accetta la richiesta di raggiungere il giocatore.",
    }]
    if beach:
        mutations.extend(_beach_outfit_mutations(npc_id, npc))

    return FinalScene.from_dict({
        "narration": f"La richiesta viene recapitata a {npc.name}. Poco dopo, {npc.name} ti raggiunge nella {location.name}.",
        "dialogue": [{"speaker": npc.name, "to": "player", "text": "Mi hai fatto chiamare. Eccomi qui: dimmi pure di cosa hai bisogno."}],
        "npc_actions": [{"npc_id": npc_id, "action": f"raggiunge il cliente VIP nella {location.name}"}],
        "intentions": [], "initiatives": [], "disclosure_events": [],
        "mutations": mutations,
        "memory_events": [],
        "visual": {
            "summary": f"{npc.name} raggiunge il cliente VIP nella {location.name}.",
            "focus_character": npc_id,
            "visible_characters": [npc_id],
            "shared_action": False,
            "visual_en": visual_en,
            "tags_en": tags,
            "moment_type": "speech",
            "speaker_character": npc_id,
            "actor_character": npc_id,
            "reactor_character": npc_id,
            "intimate_shared_moment": False,
            "multi_character_reason": "",
            "multi_character_participants": [npc_id],
        },
    })


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


def install_resort_beach_runtime_patch() -> None:
    from . import resort_playable_turn_service as module

    if getattr(module, "_beach_runtime_patch_installed", False):
        return

    module._summon_scene = _patched_summon_scene
    original_play = module.ResortPlayableTurnService.play

    def patched_play(self, state, player_text: str):
        if (
            state.location_id in _BEACH_IDS
            and _RELAX_RE.search(str(player_text or ""))
        ):
            present = [npc_id for npc_id in state.present_npc_ids() if npc_id in state.npcs]
            if len(present) == 1:
                scene = _relax_scene(self.pack, state, present[0])
                return self._commit_turn(state, state.turn, "no_check", scene, player_text=player_text)
        return original_play(self, state, player_text)

    module.ResortPlayableTurnService.play = patched_play
    module._beach_runtime_patch_installed = True
