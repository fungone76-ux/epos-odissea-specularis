"""Visual contract e compilazione del prompt package.

Regole obbligatorie:
- presenti, visibili e focus sono concetti distinti;
- nessun assente può apparire;
- l'outfit autorevole viene dallo stato, mai riscritto dalla LLM;
- il base prompt di ogni personaggio è immutabile: il runtime lo copia
  esattamente, senza ripulirlo, tradurlo o migliorarlo.

Il prompt positivo è soltanto:
    BASE_PROMPT di ogni personaggio visibile (+ sua regola di stile)
    + outfit autorevole corrente
    + visual_en
    + tags_en
    + suffisso globale di pack (una sola volta)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from .contract import VisualMoment
from .models import WorldState, outfit_state
from .schemas import validate_visual_contract_shape
from .visual_director import direct_visual
from .visual_sanitizer import (
    _BROKEN_GENERATED_CHUNK_PATTERNS,
    _CLOSE_CAMERA,
    _FACIAL_EXPRESSION_PATTERNS,
    _FULL_BODY_CAMERA,
    _IDENTITY_TEXT_PATTERNS,
    _WIDE_CAMERA,
    _remove_camera_conflicts_from_text,
    _resolve_camera_conflicts,
    _sanitize_broken_generated_tags,
    _sanitize_broken_generated_text,
    _sanitize_facial_tags,
    _sanitize_facial_text,
    _sanitize_identity_tags,
    _sanitize_identity_text,
)
from .worldpack import WorldPack

# Negativo corto in stile Pony/SDXL: i negativi lunghi diluiscono
# l'attenzione e peggiorano il risultato. Le esclusioni specifiche del
# mondo restano in `negative_extra_en` del pack; quelle di scena al
# visual del turno.
DEFAULT_NEGATIVE = (
    "score_6, score_5, score_4, score_3, score_2, score_1, lowres, "
    "worst quality, low quality, blurry, bad anatomy, bad hands, "
    "extra fingers, missing fingers, extra limbs, deformed, "
    "text, watermark, signature, child, young-looking"
)


@dataclass(frozen=True)
class VisualContract:
    turn: int
    location_id: str
    moment: str
    focus_character: str
    visible_characters: list[str]
    shared_action: bool
    characters: list[dict[str, Any]]  # outfit autorevole al momento dello scatto
    time_phase: str
    visual_en: str
    tags_en: list[str] = field(default_factory=list)
    prompt_package: dict[str, Any] = field(default_factory=dict)
    focus_reason: str = ""
    multi_character_reason: str = ""
    camera_director: dict[str, Any] = field(default_factory=dict)
    concrete_action: str = ""
    place: str = ""
    canonical_outfit: dict[str, Any] = field(default_factory=dict)
    pose: str = ""
    shot_type: str = ""
    camera_side: str = ""
    camera_angle: str = ""
    lighting: str = ""
    positive_prompt: str = ""
    negative_prompt: str = ""
    visual_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "location_id": self.location_id,
            "moment": self.moment,
            "focus_character": self.focus_character,
            "visible_characters": list(self.visible_characters),
            "shared_action": self.shared_action,
            "characters": self.characters,
            "time_phase": self.time_phase,
            "visual_en": self.visual_en,
            "tags_en": list(self.tags_en),
            "prompt_package": dict(self.prompt_package),
            "focus_reason": self.focus_reason,
            "multi_character_reason": self.multi_character_reason,
            "camera_director": dict(self.camera_director),
            "concrete_action": self.concrete_action,
            "place": self.place,
            "canonical_outfit": dict(self.canonical_outfit),
            "pose": self.pose,
            "shot_type": self.shot_type,
            "camera_side": self.camera_side,
            "camera_angle": self.camera_angle,
            "lighting": self.lighting,
            "positive_prompt": self.positive_prompt,
            "negative_prompt": self.negative_prompt,
            "visual_reason": self.visual_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualContract":
        validate_visual_contract_shape(data)
        return cls(
            turn=data["turn"],
            location_id=data["location_id"],
            moment=data["moment"],
            focus_character=data["focus_character"],
            visible_characters=list(data["visible_characters"]),
            shared_action=bool(data["shared_action"]),
            characters=list(data["characters"]),
            time_phase=data["time_phase"],
            visual_en=data["visual_en"],
            tags_en=list(data.get("tags_en", [])),
            prompt_package=dict(data.get("prompt_package", {})),
            focus_reason=str(data.get("focus_reason", "")),
            multi_character_reason=str(data.get("multi_character_reason", "")),
            camera_director=dict(data.get("camera_director", {})),
            concrete_action=str(data.get("concrete_action", data.get("moment", ""))),
            place=str(data.get("place", data.get("location_id", ""))),
            canonical_outfit=dict(data.get("canonical_outfit", {})),
            pose=str(data.get("pose", "unspecified")),
            shot_type=str(data.get("shot_type", data.get("camera_director", {}).get("shot_type", ""))),
            camera_side=str(data.get("camera_side", data.get("camera_director", {}).get("camera_side", ""))),
            camera_angle=str(data.get("camera_angle", data.get("camera_director", {}).get("camera_angle", ""))),
            lighting=str(data.get("lighting", "worldpack_default")),
            positive_prompt=str(data.get("positive_prompt", data.get("prompt_package", {}).get("positive", ""))),
            negative_prompt=str(data.get("negative_prompt", data.get("prompt_package", {}).get("negative", ""))),
            visual_reason=str(data.get("visual_reason", data.get("focus_reason", ""))),
        )


def _authoritative_character(state: WorldState, character_id: str) -> dict[str, Any]:
    if character_id == "player":
        return {
            "id": "player",
            "outfit_worn": list(state.player.outfit.worn),
            "outfit_removed": list(state.player.outfit.removed),
            "outfit_revision": state.player.outfit.revision,
            "outfit_state": outfit_state(state.player.outfit),
            "wounds": list(state.player.wounds),
            "conditions": list(state.player.conditions),
        }
    npc = state.npcs[character_id]
    return {
        "id": character_id,
        "name": npc.name,
        "outfit_worn": list(npc.outfit.worn),
        "outfit_removed": list(npc.outfit.removed),
        "outfit_revision": npc.outfit.revision,
        "outfit_state": outfit_state(npc.outfit),
        "wounds": list(npc.wounds),
        "conditions": list(npc.conditions),
    }


def _dedupe_chunks(text: str) -> str:
    """Rimuove i chunk duplicati da un prompt separato da virgole.

    SD/Pony non guadagna nulla dai tag ripetuti: diluiscono l'attenzione
    e sprecano token CLIP. Il confronto è normalizzato (lowercase, spazi
    compattati); la prima occorrenza vince e l'ordine resta invariato.
    I tag LoRA (<lora:nome:peso>) non contengono virgole, quindi passano
    indenni; la prosa di scena viene solo ri-giuntata com'era.
    """

    seen: set[str] = set()
    kept: list[str] = []
    for chunk in text.split(","):
        norm = " ".join(chunk.lower().split())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        kept.append(chunk.strip())
    return ", ".join(kept)


def _compact_sheet(base_prompt: str, max_chunks: int, identity_chunks: int = 8) -> str:
    """Versione corta di una sheet: trigger + LoRA + tratti identitari.

    Convenzione delle sheet di pack: prima del tag <lora:...> ci sono
    qualita' e trigger word, DOPO ci sono i tratti identitari del
    personaggio (es. "giant cyclops woman, single large bloodshot eye").
    In modalita' compatta si tengono: i primi max_chunks chunk pre-LoRA,
    tutti i tag LoRA, e i primi identity_chunks chunk post-LoRA — cosi'
    l'identita' non si perde mai, solo il padding estetico viene tagliato.
    """

    head: list[str] = []
    tail: list[str] = []
    loras: list[str] = []
    seen_lora = False
    for chunk in base_prompt.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.lower().startswith("<lora:"):
            loras.append(chunk)
            seen_lora = True
        elif seen_lora:
            tail.append(chunk)
        else:
            head.append(chunk)
    kept = head[:max_chunks] + loras + tail[:identity_chunks]
    return ", ".join(kept)


def _dedupe_layer(text: str) -> str:
    return _dedupe_chunks(text)


def _join_nonempty(parts: list[str]) -> str:
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _identity_layer_policy_enabled(pack: WorldPack) -> bool:
    return bool(getattr(pack.visual_policy, "sanitize_identity_layers", False))


def _avoid_facial_policy_enabled(pack: WorldPack) -> bool:
    return bool(getattr(pack.visual_policy, "avoid_facial_expressions", False))

_ROLE_PROMPT_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:survivor|navigator|adventurer|strategist|legendary|experienced)\b",
        r"\bancient\s+hero\b",
        r"\b(?:daughter|son)\s+of\b[^,.;]*",
        r"\bruler\s+of\b[^,.;]*",
        r"\b(?:king|queen)\s+of\b[^,.;]*",
        r"\b(?:lived|survived)\s+through\b[^,.;]*",
        r"\bwise\s+and\s+experienced\b",
        r"\bnoble\s+lineage\b",
    )
)


def _concise_role_policy_enabled(pack: WorldPack) -> bool:
    return bool(getattr(pack.visual_policy, "concise_role_prompts", False))


def _normalize_role_prompt_for_pack(text: str, pack: WorldPack) -> tuple[str, list[str]]:
    if not _concise_role_policy_enabled(pack):
        return text, []
    cleaned, removed = _sanitize_identity_text(text)
    if _avoid_facial_policy_enabled(pack):
        cleaned, facial_removed = _sanitize_facial_text(cleaned)
        removed.extend(facial_removed)
    kept_clauses: list[str] = []
    for raw_clause in cleaned.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        if any(pattern.search(clause) for pattern in _ROLE_PROMPT_FORBIDDEN_PATTERNS):
            removed.append(clause)
            continue
        kept_clauses.append(clause)
    normalized = ", ".join(kept_clauses)
    max_words = max(1, int(getattr(pack.visual_policy, "max_role_prompt_words", 12)))
    words = normalized.split()
    if len(words) > max_words:
        removed.append(" ".join(words[max_words:]))
        normalized = " ".join(words[:max_words]).strip(" ,")
    return normalized, removed


_LAYER_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "her",
    "his",
    "in",
    "near",
    "of",
    "on",
    "the",
    "to",
    "with",
}

_OUTFIT_LAYER_WORDS = {
    "aegis",
    "armor",
    "arm",
    "barefoot",
    "belt",
    "bow",
    "bracelets",
    "braziers",
    "chiton",
    "cloak",
    "club",
    "corselet",
    "cups",
    "greaves",
    "helmet",
    "himation",
    "jewelry",
    "leather",
    "loom",
    "pelt",
    "pelts",
    "peplos",
    "quiver",
    "rings",
    "robe",
    "sandals",
    "spear",
    "staff",
    "straps",
    "threads",
    "thighs",
}

_REVEALING_OUTFIT_WORDS = {
    "bare",
    "clinging",
    "coverage",
    "cut",
    "deep",
    "exposed",
    "fit",
    "low",
    "low-cut",
    "minimal",
    "revealing",
    "short",
    "shoulders",
    "skimpy",
    "thighs",
    "tight",
}

_POSE_OR_SCENE_WORDS = {
    "action",
    "angle",
    "background",
    "body",
    "camera",
    "cinematic",
    "cliffs",
    "composition",
    "crossed",
    "distant",
    "full",
    "hands",
    "knees",
    "against",
    "beside",
    "leg",
    "legs",
    "light",
    "looking",
    "pose",
    "resting",
    "rock",
    "seated",
    "shoreline",
    "side",
    "three",
    "view",
    "volcanic",
}

_CLOTHING_OUTFIT_WORDS = {
    "aegis",
    "armor",
    "bracelets",
    "chiton",
    "cloak",
    "corselet",
    "greaves",
    "helmet",
    "himation",
    "jewelry",
    "leather",
    "pelts",
    "peplos",
    "sandals",
}

_TORSO_CLOTHING_WORDS = {
    "armor",
    "breastplate",
    "chest wrap",
    "chiton",
    "cloak",
    "corselet",
    "dress",
    "himation",
    "leather armor",
    "peplos",
    "pelt",
    "pelts",
    "robe",
    "shirt",
    "top",
    "tunic",
    "wrap",
}

_LOWER_CLOTHING_WORDS = {
    "chiton",
    "dress",
    "himation",
    "kilt",
    "loincloth",
    "pants",
    "peplos",
    "pelt",
    "pelts",
    "robe",
    "shorts",
    "skirt",
    "tunic",
}

_FOOTWEAR_WORDS = {
    "boots",
    "greaves",
    "sandals",
    "shoes",
}

_FULL_NUDE_TAGS = [
    "completely nude",
    "fully naked",
    "no clothing",
    "no armor",
    "no dress",
    "no chiton",
]

_FULL_NUDE_NEGATIVE_TAGS = [
    "bikini",
    "swimsuit",
    "underwear",
    "lingerie",
    "bra",
    "panties",
    "dress",
    "skirt",
    "armor",
    "chiton",
    "clothing",
]

_TOPLESS_TAGS = [
    "topless",
    "bare chest",
    "no top",
    "no bra",
    "no armor",
]

_BOTTOMLESS_TAGS = [
    "bottomless",
    "no lower clothing",
    "no skirt",
    "no panties",
]

_WEAK_FULL_NUDE_SUBSTITUTES = {
    "bare thighs clearly visible",
    "bare thighs visible",
    "exposed shoulders",
    "bare-skinned",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _LAYER_STOPWORDS and len(token) > 2
    }


def _dedupe_scene_tags_for_pack(
    tags: list[str],
    outfit_blocks: list[str],
    visual_en: str,
    pack: WorldPack,
) -> tuple[list[str], list[str]]:
    if not getattr(pack.visual_policy, "dedupe_across_layers", False):
        return tags, []
    outfit_tokens = _tokens(" ".join(outfit_blocks))
    visual_tokens = _tokens(visual_en)
    max_tags = int(getattr(pack.visual_policy, "max_scene_tags", 0) or 0)
    kept: list[str] = []
    counted_scene_tags = 0
    removed: list[str] = []
    director_tags = {
        "full body",
        "medium",
        "close up",
        "low camera",
        "eye-level camera",
        "high camera",
        "rear three quarter view",
        "rear view",
        "side view",
        "front three quarter view",
        "front view",
        "facing away",
        "facing camera three quarter",
        "side orientation",
        "cavern entrance ahead",
    }
    for idx, tag in enumerate(tags):
        tag_tokens = _tokens(tag)
        if not tag_tokens:
            continue
        if tag in director_tags:
            kept.append(tag)
            continue
        if tag_tokens & _OUTFIT_LAYER_WORDS and (tag_tokens & outfit_tokens):
            removed.append(tag)
            continue
        if tag_tokens and tag_tokens <= visual_tokens:
            removed.append(tag)
            continue
        if len(tag_tokens & visual_tokens) >= max(2, len(tag_tokens) - 1):
            removed.append(tag)
            continue
        kept.append(tag)
        counted_scene_tags += 1
        if max_tags and counted_scene_tags >= max_tags:
            removed.extend(tags[idx + 1 :])
            break
    return kept, removed


def _revealing_outfit_policy_enabled(pack: WorldPack) -> bool:
    return bool(getattr(pack.visual_policy, "preserve_revealing_outfit_traits", False))


def _is_revealing_outfit_item(item: str) -> bool:
    return bool(_tokens(item) & _REVEALING_OUTFIT_WORDS)


def _compact_outfit_for_pack(
    outfit_items: list[str],
    outfit_chunks: int,
    pack: WorldPack,
) -> list[str]:
    if not getattr(pack.visual_policy, "revealing_outfit_priority", False):
        return outfit_items[:outfit_chunks]
    revealing = [item for item in outfit_items if _is_revealing_outfit_item(item)]
    other = [item for item in outfit_items if item not in revealing]
    if not revealing:
        return outfit_items[:outfit_chunks]
    kept = list(dict.fromkeys(revealing))
    for item in other:
        if len(kept) >= outfit_chunks and outfit_chunks > 0:
            break
        kept.append(item)
    return kept


def _dedupe_visual_against_outfit_for_pack(
    visual_en: str,
    outfit_blocks: list[str],
    pack: WorldPack,
) -> tuple[str, list[str]]:
    if not getattr(pack.visual_policy, "dedupe_across_layers", False):
        return visual_en, []
    outfit_tokens = _tokens(" ".join(outfit_blocks))
    removed: list[str] = []
    kept: list[str] = []
    for raw_clause in visual_en.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        clause_tokens = _tokens(clause)
        outfit_overlap = clause_tokens & outfit_tokens & _OUTFIT_LAYER_WORDS
        scene_overlap = clause_tokens & _POSE_OR_SCENE_WORDS
        if outfit_overlap and re.search(r"\b(?:wears?|wearing|dressed in)\b", clause, re.IGNORECASE):
            removed.append(clause)
            continue
        if outfit_overlap & _CLOTHING_OUTFIT_WORDS and not scene_overlap:
            removed.append(clause)
            continue
        if outfit_overlap and len(outfit_overlap) >= 2 and not scene_overlap:
            removed.append(clause)
            continue
        kept.append(clause)
    return ", ".join(kept), removed


def _contains_any(text: str, terms: set[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _has_torso_clothing(items: list[str]) -> bool:
    return any(_contains_any(item, _TORSO_CLOTHING_WORDS) for item in items)


def _has_lower_clothing(items: list[str]) -> bool:
    return any(_contains_any(item, _LOWER_CLOTHING_WORDS) for item in items)


def _has_footwear(items: list[str]) -> bool:
    return any(_contains_any(item, _FOOTWEAR_WORDS) for item in items)


def _barefoot_coherent(worn: list[str], removed: list[str]) -> bool:
    text = " ".join(worn + removed).lower()
    return "barefoot" in text or "bare feet" in text or not _has_footwear(worn)


def _scene_implies_full_nudity(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:completely|fully|entirely|totally)\s+(?:nude|naked)\b"
            r"|\bno\s+(?:clothes|clothing|garments|outfit|armor|dress|chiton)\b"
            r"|\bwithout\s+(?:clothes|clothing|garments|outfit|armor|dress|chiton)\b"
            r"|\b(?:nuda|nudo|nudita|nudità)\s+(?:completa|totale)\b"
            r"|\bcompletamente\s+nuda\b"
            r"|\bbare[- ]skinned\b",
            text,
            re.IGNORECASE,
        )
    )


def _scene_implies_topless(text: str) -> bool:
    return bool(
        re.search(
            r"\btopless\b|\bbare\s+(?:chest|breasts?)\b|\bno\s+(?:top|bra)\b"
            r"|\bwithout\s+(?:top|bra|torso clothing)\b",
            text,
            re.IGNORECASE,
        )
    )


def _scene_implies_bottomless(text: str) -> bool:
    return bool(
        re.search(
            r"\bbottomless\b|\bno\s+(?:lower clothing|skirt|panties|underwear)\b"
            r"|\bwithout\s+(?:lower clothing|skirt|panties|underwear)\b",
            text,
            re.IGNORECASE,
        )
    )


def _classify_player_nudity(
    visible_characters: list[str],
    characters: list[dict[str, Any]],
    visual_en: str,
    tags_en: list[str],
) -> dict[str, Any]:
    player = next((c for c in characters if c.get("id") == "player"), None)
    if "player" not in visible_characters or player is None:
        return {
            "detected_clothing_state": "not_visible",
            "nudity_mode": "none",
            "nudity_tags_added": [],
            "clothing_block_tags_added": [],
        }

    worn = [str(item) for item in player.get("outfit_worn", [])]
    removed = [str(item) for item in player.get("outfit_removed", [])]
    if isinstance(player.get("outfit_state"), dict):
        canonical = dict(player["outfit_state"])
    else:
        canonical = outfit_state(
            type(
                "_OutfitView",
                (),
                {"worn": worn, "removed": removed, "revision": player.get("outfit_revision", 0)},
            )()
        )
    text = " ".join([visual_en, *tags_en])
    has_torso = bool(canonical["torso_slot"])
    has_lower = bool(canonical["lower_body_slot"])
    revealing = any(_is_revealing_outfit_item(item) for item in worn)
    if has_torso and has_lower:
        clothing_state = "torso_and_lower_clothed"
    elif has_torso:
        clothing_state = "torso_clothed_lower_unclothed"
    elif has_lower:
        clothing_state = "torso_unclothed_lower_clothed"
    else:
        clothing_state = "no_torso_or_lower_clothing"

    mode = "none"
    state_authoritative = isinstance(player.get("outfit_state"), dict)
    if not has_torso and not has_lower and (state_authoritative or removed or _scene_implies_full_nudity(text)):
        mode = "fully_nude"
    elif not has_torso and (state_authoritative or removed or _scene_implies_topless(text)):
        mode = "topless"
    elif not has_lower and (state_authoritative or removed or _scene_implies_bottomless(text)):
        mode = "bottomless"
    elif revealing:
        mode = "revealing"

    positive_tags: list[str] = []
    negative_tags: list[str] = []
    if mode == "fully_nude":
        positive_tags = list(_FULL_NUDE_TAGS)
        if _barefoot_coherent(worn, removed):
            positive_tags.append("barefoot")
        negative_tags = list(_FULL_NUDE_NEGATIVE_TAGS)
    elif mode == "topless":
        positive_tags = list(_TOPLESS_TAGS)
    elif mode == "bottomless":
        positive_tags = list(_BOTTOMLESS_TAGS)

    return {
        "detected_clothing_state": clothing_state,
        "nudity_mode": mode,
        "nudity_tags_added": positive_tags,
        "clothing_block_tags_added": negative_tags,
        "canonical_outfit_state": canonical,
    }


def _remove_weak_full_nude_substitutes(items: list[str]) -> list[str]:
    return [
        item
        for item in items
        if item.strip().lower() not in _WEAK_FULL_NUDE_SUBSTITUTES
    ]


def _explicit_nudity_visual_en(visual_en: str, mode: str) -> str:
    if mode != "fully_nude" or re.search(
        r"\bcompletely nude\b|\bfully naked\b|\bno clothing\b",
        visual_en,
        re.IGNORECASE,
    ):
        return visual_en
    cleaned = re.sub(r"\bbare[- ]skinned\b", "", visual_en, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    if re.match(r"^Ulisse\s+stands\b", cleaned, re.IGNORECASE):
        return re.sub(
            r"^Ulisse\s+stands\b",
            "Ulisse stands completely nude, fully naked, with no clothing, no armor, no dress, no chiton,",
            cleaned,
            flags=re.IGNORECASE,
        )
    if cleaned:
        return (
            "Ulisse stands completely nude, fully naked, with no clothing, "
            "no armor, no dress, no chiton, "
            + cleaned
        )
    return "Ulisse stands completely nude, fully naked, with no clothing, no armor, no dress, no chiton"


def _sanitize_outfit_item(item: str) -> bool:
    _, removed = _sanitize_identity_text(item)
    return bool(removed)


def _normalize_visual_outfits_for_pack(state: WorldState, pack: WorldPack) -> None:
    if not _identity_layer_policy_enabled(pack):
        return
    state.player.outfit.worn = [
        item for item in state.player.outfit.worn if not _sanitize_outfit_item(item)
    ]
    for npc in state.npcs.values():
        npc.outfit.worn = [
            item for item in npc.outfit.worn if not _sanitize_outfit_item(item)
        ]


def _single_character_negative() -> str:
    return (
        "multiple people, extra person, background people, duplicate character, "
        "cloned face, merged bodies, fused bodies, extra face"
    )


def _multi_character_negative() -> str:
    return (
        "merged bodies, fused faces, same face, identical faces, twins, "
        "cloned face, duplicate character, same hair, same hairstyle, "
        "swapped outfits, costume leak, incorrect anatomy, extra person, "
        "background people"
    )


# ---------------------------------------------------------------------------
# Composizione multi-personaggio (raggruppata per soggetto)
# ---------------------------------------------------------------------------

# Cap dei pesi dei LoRA identita' in scene con 2+ LoRA di personaggio:
# i LoRA si applicano a tutta l'immagine e due identita' a peso pieno si
# fondono (tratti di un volto nell'altro). Mai applicato al suffisso di pack.
MULTI_LORA_WEIGHT_CAP = float(os.environ.get("EPOS_MULTI_LORA_CAP", "0.45"))

_LORA_TAG_PATTERN = re.compile(r"<lora:([^:>]+):([0-9]*\.?[0-9]+)>")


def _downscale_lora_blocks(text: str, cap: float) -> str:
    def _sub(match: re.Match[str]) -> str:
        weight = float(match.group(2))
        return f"<lora:{match.group(1)}:{min(weight, cap):g}>"

    return _LORA_TAG_PATTERN.sub(_sub, text)


def _character_gender(base_prompt: str) -> str | None:
    match = re.search(r"\b(1girl|1boy|1man|1woman)\b", base_prompt, re.IGNORECASE)
    if not match:
        return None
    return "girl" if match.group(1).lower() in ("1girl", "1woman") else "boy"


def _count_anchor_tag(
    visible_characters: list[str], base_prompt_by_character: dict[str, str]
) -> str:
    """Tag di conteggio in testa al prompt: l'ancora piu' forte che Pony/SDXL
    ha per il multi-soggetto (2girls / 2boys / 1girl and 1boy)."""

    girls = sum(
        1
        for c in visible_characters
        if _character_gender(base_prompt_by_character.get(c, "")) == "girl"
    )
    boys = sum(
        1
        for c in visible_characters
        if _character_gender(base_prompt_by_character.get(c, "")) == "boy"
    )
    total = len(visible_characters)
    if girls + boys != total:
        return f"{total}people"
    if girls == 1 and boys == 1:
        return "1girl and 1boy"
    parts: list[str] = []
    if girls:
        parts.append(f"{girls}girl{'s' if girls > 1 else ''}")
    if boys:
        parts.append(f"{boys}boy{'s' if boys > 1 else ''}")
    if len(parts) == 1:
        return parts[0]
    return f"{total}people, " + ", ".join(parts)


def _position_tags(count: int) -> list[str]:
    if count == 2:
        return ["on the left", "on the right"]
    if count == 3:
        return ["on the left", "in the center", "on the right"]
    if count == 4:
        return ["on the far left", "on the left", "on the right", "on the far right"]
    return [f"position {index + 1}" for index in range(count)]


def _dedupe_base_chunks(text: str, seen: set[str]) -> str:
    """Dedup dei chunk ripetuti tra due base prompt (score_9, masterpiece...).

    Solo duplicati esatti: il testo del base prompt resta verbatim; i tag
    LoRA passano sempre. La prima occorrenza vince, l'ordine e' invariato.
    """

    kept: list[str] = []
    for chunk in text.split(","):
        norm = " ".join(chunk.lower().split())
        if not norm:
            continue
        if norm.startswith("<lora:") or norm not in seen:
            kept.append(chunk.strip())
        seen.add(norm)
    return ", ".join(kept)


def _compose_multi_character_positive(
    visible_characters: list[str],
    base_prompt_by_character: dict[str, str],
    character_lora_by_character: dict[str, str],
    outfit_prompt_by_character: dict[str, str],
    role_prompt_by_character: dict[str, str],
    scene_tag_blocks: list[str],
    scene_visual_blocks: list[str],
    global_suffix_blocks: list[str],
    diagnostics: dict[str, Any],
) -> str:
    """Prompt multi-personaggio raggruppato per soggetto.

    Convenzione Pony/SDXL per il multi-soggetto: tag di conteggio in testa,
    poi un gruppo per personaggio — base prompt, LoRA, outfit autorevole,
    role prompt, posizione — cosi' attributi e abiti restano legati al
    soggetto giusto invece di finire in pool condivisi (causa di volti
    fusi, gemelli e outfit scambiati).
    """

    anchor = _count_anchor_tag(visible_characters, base_prompt_by_character)
    positions = _position_tags(len(visible_characters))
    lora_count = sum(1 for c in visible_characters if character_lora_by_character.get(c))
    cap = MULTI_LORA_WEIGHT_CAP if lora_count >= 2 else None

    seen: set[str] = set()
    groups: list[str] = []
    for index, character_id in enumerate(visible_characters):
        base = _dedupe_base_chunks(
            base_prompt_by_character.get(character_id, ""), seen
        )
        lora = character_lora_by_character.get(character_id, "")
        if lora and cap is not None:
            lora = _downscale_lora_blocks(lora, cap)
        groups.append(
            _join_nonempty(
                [
                    base,
                    lora,
                    outfit_prompt_by_character.get(character_id, ""),
                    role_prompt_by_character.get(character_id, ""),
                    positions[index],
                ]
            )
        )

    diagnostics.update(
        {
            "grouped_per_character": True,
            "count_anchor": anchor,
            "positions": dict(zip(visible_characters, positions)),
            "character_lora_weight_cap": cap,
        }
    )
    return _join_nonempty(
        [
            anchor,
            *groups,
            _dedupe_layer(_join_nonempty(scene_tag_blocks)),
            _join_nonempty(scene_visual_blocks),
            _dedupe_layer(_join_nonempty(global_suffix_blocks)),
        ]
    )


def compile_prompt_package(
    pack: WorldPack,
    visible_characters: list[str],
    characters: list[dict[str, Any]],
    visual_en: str,
    tags_en: list[str],
    visual_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assembla il prompt positivo. Nessuno strato creativo aggiuntivo.

    `visual_overrides` copre le sheet di sessione (es. personaggio creato
    interattivamente): hanno precedenza sul pack, stessa immutabilità.

    Ordine del prompt (convenzione Pony/SDXL):
    qualità+soggetto (base prompt) → stile → outfit autorevole → tag di
    scena → prosa di scena (visual_en) → suffisso globale (LoRA di pack).
    I chunk duplicati vengono eliminati: sheet di stile e outfit canonico
    si sovrappongono spesso, e le ripetizioni diluiscono il prompt.

    EPOS_PROMPT_MODE=compact accorcia sheet e outfit (env
    EPOS_PROMPT_BASE_CHUNKS / EPOS_PROMPT_OUTFIT_CHUNKS) per non affogare
    i tag di scena: consigliata con Pony e scene multi-personaggio.
    """

    compact = os.environ.get("EPOS_PROMPT_MODE", "full").lower() == "compact"
    base_chunks = int(os.environ.get("EPOS_PROMPT_BASE_CHUNKS", "10"))
    identity_chunks = int(os.environ.get("EPOS_PROMPT_IDENTITY_CHUNKS", "8"))
    outfit_chunks = int(os.environ.get("EPOS_PROMPT_OUTFIT_CHUNKS", "3"))

    overrides = visual_overrides or {}
    protected = pack.visual_policy.protected_base_prompts
    base_prompt_by_character: dict[str, str] = {}
    character_lora_by_character: dict[str, str] = {}
    outfit_prompt_by_character: dict[str, str] = {}
    role_prompt_by_character: dict[str, str] = {}
    role_prompt_original_by_character: dict[str, str] = {}
    role_prompt_removed_by_character: dict[str, list[str]] = {}
    negative_prompt_by_character: dict[str, str] = {}
    protected_base_blocks: list[str] = []
    character_lora_blocks: list[str] = []
    outfit_blocks: list[str] = []
    role_blocks: list[str] = []
    scene_tag_blocks: list[str] = []
    scene_visual_blocks: list[str] = []
    global_suffix_blocks: list[str] = []
    original_tags_en = list(tags_en)
    original_visual_en = visual_en
    removed_identity_terms: list[str] = []
    removed_facial_terms: list[str] = []
    removed_broken_generated_chunks: list[str] = []
    camera_tag_conflicts: list[dict[str, Any]] = []
    removed_layer_duplicates: dict[str, list[str]] = {"tags": [], "visual": []}
    outfit_tags_suppressed: dict[str, list[str]] = {}
    if _identity_layer_policy_enabled(pack):
        tags_en, removed_tag_terms = _sanitize_identity_tags(tags_en)
        visual_en, removed_visual_terms = _sanitize_identity_text(visual_en)
        removed_identity_terms = removed_tag_terms + removed_visual_terms
    if _avoid_facial_policy_enabled(pack):
        tags_en, removed_tag_facial_terms = _sanitize_facial_tags(tags_en)
        visual_en, removed_visual_facial_terms = _sanitize_facial_text(visual_en)
        removed_facial_terms = removed_tag_facial_terms + removed_visual_facial_terms
    if protected:
        tags_en, removed_tag_broken_chunks = _sanitize_broken_generated_tags(tags_en)
        visual_en, removed_visual_broken_chunks = _sanitize_broken_generated_text(visual_en)
        removed_broken_generated_chunks = (
            removed_tag_broken_chunks + removed_visual_broken_chunks
        )
    visual_en, tags_en, camera_tag_conflicts = _resolve_camera_conflicts(visual_en, tags_en)
    nudity_diagnostics = _classify_player_nudity(
        visible_characters, characters, visual_en, tags_en
    )
    visual_en = _explicit_nudity_visual_en(
        visual_en, nudity_diagnostics["nudity_mode"]
    )
    tags_en = list(tags_en) + list(nudity_diagnostics["nudity_tags_added"])

    for character_id in visible_characters:
        if character_id in overrides:
            base_prompt_by_character[character_id] = overrides[character_id]
            if protected:
                protected_base_blocks.append(overrides[character_id])
            else:
                protected_base_blocks.append(overrides[character_id])
        else:
            sheet = pack.visual_sheets.get(character_id)
            if sheet is not None:
                base_prompt_by_character[character_id] = sheet.base_prompt
                character_lora_by_character[character_id] = sheet.character_lora_en
                negative_prompt_by_character[character_id] = sheet.negative_prompt
                if protected:
                    protected_base_blocks.append(sheet.base_prompt)
                    if sheet.character_lora_en:
                        character_lora_blocks.append(sheet.character_lora_en)
                    if sheet.role_prompt_en:
                        role_prompt_original_by_character[character_id] = sheet.role_prompt_en
                        role_prompt, removed_role_terms = _normalize_role_prompt_for_pack(
                            sheet.role_prompt_en, pack
                        )
                        if removed_role_terms:
                            role_prompt_removed_by_character[character_id] = removed_role_terms
                        if role_prompt:
                            role_prompt_by_character[character_id] = role_prompt
                            role_blocks.append(role_prompt)
                elif compact:
                    protected_base_blocks.append(
                        _compact_sheet(sheet.base_prompt, base_chunks, identity_chunks)
                    )
                    if sheet.character_lora_en:
                        character_lora_blocks.append(sheet.character_lora_en)
                    # in compatta lo style_en (padding estetico) si salta:
                    # l'outfit autorevole copre gia' l'abbigliamento
                else:
                    protected_base_blocks.append(sheet.base_prompt)  # copia esatta, mai alterata
                    if sheet.character_lora_en:
                        character_lora_blocks.append(sheet.character_lora_en)
                    # regola di stile: prima quella del personaggio, poi il pack
                    style = sheet.style_en or pack.visual_style_en
                    if style:
                        outfit_blocks.append(style)
                    if sheet.role_prompt_en:
                        role_prompt_original_by_character[character_id] = sheet.role_prompt_en
                        role_prompt, removed_role_terms = _normalize_role_prompt_for_pack(
                            sheet.role_prompt_en, pack
                        )
                        if removed_role_terms:
                            role_prompt_removed_by_character[character_id] = removed_role_terms
                        if role_prompt:
                            role_prompt_by_character[character_id] = role_prompt
                            role_blocks.append(role_prompt)
    for character in characters:
        if character["outfit_worn"]:
            worn = character["outfit_worn"]
            if (
                character["id"] == "player"
                and nudity_diagnostics["nudity_mode"] == "fully_nude"
            ):
                outfit_tags_suppressed[character["id"]] = list(worn)
                worn = []
            if compact:
                worn = _compact_outfit_for_pack(worn, outfit_chunks, pack)
            outfit = ", ".join(worn)
            if outfit:
                outfit_prompt_by_character[character["id"]] = outfit
                outfit_blocks.append(outfit)
    if getattr(pack.visual_policy, "visual_en_primary", False):
        visual_en, removed_visual_duplicates = _dedupe_visual_against_outfit_for_pack(
            visual_en, outfit_blocks, pack
        )
        removed_layer_duplicates["visual"] = removed_visual_duplicates
    if getattr(pack.visual_policy, "dedupe_across_layers", False):
        tags_en, removed_tag_duplicates = _dedupe_scene_tags_for_pack(
            tags_en, outfit_blocks, visual_en, pack
        )
        removed_layer_duplicates["tags"] = removed_tag_duplicates
    # tag di scena (corti, ad alto segnale) prima della prosa
    if tags_en:
        scene_tag_blocks.append(", ".join(tags_en))
    # La prosa di scena (visual_en) e opzionale: Pony pensa per tag booru,
    # non per frasi. EPOS_PROMPT_PROSE=0 la esclude dal prompt (resta nel
    # contratto visivo e nel file di debug del turno). I pack con base
    # protetti, come Odissea, mantengono sempre la prosa visuale: e' il layer
    # prioritario che descrive posa, azione e camera del frame.
    prose_enabled = os.environ.get("EPOS_PROMPT_PROSE", "1") not in ("0", "false", "no")
    if visual_en and (prose_enabled or protected):
        scene_visual_blocks.append(visual_en)
    # suffisso globale di pack (es. LoRA canonici globali): una sola volta,
    # in coda, indipendentemente da quanti personaggi sono visibili
    if pack.visual_prompt_suffix_en:
        global_suffix_blocks.append(pack.visual_prompt_suffix_en)

    multi_character_diagnostics: dict[str, Any] = {"grouped_per_character": False}
    if len(visible_characters) > 1:
        # Scena multi-personaggio: prompt raggruppato per soggetto (tag di
        # conteggio + un gruppo per personaggio con outfit e posizione),
        # invece dei pool condivisi che causano volti fusi e outfit scambiati.
        positive = _compose_multi_character_positive(
            visible_characters,
            base_prompt_by_character,
            character_lora_by_character,
            outfit_prompt_by_character,
            role_prompt_by_character,
            scene_tag_blocks,
            scene_visual_blocks,
            global_suffix_blocks,
            multi_character_diagnostics,
        )
    else:
        non_protected_layers = [
            _dedupe_layer(_join_nonempty(character_lora_blocks)),
            _dedupe_layer(_join_nonempty(outfit_blocks)),
            _dedupe_layer(_join_nonempty(role_blocks)),
            _dedupe_layer(_join_nonempty(scene_tag_blocks)),
            _join_nonempty(scene_visual_blocks),
            _dedupe_layer(_join_nonempty(global_suffix_blocks)),
        ]

        if protected:
            positive = _join_nonempty(
                protected_base_blocks + [p for p in non_protected_layers if p]
            )
        else:
            positive = _dedupe_chunks(
                _join_nonempty(protected_base_blocks + [p for p in non_protected_layers if p])
            )

    negative = DEFAULT_NEGATIVE
    if pack.visual_policy.include_sheet_negative:
        sheet_negative = _join_nonempty(
            [negative_prompt_by_character.get(c, "") for c in visible_characters]
        )
        if sheet_negative:
            negative = f"{negative}, {sheet_negative}"
    if pack.visual_negative_extra_en:
        negative = f"{negative}, {pack.visual_negative_extra_en}"
    if nudity_diagnostics["clothing_block_tags_added"]:
        negative = f"{negative}, {', '.join(nudity_diagnostics['clothing_block_tags_added'])}"
    if pack.visual_policy.include_sheet_negative:
        negative = (
            f"{negative}, "
            f"{_multi_character_negative() if len(visible_characters) > 1 else _single_character_negative()}"
        )
    negative_final = _dedupe_chunks(negative)
    return {
        "positive": positive,
        "negative": negative_final,
        "base_prompt_by_character": base_prompt_by_character,
        "character_lora_by_character": character_lora_by_character,
        "outfit_prompt_by_character": outfit_prompt_by_character,
        "role_prompt_by_character": role_prompt_by_character,
        "role_prompt_original_by_character": role_prompt_original_by_character,
        "role_prompt_sanitization": {
            "removed_terms_by_character": role_prompt_removed_by_character,
            "max_words": getattr(pack.visual_policy, "max_role_prompt_words", 12),
        },
        "scene_tags": list(tags_en),
        "scene_visual": visual_en,
        "original_scene_tags": original_tags_en,
        "original_scene_visual": original_visual_en,
        "sanitized_scene_tags": list(tags_en),
        "sanitized_scene_visual": visual_en,
        "identity_sanitization": {
            "removed_terms": removed_identity_terms,
            "reason": (
                "physical identity traits outside protected base_prompt are not authoritative"
                if removed_identity_terms
                else ""
            ),
        },
        "facial_expression_sanitization": {
            "removed_terms": removed_facial_terms,
            "reason": (
                "facial expressions are not allowed outside protected base_prompt"
                if removed_facial_terms
                else ""
            ),
        },
        "broken_chunk_sanitization": {
            "removed_chunks": removed_broken_generated_chunks,
            "reason": (
                "incomplete generated visual chunks are discarded"
                if removed_broken_generated_chunks
                else ""
            ),
        },
        "camera_tag_conflicts": camera_tag_conflicts,
        "revealing_outfit_policy": {
            "preserve_revealing_outfit_traits": getattr(
                pack.visual_policy, "preserve_revealing_outfit_traits", False
            ),
            "revealing_outfit_priority": getattr(
                pack.visual_policy, "revealing_outfit_priority", False
            ),
        },
        "multi_character_composition": multi_character_diagnostics,
        "cross_layer_deduplication": {
            "removed": removed_layer_duplicates,
            "max_scene_tags": getattr(pack.visual_policy, "max_scene_tags", 0),
        },
        "nudity_diagnostics": nudity_diagnostics,
        "detected_clothing_state": nudity_diagnostics["detected_clothing_state"],
        "nudity_mode": nudity_diagnostics["nudity_mode"],
        "nudity_tags_added": list(nudity_diagnostics["nudity_tags_added"]),
        "clothing_block_tags_added": list(nudity_diagnostics["clothing_block_tags_added"]),
        "outfit_tags_added": list(outfit_blocks),
        "outfit_tags_suppressed": outfit_tags_suppressed,
        "source_of_truth": "character.outfit",
        "negative_prompt_by_character": negative_prompt_by_character,
        "visible_characters": list(visible_characters),
        "positive_prompt": positive,
        "negative_prompt": negative_final,
    }


def _first_present(candidates: list[str], present: set[str]) -> str | None:
    for candidate in candidates:
        if candidate and candidate in present:
            return candidate
    return None


def _focus_for_policy(
    visual: VisualMoment, present: set[str]
) -> tuple[str, str]:
    moment_type = visual.moment_type.strip().lower()
    if moment_type == "speech":
        speaker = _first_present([visual.speaker_character], present)
        if speaker:
            return speaker, "speaker"
    if moment_type == "action":
        actor = _first_present([visual.actor_character], present)
        if actor:
            return actor, "actor"
    if moment_type == "reaction":
        reactor = _first_present([visual.reactor_character], present)
        if reactor:
            return reactor, "reactor"

    explicit = _first_present(
        [
            visual.actor_character,
            visual.speaker_character,
            visual.reactor_character,
            visual.focus_character,
        ],
        present,
    )
    if explicit:
        return explicit, "explicit_visual_focus"
    return "player", "fallback_player"


def _validated_intimate_participants(
    visual: VisualMoment, present: set[str]
) -> tuple[list[str], str]:
    participants = [
        c for c in visual.multi_character_participants if c in present
    ]
    if not participants:
        participants = [c for c in visual.visible_characters if c in present]
    participants = list(dict.fromkeys(participants))
    if (
        visual.intimate_shared_moment
        and visual.moment_type.strip().lower() == "intimate"
        and len(participants) >= 2
    ):
        return participants, visual.multi_character_reason or "intimate_shared_moment"
    return [], "not_validated_intimate_shared_moment"


def _contract_place(state: WorldState, pack: WorldPack) -> str:
    location = pack.locations.get(state.location_id)
    if location is None:
        return state.location_id
    return location.name or location.id


def _contract_outfit(characters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        str(character["id"]): {
            "worn": list(character.get("outfit_worn", [])),
            "removed": list(character.get("outfit_removed", [])),
            "outfit_state": dict(character.get("outfit_state", {})),
            "conditions": list(character.get("conditions", [])),
            "wounds": list(character.get("wounds", [])),
        }
        for character in characters
    }


def _contract_pose(visual: VisualMoment, camera_director: dict[str, Any]) -> str:
    explicit_pose = str(camera_director.get("explicit_pose", "")).strip()
    if explicit_pose:
        return explicit_pose
    text = " ".join([visual.visual_en, *visual.tags_en]).strip()
    return text or "unspecified"


def _contract_lighting(pack: WorldPack, package: dict[str, Any]) -> str:
    tags = [str(tag) for tag in package.get("scene_tags", [])]
    text = " ".join([*tags, str(package.get("scene_visual", "")), str(getattr(pack, "visual_style_en", ""))]).lower()
    for keyword in ("firelight", "moonlight", "sunlight", "torchlight", "candlelight", "backlight", "soft light", "hard light", "dramatic lighting", "realistic lighting"):
        if keyword in text:
            return keyword
    return "worldpack_default"


def _contract_visual_reason(focus_reason: str, multi_character_reason: str, camera_director: dict[str, Any]) -> str:
    parts = [focus_reason]
    if multi_character_reason:
        parts.append(multi_character_reason)
    director_reason = str(camera_director.get("director_reason", "")).strip()
    if director_reason:
        parts.append(director_reason)
    return "; ".join(part for part in parts if part) or "runtime_visual_contract"


def build_visual_contract(
    state: WorldState,
    pack: WorldPack,
    visual: VisualMoment,
    turn: int,
) -> VisualContract:
    """Costruisce il contratto visivo autorevole del turno.

    Solleva ValueError se il momento visivo viola la coerenza: il chiamante
    deve aver già validato la scena, ma questo è il confine ultimo.
    """

    present = set(state.present_character_ids())
    absent = [c for c in visual.visible_characters if c not in present]
    if absent:
        raise ValueError(f"personaggi visibili ma assenti: {', '.join(absent)}")

    visible = list(visual.visible_characters)
    focus = visual.focus_character
    shared_action = visual.shared_action
    focus_reason = "llm_focus"
    multi_character_reason = visual.multi_character_reason

    if pack.visual_policy.speaker_action_focus:
        focus, focus_reason = _focus_for_policy(visual, present)

    if pack.visual_policy.multi_character_mode == "intimate_only":
        intimate_visible, intimate_reason = _validated_intimate_participants(visual, present)
        if intimate_visible:
            visible = intimate_visible
            shared_action = True
            multi_character_reason = intimate_reason
            if focus not in visible:
                focus = visible[0]
                focus_reason = "intimate_participant_fallback"
        else:
            visible = [focus]
            shared_action = False
            multi_character_reason = intimate_reason
    elif not visual.shared_action and len(visible) > 1:
        focus = visual.focus_character if visual.focus_character in visible else visible[0]
        visible = [focus]

    if pack.visual_policy.single_character_default and len(visible) > 1 and not shared_action:
        visible = [focus]

    _normalize_visual_outfits_for_pack(state, pack)
    characters = [_authoritative_character(state, c) for c in visible]
    overrides = state.flags.get("visual_overrides", {})
    directed = direct_visual(pack, state, visual, focus)
    package = compile_prompt_package(
        pack,
        visible,
        characters,
        directed.visual_en,
        directed.tags_en,
        visual_overrides=overrides,
    )
    package["visible_characters"] = list(visible)
    package["focus_character"] = focus
    package["focus_reason"] = focus_reason
    package["multi_character_reason"] = multi_character_reason
    if directed.diagnostics:
        package.update(directed.diagnostics)
    final_visual_en = str(package.get("scene_visual") or directed.visual_en)
    final_tags_en = list(package.get("scene_tags") or directed.tags_en)
    return VisualContract(
        turn=turn,
        location_id=state.location_id,
        moment=visual.summary,
        focus_character=focus,
        visible_characters=visible,
        shared_action=shared_action,
        characters=characters,
        time_phase=state.time_phase,
        visual_en=final_visual_en,
        tags_en=final_tags_en,
        prompt_package=package,
        focus_reason=focus_reason,
        multi_character_reason=multi_character_reason,
        camera_director=directed.diagnostics,
        concrete_action=visual.summary or final_visual_en,
        place=_contract_place(state, pack),
        canonical_outfit=_contract_outfit(characters),
        pose=_contract_pose(visual, directed.diagnostics),
        shot_type=str(directed.diagnostics.get("shot_type", "unspecified")),
        camera_side=str(directed.diagnostics.get("camera_side", "unspecified")),
        camera_angle=str(directed.diagnostics.get("camera_angle", "unspecified")),
        lighting=_contract_lighting(pack, package),
        positive_prompt=str(package.get("positive", "")),
        negative_prompt=str(package.get("negative", "")),
        visual_reason=_contract_visual_reason(
            focus_reason, multi_character_reason, directed.diagnostics
        ),
    )
