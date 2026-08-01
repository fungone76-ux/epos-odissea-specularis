"""Canonical outfit helpers.

This module keeps outfit state derived from ``character.outfit`` and provides
the deterministic bridge between unambiguous player clothing intent and runtime
mutations. The renderer and UI consume the result; they never decide outfit.

Pipeline per scena (``normalize_player_outfit_scene``):

1. **Riparazione payload**: le mutazioni outfit_wear/outfit_remove della LLM
   con payload non canonico (``{"items": [...]}``, ``{"removed_items": [...]}``,
   liste in ``item``) vengono esplose in mutazioni canoniche ``{"item": capo}``,
   una per capo. Le rimozioni di capi non indossati vengono scartate.
2. **Intento deterministico** dal testo del giocatore:
   - spogliarsi del tutto -> rimuove TUTTO ciò che è indossato, armi e
     accessori inclusi (restano in ``removed``, reindossabili);
   - togliere un capo specifico -> rimuove quel capo (anche armi/accessori);
   - indossare/rimettere un capo posseduto (``removed`` o ``inventory``);
   - indossare qualcosa di generico/nuovo -> nessuna mutazione deterministica:
     la LLM inventa i capi (vedi prompt), i conflitti sono risolti al punto 3.
3. **Conflitti di slot**: un capo indossato sostituisce i capi attualmente
   indossati che coprono le stesse parti del corpo (torso/lower/footwear).
   I capi sostituiti passano in ``removed``: non si perdono, si ripongono.
   Indossare calzature rimuove il descrittore ``barefoot``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from .contract import FinalScene, Mutation
from .models import (
    FOOTWEAR_TERMS,
    LOWER_CLOTHING_TERMS,
    TORSO_CLOTHING_TERMS,
    Outfit,
    PlayerState,
    WorldState,
    outfit_state,
)

VISUAL_DESCRIPTOR_ITEMS = {
    "bare thighs clearly visible",
    "exposed shoulders",
}

ACCESSORY_OR_WEAPON_TERMS = {
    "bow",
    "quiver",
    "strap",
    "straps",
    "sword",
    "spear",
    "knife",
    "dagger",
    "club",
    "shield",
}

COMPLETE_UNDRESS_HINTS = (
    "mi spoglio completamente",
    "mi spoglio del tutto",
    "mi tolgo tutto",
    "tolgo tutti i vestiti",
    "tolgo tutti gli abiti",
    "mi svesto completamente",
    "resto nuda",
    "rimango nuda",
    "resto nudo",
    "rimango nudo",
    "mi spoglio",
    "mi svesto",
    "si spoglia",
    "si sveste",
    "senza vestiti",
    "senza abiti",
    "tutta nuda",
    "tutto nudo",
    "completamente nuda",
    "completamente nudo",
)

# Pattern per flessioni di "nudo/a/i/e" legate al protagonista.
_COMPLETE_UNDRESS_PATTERNS = (
    re.compile(
        r"\b(?:resto|rimango|sono|restare|rimanere|vado|cammino|sto|"
        r"voglio\s+essere|ecco|ormai)\s+(?:\w+\s+){0,2}nud[aoie]\b"
    ),
)

REMOVE_HINTS = (
    "mi tolgo",
    "si toglie",
    "toglie",
    "tolgo",
    "rimuovo",
    "rimuove",
    "mi sfilo",
    "si sfila",
    "sfilo",
    "levo",
)
WEAR_HINTS = (
    "indosso",
    "indossa",
    "rimetto",
    "rimette",
    "mi metto",
    "si mette",
    "mettiti",
    "metto",
    "mi vesto",
    "si veste",
    "vestiti",
    "rivestiti",
    "mi rivesto",
    "si riveste",
)

ITEM_ALIASES = {
    "chitone": ("chiton",),
    "chiton": ("chiton",),
    "armatura": ("armor", "breastplate", "corselet"),
    "corazza": ("armor", "breastplate", "corselet"),
    "armor": ("armor",),
    "vestito": ("dress", "robe", "peplos", "himation", "chiton"),
    "abito": ("dress", "robe", "peplos", "himation", "chiton"),
    "mantello": ("cloak", "himation"),
    "sandali": ("sandals",),
    "stivali": ("boots",),
    "scarpe": ("shoes", "sandals", "boots"),
    "calzature": ("sandals", "boots", "shoes"),
    "arco": ("bow",),
    "faretra": ("quiver",),
    "pugnale": ("dagger", "knife"),
    "spada": ("sword",),
    "lancia": ("spear",),
    "cintura": ("belt",),
}

# Chiavi di payload non canoniche che la LLM usa al posto di {"item": ...}.
_NONCANONICAL_LIST_KEYS = (
    "items",
    "removed_items",
    "worn_items",
    "item_list",
    "clothing_items",
    "garments",
)

_REASON_REPAIR = "Riparazione deterministica payload outfit non canonico."
_REASON_INTENT = "Deterministic outfit normalization from explicit player input."
_REASON_CONFLICT = "Sostituzione automatica: il nuovo capo copre la stessa parte del corpo."


@dataclass(frozen=True)
class OutfitUiState:
    value: str
    items: list[str]


@dataclass(frozen=True)
class OutfitNormalizationResult:
    scene: FinalScene
    intent_detected: str
    mutations_requested: list[dict[str, Any]]
    mutations_normalized: list[dict[str, Any]]
    problems: list[str]

    @property
    def changed(self) -> bool:
        return bool(self.mutations_normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outfit_intent_detected": self.intent_detected,
            "outfit_mutations_requested": list(self.mutations_requested),
            "outfit_mutations_normalized": list(self.mutations_normalized),
            "outfit_normalization_problems": list(self.problems),
        }


def is_visual_descriptor(item: str) -> bool:
    text = item.strip().lower()
    return text in VISUAL_DESCRIPTOR_ITEMS or text == "barefoot"


def is_clothing_item(item: str) -> bool:
    text = item.strip().lower()
    if not text or is_visual_descriptor(text):
        return False
    if any(term in text for term in ACCESSORY_OR_WEAPON_TERMS):
        return False
    clothing_terms = TORSO_CLOTHING_TERMS | LOWER_CLOTHING_TERMS | FOOTWEAR_TERMS
    return any(term in text for term in clothing_terms)


def real_worn_clothing(outfit: Outfit) -> list[str]:
    return [item for item in outfit.worn if is_clothing_item(item)]


def item_slots(item: str) -> set[str]:
    """Parti del corpo coperte da un capo: torso / lower / footwear."""

    text = item.strip().lower()
    slots: set[str] = set()
    if any(term in text for term in TORSO_CLOTHING_TERMS):
        slots.add("torso")
    if any(term in text for term in LOWER_CLOTHING_TERMS):
        slots.add("lower")
    if any(term in text for term in FOOTWEAR_TERMS):
        slots.add("footwear")
    return slots


def format_current_outfit_for_ui(character_state: PlayerState) -> OutfitUiState:
    state = outfit_state(character_state.outfit)
    torso = [item for item in state["torso_slot"] if is_clothing_item(item)]
    lower = [item for item in state["lower_body_slot"] if is_clothing_item(item)]
    footwear = [item for item in state["footwear"] if is_clothing_item(item)]
    items = []
    for item in [*torso, *lower, *footwear]:
        if item not in items:
            items.append(item)
    if not torso and not lower:
        return OutfitUiState("Nuda", [])
    if not torso:
        return OutfitUiState("Topless", [*lower, *footwear])
    if not lower:
        return OutfitUiState("Senza abiti nella parte inferiore", [*torso, *footwear])
    return OutfitUiState("Indossa", items)


# ---------------------------------------------------------------------------
# Normalizzazione della scena
# ---------------------------------------------------------------------------


def normalize_player_outfit_scene(
    state: WorldState,
    player_text: str,
    scene: FinalScene,
) -> OutfitNormalizationResult:
    problems: list[str] = []

    # 1. ripara i payload outfit non canonici della LLM
    repaired_scene, repair_notes = _repair_outfit_mutations(state, scene)
    problems.extend(repair_notes)

    requested = [
        _mutation_to_dict(m)
        for m in repaired_scene.mutations
        if _is_player_outfit_mutation(m)
    ]

    # 2. intento deterministico dal testo del giocatore
    intent, intent_mutations, intent_problems = _detect_player_outfit_mutations(
        state, player_text
    )
    problems.extend(intent_problems)

    existing_keys = {_mutation_key(m) for m in repaired_scene.mutations}
    additions = [m for m in intent_mutations if _mutation_key(m) not in existing_keys]
    combined = [*repaired_scene.mutations, *additions]

    # 3. conflitti di slot: i capi indossati sostituiscono quelli che coprono
    #    le stesse parti del corpo (auto-rimozione in `removed`)
    conflict_removals = _slot_conflict_removals(state, combined)

    normalized = [_mutation_to_dict(m) for m in [*additions, *conflict_removals]]
    final_mutations = [*combined, *conflict_removals]
    if not normalized and repaired_scene is scene:
        return OutfitNormalizationResult(scene, intent, requested, [], problems)
    return OutfitNormalizationResult(
        replace(scene, mutations=final_mutations),
        intent,
        requested,
        normalized,
        problems,
    )


def normalize_player_outfit_phase_response(
    state: WorldState,
    player_text: str,
    response,
):
    if response.mode != "no_check" or response.scene is None:
        return response, OutfitNormalizationResult(
            response.scene,
            "none",
            [],
            [],
            [],
        )
    result = normalize_player_outfit_scene(state, player_text, response.scene)
    if result.scene is response.scene:
        return response, result
    return replace(response, scene=result.scene), result


# ---------------------------------------------------------------------------
# 1. riparazione payload non canonici
# ---------------------------------------------------------------------------


def _repair_outfit_mutations(
    state: WorldState, scene: FinalScene
) -> tuple[FinalScene, list[str]]:
    """Esplode payload outfit non canonici in mutazioni {"item": capo}.

    La LLM a volte produce {"removed_items": [...]}, {"items": [...]} oppure
    una lista dentro "item". Il contratto canonico vuole UNA mutazione per
    capo: qui la ripariamo invece di rifiutarla. Le rimozioni di capi non
    indossati vengono scartate (non possono fallire in validazione).
    """

    notes: list[str] = []
    repaired: list[Mutation] = []
    changed = False

    for mutation in scene.mutations:
        if mutation.type not in ("outfit_wear", "outfit_remove"):
            repaired.append(mutation)
            continue

        payload = mutation.payload or {}
        raw_item = payload.get("item")
        items: list[str] = []
        mutation_changed = False

        if isinstance(raw_item, str) and raw_item.strip():
            items = [raw_item.strip()]
        else:
            mutation_changed = True
            collected: list[str] = []
            if isinstance(raw_item, (list, tuple)):
                collected.extend(str(x).strip() for x in raw_item)
            for key in _NONCANONICAL_LIST_KEYS:
                value = payload.get(key)
                if isinstance(value, (list, tuple)):
                    collected.extend(str(x).strip() for x in value)
                elif isinstance(value, str) and value.strip():
                    collected.append(value.strip())
            items = [x for x in dict.fromkeys(collected) if x]
            notes.append(
                f"{mutation.type}: payload non canonico {sorted(payload)} "
                f"riparato in {len(items)} mutazioni canoniche"
            )

        if not items:
            notes.append(f"{mutation.type}: nessun capo valido, mutazione eliminata")
            changed = True
            continue

        character = state.player if mutation.target == "player" else state.npcs.get(
            mutation.target
        )
        worn = character.outfit.worn if character is not None else []

        kept: list[str] = []
        for item in items:
            if mutation_changed and mutation.type == "outfit_remove" and item not in worn:
                notes.append(
                    f"outfit_remove scartato: {item!r} non indossato da "
                    f"{mutation.target!r}"
                )
                continue
            kept.append(item)

        if not kept:
            changed = True
            continue

        if not mutation_changed:
            repaired.append(mutation)
            continue

        changed = True
        for item in kept:
            repaired.append(
                Mutation(
                    type=mutation.type,
                    target=mutation.target,
                    payload={"item": item},
                    reason=mutation.reason or _REASON_REPAIR,
                )
            )

    if not changed:
        return scene, notes
    return replace(scene, mutations=repaired), notes


# ---------------------------------------------------------------------------
# 2. intento deterministico dal testo del giocatore
# ---------------------------------------------------------------------------


def _is_complete_undress(text: str) -> bool:
    if any(hint in text for hint in COMPLETE_UNDRESS_HINTS):
        return True
    return any(pattern.search(text) for pattern in _COMPLETE_UNDRESS_PATTERNS)


def _detect_player_outfit_mutations(
    state: WorldState,
    player_text: str,
) -> tuple[str, list[Mutation], list[str]]:
    text = _normalize_text(player_text)
    worn = [item for item in state.player.outfit.worn if str(item).strip()]

    # spogliarsi del tutto: via TUTTO ciò che è indossato, armi e accessori
    # inclusi. I capi restano in `removed`, reindossabili.
    if _is_complete_undress(text):
        return (
            "remove_all_worn_clothing",
            [
                Mutation(
                    type="outfit_remove",
                    target="player",
                    payload={"item": item},
                    reason=_REASON_INTENT,
                )
                for item in real_worn_clothing(state.player.outfit)
            ],
            [],
        )

    for hint in REMOVE_HINTS:
        if hint in text:
            candidates = [item for item in worn if not is_visual_descriptor(item)]
            item = _resolve_named_item(text, candidates)
            if item:
                return (
                    "remove_named_worn_item",
                    [
                        Mutation(
                            type="outfit_remove",
                            target="player",
                            payload={"item": item},
                            reason=_REASON_INTENT,
                        )
                    ],
                    [],
                )
            return "remove_named_unresolved", [], []

    for hint in WEAR_HINTS:
        if hint in text:
            available = [
                item
                for item in [*state.player.outfit.removed, *state.player.inventory]
                if str(item).strip()
            ]
            item = _resolve_named_item(text, available)
            if item:
                return (
                    "wear_owned_item",
                    [
                        Mutation(
                            type="outfit_wear",
                            target="player",
                            payload={"item": item},
                            reason=_REASON_INTENT,
                        )
                    ],
                    [],
                )
            # intento generico ("indossa qualcosa di sexy", "mettiti un
            # abito elegante"): nessuna mutazione deterministica — la LLM
            # inventa i capi (regole nel prompt) e i conflitti di slot
            # vengono risolti dal normalizzatore.
            return "wear_generic_new", [], []

    return "none", [], []


# ---------------------------------------------------------------------------
# 3. conflitti di slot
# ---------------------------------------------------------------------------


def _slot_conflict_removals(
    state: WorldState, mutations: list[Mutation]
) -> list[Mutation]:
    """Auto-rimozione dei capi che confliggono con i capi appena indossati.

    Un capo indossato (outfit_wear) sostituisce i capi attualmente indossati
    che coprono le stesse parti del corpo. I capi sostituiti vanno in
    `removed` (riposti, reindossabili). Indossare calzature rimuove anche
    il descrittore "barefoot".
    """

    worn = [item for item in state.player.outfit.worn if str(item).strip()]
    existing_keys = {_mutation_key(m) for m in mutations}

    # le rimozioni già presenti in scena aggiornano la simulazione
    for mutation in mutations:
        if mutation.type == "outfit_remove" and mutation.target == "player":
            item = str(mutation.payload.get("item", "")).strip()
            if item in worn:
                worn.remove(item)

    removals: list[Mutation] = []
    removal_keys: set[tuple[str, str, str]] = set()

    def _queue_removal(item: str) -> None:
        key = ("outfit_remove", "player", item)
        if key in existing_keys or key in removal_keys:
            return
        removal_keys.add(key)
        removals.append(
            Mutation(
                type="outfit_remove",
                target="player",
                payload={"item": item},
                reason=_REASON_CONFLICT,
            )
        )
        if item in worn:
            worn.remove(item)

    for mutation in mutations:
        if mutation.type != "outfit_wear" or mutation.target != "player":
            continue
        new_item = str(mutation.payload.get("item", "")).strip()
        if not new_item:
            continue
        new_slots = item_slots(new_item)
        if "footwear" in new_slots and "barefoot" in worn:
            _queue_removal("barefoot")
        for old in list(worn):
            if old == new_item or not is_clothing_item(old):
                continue
            if item_slots(old) & new_slots:
                _queue_removal(old)
        if new_item not in worn:
            worn.append(new_item)

    return removals


# ---------------------------------------------------------------------------
# utilità
# ---------------------------------------------------------------------------


def _resolve_named_item(text: str, items: list[str]) -> str | None:
    candidates = [item for item in items if str(item).strip()]
    for item in candidates:
        lowered = item.lower()
        if any(token and token in text for token in _meaningful_tokens(lowered)):
            return item
    for alias, terms in ITEM_ALIASES.items():
        if alias in text:
            matches = [item for item in candidates if any(term in item.lower() for term in terms)]
            if len(matches) == 1:
                return matches[0]
    return None


def _meaningful_tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z]{4,}", text)
        if token not in {"with", "worn", "very", "short", "deep", "revealing"}
    ]


def _normalize_text(text: str) -> str:
    return (
        text.casefold()
        .replace("'", " ")
        .replace("’", " ")
        .replace("à", "a")
        .replace("è", "e")
        .replace("é", "e")
        .replace("ì", "i")
        .replace("ò", "o")
        .replace("ù", "u")
    )


def _is_player_outfit_mutation(mutation: Mutation) -> bool:
    return mutation.target == "player" and mutation.type in ("outfit_wear", "outfit_remove")


def _mutation_key(mutation: Mutation) -> tuple[str, str, str]:
    return (mutation.type, mutation.target, str(mutation.payload.get("item", "")))


def _mutation_to_dict(mutation: Mutation) -> dict[str, Any]:
    return {
        "type": mutation.type,
        "target": mutation.target,
        "payload": dict(mutation.payload),
        "reason": mutation.reason,
    }
