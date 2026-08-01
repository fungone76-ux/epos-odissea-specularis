"""Single-call intent guidance for the Resort runtime.

No provider call is added.  Python derives a conservative intent hint from the
player text and injects it into the same canonical snapshot already sent to the
Game Master.  The existing GM call must then both interpret and produce the
scene while respecting explicit NPC-response and visual requirements.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ResortIntentHint:
    intent: str
    target_npc: str = ""
    location_target: str = ""
    requires_npc_response: bool = False
    requires_location_change: bool = False
    requires_visual: bool = True
    visual_focus: str = ""
    visual_requirements: tuple[str, ...] = ()


_MOVE_WORDS = re.compile(
    r"\b(?:vado|andiamo|voglio andare|vorrei andare|mi reco|raggiungo|torno|ritorno|spost)\w*\b",
    re.IGNORECASE,
)
_ASK_SELF = re.compile(
    r"\b(?:raccontami di te|parlami di te|dimmi di te|chi sei|cosa vuoi|cosa desideri)\b",
    re.IGNORECASE,
)
_SOCIAL = re.compile(
    r"\b(?:dimmi|raccontami|parlami|rispondimi|guardami|avvicinati|vieni|resta|siediti|"
    r"aiutami|mostrami|fammi vedere|cosa ne pensi|che ne pensi|come stai)\b",
    re.IGNORECASE,
)
_RELAX = re.compile(
    r"\b(?:mi rilasso|rilassarmi|mi riposo|riposarmi|prendo il sole|mi sdraio|mi stendo|relax)\b",
    re.IGNORECASE,
)

_LOCATION_ALIASES = {
    "loc_suite": ("suite", "camera", "stanza"),
    "loc_lobby": ("lobby", "reception", "atrio"),
    "loc_restaurant": ("ristorante",),
    "loc_pool": ("piscina",),
    "loc_spa": ("spa", "sauna", "centro benessere"),
    "loc_private_beach": ("spiaggia privata", "spiaggia"),
    "loc_wild_beach": ("spiaggia selvaggia", "cala", "cala rocciosa"),
    "loc_lounge": ("lounge", "bar", "cocktail bar"),
    "loc_victoria_office": ("ufficio di victoria", "ufficio victoria"),
}


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


def _target_npc(state, text: str) -> str:
    normalized = _plain(text)
    mentioned: list[str] = []
    for npc_id, npc in state.npcs.items():
        names = {_plain(npc_id), _plain(getattr(npc, "name", ""))}
        full_name = _plain(getattr(npc, "name", ""))
        if full_name:
            names.add(full_name.split()[0])
        if any(name and re.search(rf"\b{re.escape(name)}\b", normalized) for name in names):
            mentioned.append(npc_id)
    if len(mentioned) == 1:
        return mentioned[0]
    present = [npc_id for npc_id in state.present_npc_ids() if npc_id in state.npcs]
    return present[0] if len(present) == 1 else ""


def _location_target(pack, text: str) -> str:
    normalized = _plain(text)
    # Specific aliases first so "spiaggia selvaggia" never collapses to generic beach.
    ordered = [
        "loc_wild_beach",
        "loc_private_beach",
        "loc_suite",
        "loc_lobby",
        "loc_restaurant",
        "loc_pool",
        "loc_spa",
        "loc_lounge",
        "loc_victoria_office",
    ]
    for location_id in ordered:
        if location_id not in pack.locations:
            continue
        if any(_plain(alias) in normalized for alias in _LOCATION_ALIASES[location_id]):
            return location_id
    return ""


def interpret_resort_intent(pack, state, player_text: str) -> ResortIntentHint:
    text = _plain(player_text)
    target = _target_npc(state, text)
    destination = _location_target(pack, text) if _MOVE_WORDS.search(text) else ""

    if destination:
        requirements = (
            "canonical destination environment",
            "outdoor setting" if "beach" in destination or destination == "loc_pool" else "location-accurate setting",
        )
        return ResortIntentHint(
            intent="move",
            location_target=destination,
            requires_location_change=True,
            requires_visual=False,
            visual_requirements=requirements,
        )

    if _ASK_SELF.search(text):
        return ResortIntentHint(
            intent="ask_npc_about_self",
            target_npc=target,
            requires_npc_response=bool(target),
            visual_focus=target,
            visual_requirements=("target NPC only", "location-accurate background"),
        )

    if _RELAX.search(text):
        return ResortIntentHint(
            intent="relax",
            target_npc=target,
            requires_npc_response=bool(target),
            visual_focus=target,
            visual_requirements=("quiet relaxation", "location-accurate background"),
        )

    if _SOCIAL.search(text) or target:
        return ResortIntentHint(
            intent="interact_with_npc",
            target_npc=target,
            requires_npc_response=bool(target),
            visual_focus=target,
            visual_requirements=("target NPC performs the visible action", "player remains off-camera"),
        )

    return ResortIntentHint(intent="free_action", requires_visual=True)


def _directive(hint: ResortIntentHint) -> str:
    requirements = ", ".join(hint.visual_requirements) or "none"
    parts = [
        "RESORT SINGLE-CALL INTENT CONTRACT",
        f"intent={hint.intent}",
        f"target_npc={hint.target_npc or 'none'}",
        f"location_target={hint.location_target or 'none'}",
        f"requires_npc_response={'true' if hint.requires_npc_response else 'false'}",
        f"requires_location_change={'true' if hint.requires_location_change else 'false'}",
        f"requires_visual={'true' if hint.requires_visual else 'false'}",
        f"visual_focus={hint.visual_focus or 'none'}",
        f"visual_requirements={requirements}",
    ]
    if hint.requires_npc_response:
        parts.append(
            "MANDATORY: the target NPC must personally respond in dialogue, npc_actions, or initiatives. "
            "Narration or visual description alone is invalid."
        )
    if hint.visual_focus:
        parts.append(
            f"MANDATORY VISUAL: focus_character and visible_characters must use '{hint.visual_focus}', "
            "never player and never the placeholder npc_id."
        )
    if hint.requires_location_change:
        parts.append(
            f"MANDATORY MUTATION: include the canonical player location change to '{hint.location_target}'."
        )
    return " | ".join(parts)


def install_resort_single_call_intent_patch() -> None:
    from . import resort_playable_turn_service as playable

    if getattr(playable, "_single_call_intent_patch_installed", False):
        return

    original_play = playable.ResortPlayableTurnService.play

    def patched_play(self, state, player_text: str):
        hint = interpret_resort_intent(self.pack, state, player_text)
        # last_scene is already included in the existing canonical snapshot.  Appending
        # this directive changes only the content of that one provider request.
        previous = str(getattr(state, "last_scene", "") or "").strip()
        directive = _directive(hint)
        state.last_scene = f"{previous}\n\n{directive}" if previous else directive
        return original_play(self, state, player_text)

    playable.ResortPlayableTurnService.play = patched_play
    playable._single_call_intent_patch_installed = True
