"""Single-call intent guidance for the Resort runtime.

Python derives a conservative intent hint from the player's text and injects it
into the same canonical snapshot already sent to the Game Master. No extra LLM
call is introduced. Explicit visual and outfit-action requests are represented
as structured mandatory requirements so they survive scene planning, state
mutation and prompt construction.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class VisualRequirement:
    kind: str
    value: str
    priority: str = "high"
    mandatory: bool = True


@dataclass(frozen=True)
class ResortIntentHint:
    intent: str
    target_npc: str = ""
    location_target: str = ""
    requires_npc_response: bool = False
    requires_location_change: bool = False
    requires_visual: bool = True
    visual_focus: str = ""
    visual_requirements: tuple[VisualRequirement, ...] = ()


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
    r"aiutami|mostrami|fammi vedere|fai vedere|girarti|girati|voltati|posa|mettiti|"
    r"togli|togliti|rimuovi|sfila|slaccia|apri|abbassa|alza|indossa|metti|"
    r"cosa ne pensi|che ne pensi|come stai)\b",
    re.IGNORECASE,
)
_VISUAL_REQUEST = re.compile(
    r"\b(?:mostrami|fammi vedere|fai vedere|voglio vedere|vorrei vedere|inquadr|"
    r"primo piano|da vicino|di schiena|profilo|girarti|girati|voltati|posa|mettiti|"
    r"togli|togliti|rimuovi|sfila|slaccia|apri|abbassa|alza|indossa|metti)\w*\b",
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

_VISUAL_ALIASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("body_part", "feet", ("piede", "piedi", "piedini", "dita dei piedi")),
    ("body_part", "hands", ("mano", "mani", "dita")),
    ("body_part", "face", ("viso", "volto", "faccia", "occhi", "sguardo")),
    ("body_part", "chest", ("petto", "seno", "seni", "tette", "scollatura")),
    ("body_part", "legs", ("gamba", "gambe", "cosce")),
    ("body_part", "back", ("schiena", "dorso")),
    ("body_part", "hair", ("capelli", "chioma")),
    ("body_part", "tattoo", ("tatuaggio", "tatuaggi")),
    ("outfit", "outfit", ("vestito", "abito", "outfit", "bikini", "scarpe", "gioiello", "collana")),
    ("orientation", "back_view", ("di schiena", "da dietro", "voltati", "girati")),
    ("orientation", "front_view", ("di fronte", "frontalmente", "frontale")),
    ("orientation", "side_view", ("di profilo", "laterale", "di lato")),
    ("camera", "close_up", ("primo piano", "da vicino", "ravvicinato")),
    ("camera", "full_body", ("figura intera", "corpo intero", "dalla testa ai piedi")),
    ("camera", "low_angle", ("dal basso", "inquadratura bassa", "angolazione bassa")),
    ("camera", "high_angle", ("dall'alto", "inquadratura alta", "angolazione alta")),
    ("pose", "sitting", ("seduta", "siediti", "sedersi")),
    ("pose", "lying", ("sdraiata", "sdraiati", "stesa")),
    ("pose", "standing", ("in piedi", "alzati")),
    ("pose", "kneeling", ("in ginocchio", "inginocchiata")),
)

_OUTFIT_ITEMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bra", ("reggiseno", "reggiseni")),
    ("bikini_top", ("top del bikini", "bikini top", "pezzo sopra del bikini", "parte sopra del bikini")),
    ("bikini_bottom", ("slip del bikini", "bikini bottom", "pezzo sotto del bikini", "parte sotto del bikini")),
    ("bikini", ("bikini",)),
    ("sarong", ("sarong", "pareo")),
    ("dress", ("vestito", "abito")),
    ("shirt", ("camicia", "maglia", "top")),
    ("skirt", ("gonna",)),
    ("trousers", ("pantaloni",)),
    ("underwear", ("intimo", "mutandine", "slip")),
    ("shoes", ("scarpe", "tacchi", "sandali")),
    ("accessory", ("collana", "gioiello", "occhiali")),
)

_REMOVE_ACTION = re.compile(r"\b(?:togli|togliti|rimuovi|sfila|levati|slaccia|apri|abbassa|scopri)\w*\b", re.IGNORECASE)
_WEAR_ACTION = re.compile(r"\b(?:indossa|mettiti|metti|rimetti|infila)\w*\b", re.IGNORECASE)


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
    ordered = [
        "loc_wild_beach", "loc_private_beach", "loc_suite", "loc_lobby",
        "loc_restaurant", "loc_pool", "loc_spa", "loc_lounge", "loc_victoria_office",
    ]
    for location_id in ordered:
        if location_id not in pack.locations:
            continue
        if any(_plain(alias) in normalized for alias in _LOCATION_ALIASES[location_id]):
            return location_id
    return ""


def _outfit_item(text: str) -> str:
    for canonical, aliases in _OUTFIT_ITEMS:
        if any(_plain(alias) in text for alias in aliases):
            return canonical
    return ""


def _extract_visual_requirements(player_text: str) -> tuple[VisualRequirement, ...]:
    text = _plain(player_text)
    requirements: list[VisualRequirement] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str) -> None:
        key = (kind, value)
        if key not in seen:
            requirements.append(VisualRequirement(kind=kind, value=value))
            seen.add(key)

    for kind, value, aliases in _VISUAL_ALIASES:
        if any(_plain(alias) in text for alias in aliases):
            add(kind, value)

    item = _outfit_item(text)
    if item and _REMOVE_ACTION.search(text):
        add("action", f"remove_outfit_item:{item}")
        add("outfit_state", f"removed:{item}")
        add("state_mutation", f"move_item_from_worn_to_removed:{item}")
        add("prompt_constraint", f"forbid_worn_item:{item}")
    elif item and _WEAR_ACTION.search(text):
        add("action", f"wear_outfit_item:{item}")
        add("outfit_state", f"worn:{item}")
        add("state_mutation", f"move_item_to_worn:{item}")
        add("prompt_constraint", f"require_worn_item:{item}")

    if _VISUAL_REQUEST.search(text) and requirements:
        add("visibility", "clear_and_unobstructed")
        add("framing", "must_include_all_requested_elements")

    return tuple(requirements)


def interpret_resort_intent(pack, state, player_text: str) -> ResortIntentHint:
    text = _plain(player_text)
    target = _target_npc(state, text)
    destination = _location_target(pack, text) if _MOVE_WORDS.search(text) else ""
    explicit_visual = _extract_visual_requirements(player_text)

    if destination:
        requirements = (
            VisualRequirement("environment", "canonical_destination"),
            VisualRequirement("environment", "outdoor_setting" if "beach" in destination or destination == "loc_pool" else "location_accurate_setting"),
        )
        return ResortIntentHint(intent="move", location_target=destination, requires_location_change=True, requires_visual=False, visual_requirements=requirements)

    base: tuple[VisualRequirement, ...] = explicit_visual
    if target:
        base += (VisualRequirement("subject", target), VisualRequirement("composition", "player_off_camera"))

    if _ASK_SELF.search(text):
        return ResortIntentHint(intent="ask_npc_about_self", target_npc=target, requires_npc_response=bool(target), visual_focus=target, visual_requirements=base + (VisualRequirement("environment", "location_accurate_background"),))
    if _RELAX.search(text):
        return ResortIntentHint(intent="relax", target_npc=target, requires_npc_response=bool(target), visual_focus=target, visual_requirements=base + (VisualRequirement("action", "quiet_relaxation"),))
    if _SOCIAL.search(text) or target or explicit_visual:
        return ResortIntentHint(intent="interact_with_npc", target_npc=target, requires_npc_response=bool(target), visual_focus=target, visual_requirements=base)
    return ResortIntentHint(intent="free_action", requires_visual=True)


def _serialize_requirement(requirement: VisualRequirement) -> str:
    return f"kind={requirement.kind};value={requirement.value};priority={requirement.priority};mandatory={'true' if requirement.mandatory else 'false'}"


def _directive(hint: ResortIntentHint) -> str:
    requirements = " || ".join(_serialize_requirement(item) for item in hint.visual_requirements) or "none"
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
        parts.append("MANDATORY: the target NPC must personally respond in dialogue, npc_actions, or initiatives. Narration or visual description alone is invalid.")
    if hint.visual_focus:
        parts.append(f"MANDATORY VISUAL SUBJECT: focus_character and visible_characters must use '{hint.visual_focus}', never player and never the placeholder npc_id.")
    if hint.visual_requirements:
        parts.append("MANDATORY VISUAL FIDELITY: every mandatory visual requirement must be represented explicitly in visual.summary, visual.visual_en and visual.tags_en and survive into the renderer prompt.")
    outfit_actions = [item.value for item in hint.visual_requirements if item.kind == "state_mutation"]
    if outfit_actions:
        parts.append("MANDATORY OUTFIT ACTION: on success, the requested outfit action must occur literally, npc_actions must describe it, mutations must update the canonical outfit, removed/worn slots and nudity_mode must be coherent, and the final positive prompt must reflect the post-action outfit. A generic approach, smile, flirtation or dialogue is not fulfillment. A success response with mutations=[] is invalid. Never include a removed item as still worn in the positive prompt. Required mutations: " + ", ".join(outfit_actions))
    if hint.requires_location_change:
        parts.append(f"MANDATORY MUTATION: include the canonical player location change to '{hint.location_target}'.")
    return " | ".join(parts)


def install_resort_single_call_intent_patch() -> None:
    from . import resort_playable_turn_service as playable

    if getattr(playable, "_single_call_intent_patch_installed", False):
        return
    original_play = playable.ResortPlayableTurnService.play

    def patched_play(self, state, player_text: str):
        hint = interpret_resort_intent(self.pack, state, player_text)
        previous = str(getattr(state, "last_scene", "") or "").strip()
        directive = _directive(hint)
        state.last_scene = f"{previous}\n\n{directive}" if previous else directive
        return original_play(self, state, player_text)

    playable.ResortPlayableTurnService.play = patched_play
    playable._single_call_intent_patch_installed = True
