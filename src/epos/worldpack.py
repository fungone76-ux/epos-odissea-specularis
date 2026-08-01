"""World-pack: l'ambientazione come contenuto dati, non codice.

Un pack è una cartella YAML:

    worlds/<pack>/
      world.yaml     — locations, fase iniziale, setup del giocatore
      npcs.yaml      — canone stabile degli NPC (personalità, segreti, stile)
      visual.yaml    — character sheet visive (base prompt immutabili)

Il motore non conosce né Passo di Vetro né altri mondi: carica il pack.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import NpcState, Outfit, PlayerState, WorldState
from .schemas import SchemaError, validate_worldpack_mission_shape


class WorldPackError(ValueError):
    """World-pack mancante, invalido o incoerente."""


@dataclass(frozen=True)
class LocationDef:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class NpcCanon:
    """Canone stabile di un NPC: identità, voce, segreti, limiti.

    Non entra tutto nel prompt a ogni turno: il prompt builder seleziona
    ciò che è pertinente. Le preferenze intime entrano solo quando
    relazione, situazione e consenso le rendono pertinenti.
    """

    id: str
    name: str
    age: int
    location_id: str
    present_at_start: bool = False
    personality: list[str] = field(default_factory=list)
    speech_style: str = ""
    desires: list[str] = field(default_factory=list)
    fears: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    knowledge: list[str] = field(default_factory=list)
    skills: dict[str, int] = field(default_factory=dict)  # pool per il confronto
    disclosure_policy: str = ""
    red_lines: list[str] = field(default_factory=list)
    intimate_profile: str = ""  # mai nel prompt di default
    starting_outfit: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VisualSheet:
    """Character sheet visiva: base prompt immutabile per il rendering."""

    character_id: str
    base_prompt: str
    negative_prompt: str = ""
    character_lora_en: str = ""
    role_prompt_en: str = ""
    style_en: str = ""  # regola di stile del guardaroba (override del pack)
    # outfit iniziale canonico lato renderer (inglese): se presente ha
    # precedenza sullo starting_outfit narrativo del world.yaml
    starting_outfit_en: tuple[str, ...] = ()


@dataclass(frozen=True)
class VisualPolicy:
    """Regole opzionali di compilazione visuale abilitate dal world-pack."""

    protected_base_prompts: bool = False
    single_character_default: bool = False
    multi_character_mode: str = "shared_action"
    speaker_action_focus: bool = False
    include_sheet_negative: bool = False
    sanitize_identity_layers: bool = False
    concise_role_prompts: bool = False
    max_role_prompt_words: int = 12
    avoid_facial_expressions: bool = False
    visual_en_primary: bool = False
    dedupe_across_layers: bool = False
    max_scene_tags: int = 0
    role_prompt_optional: bool = False
    preserve_revealing_outfit_traits: bool = False
    revealing_outfit_priority: bool = False
    visual_director_enabled: bool = False
    structured_camera: bool = False
    camera_variety_enabled: bool = False
    camera_history_size: int = 0
    crawling_preferred_views: tuple[str, ...] = ()
    avoid_repeating_camera: bool = False
    # Tag di posa esplicita iniettati dal regista quando la scena dichiara
    # una posa esibizionistica (priorita' sulla varieta' di camera).
    # Vuoti = default interni di visual_director.
    explicit_pose_tags_rear: tuple[str, ...] = ()
    explicit_pose_tags_front: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoryMarkerDef:
    """Una tappa canonica del vertical slice, definita dal pack."""

    id: str
    summary: str
    concludes_slice: bool = False


@dataclass(frozen=True)
class PressureDef:
    """Una minaccia incombente definita dal pack."""

    id: str
    summary: str
    escalation_hint: str = ""


@dataclass(frozen=True)
class WorldFactDef:
    """Un fatto di mondo canonico con le inferenze proibite.

    `does_not_imply` è la parte più preziosa: impedisce al GM di dedurre
    conseguenze non canoniche da un fatto vero.
    """

    id: str
    statement: str
    visibility: str = "contextual"  # public | contextual | secret | highly_restricted
    does_not_imply: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RelationshipDef:
    """Relazione canonica tra NPC: chi la conosce e cosa NON si può dedurre."""

    from_id: str
    to_id: str
    statement: str
    known_by: list[str] = field(default_factory=list)
    forbidden_inferences: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MissionDef:
    """Missione data-driven del world-pack.

    Le condizioni restano dati: il runtime applicativo decide se un evento
    validato le soddisfa, senza keyword match hardcoded nel motore.
    """

    id: str
    location_id: str
    name: str
    description: str
    prerequisites: list[str] = field(default_factory=list)
    state: str = "locked"
    objectives: list[dict[str, Any]] = field(default_factory=list)
    success_conditions: list[dict[str, Any]] = field(default_factory=list)
    failure_conditions: list[dict[str, Any]] = field(default_factory=list)
    rewards: list[dict[str, Any]] = field(default_factory=list)
    consequences: list[dict[str, Any]] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    alternative_solutions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class WorldPack:
    id: str
    title: str
    premise: str
    start_time_phase: str
    start_location_id: str
    player_start: dict[str, Any]
    locations: dict[str, LocationDef]
    npc_canon: dict[str, NpcCanon]
    visual_sheets: dict[str, VisualSheet]
    visual_style_en: str = ""  # regola di stile visivo del pack
    visual_negative_extra_en: str = ""  # aggiunte al prompt negativo
    # suffisso globale del prompt positivo (es. LoRA canonici globali):
    # aggiunto UNA sola volta in coda, qualunque sia il cast visibile
    visual_prompt_suffix_en: str = ""
    visual_policy: VisualPolicy = field(default_factory=VisualPolicy)
    story_markers: dict[str, StoryMarkerDef] = field(default_factory=dict)
    pressures: dict[str, PressureDef] = field(default_factory=dict)
    world_facts: dict[str, WorldFactDef] = field(default_factory=dict)
    relationships: list[RelationshipDef] = field(default_factory=list)
    missions: dict[str, MissionDef] = field(default_factory=dict)
    opening_narration: str = ""
    # regole opzionali EVENT attivabili per-pack
    open_end: bool = False
    riserva_dice: int = 0
    interactive_creation: bool = True

    def location_ids(self) -> list[str]:
        return list(self.locations.keys())

    def new_world(self, session_id: str | None = None) -> WorldState:
        """Crea lo stato iniziale di una nuova sessione dal pack."""

        session_id = session_id or str(uuid.uuid4())
        start = dict(self.player_start)
        # l'outfit canonico inglese della sheet visiva, se presente, vince
        # su quello narrativo del world.yaml: è lui che finisce nel prompt
        player_sheet = self.visual_sheets.get("player")
        player_outfit = list(player_sheet.starting_outfit_en) if player_sheet and player_sheet.starting_outfit_en else list(start.get("outfit", []))
        player = PlayerState(
            name=start.get("name"),
            location_id=self.start_location_id,
            skills=dict(start.get("skills", {})),
            inventory=list(start.get("inventory", [])),
            conditions=list(start.get("conditions", [])),
            outfit=Outfit(worn=player_outfit),
            resources=dict(start.get("resources", {})),
        )
        npcs = {}
        for canon in self.npc_canon.values():
            sheet = self.visual_sheets.get(canon.id)
            worn = list(sheet.starting_outfit_en) if sheet and sheet.starting_outfit_en else list(canon.starting_outfit)
            npcs[canon.id] = NpcState(
                id=canon.id,
                name=canon.name,
                age=canon.age,
                location_id=canon.location_id,
                present=canon.present_at_start and canon.location_id == self.start_location_id,
                knowledge=list(canon.knowledge),
                outfit=Outfit(worn=worn),
            )
        return WorldState(
            session_id=session_id,
            turn=0,
            time_phase=self.start_time_phase,
            location_id=self.start_location_id,
            player=player,
            npcs=npcs,
            riserva=self.riserva_dice,
            last_scene=self.opening_narration,
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorldPackError(message)


def load_pack(pack_dir: str | Path) -> WorldPack:
    pack_dir = Path(pack_dir)
    _require(pack_dir.is_dir(), f"world-pack non trovato: {pack_dir}")

    world_path = pack_dir / "world.yaml"
    _require(world_path.is_file(), f"world.yaml mancante in {pack_dir}")
    world_data = yaml.safe_load(world_path.read_text(encoding="utf-8")) or {}

    locations = {
        loc["id"]: LocationDef(
            id=loc["id"],
            name=str(loc.get("name", loc["id"])),
            description=str(loc.get("description", "")),
        )
        for loc in world_data.get("locations", [])
    }
    _require(bool(locations), f"{world_path}: nessuna location definita")
    start_location = str(world_data.get("start_location_id", ""))
    _require(start_location in locations, f"start_location_id sconosciuta: {start_location!r}")

    npc_canon: dict[str, NpcCanon] = {}
    npcs_path = pack_dir / "npcs.yaml"
    if npcs_path.is_file():
        npcs_data = yaml.safe_load(npcs_path.read_text(encoding="utf-8")) or {}
        for raw in npcs_data.get("npcs", []):
            _require("id" in raw and "name" in raw, f"NPC senza id/name in {npcs_path}")
            _require(int(raw.get("age", 0)) >= 18, f"NPC {raw['id']}: età adulta obbligatoria")
            loc_id = str(raw.get("location_id", start_location))
            _require(loc_id in locations, f"NPC {raw['id']}: location sconosciuta {loc_id!r}")
            npc_canon[raw["id"]] = NpcCanon(
                id=raw["id"],
                name=str(raw["name"]),
                age=int(raw["age"]),
                location_id=loc_id,
                present_at_start=bool(raw.get("present_at_start", False)),
                personality=[str(p) for p in raw.get("personality", [])],
                speech_style=str(raw.get("speech_style", "")),
                desires=[str(d) for d in raw.get("desires", [])],
                fears=[str(f) for f in raw.get("fears", [])],
                goals=[str(g) for g in raw.get("goals", [])],
                secrets=[str(s) for s in raw.get("secrets", [])],
                knowledge=[str(k) for k in raw.get("knowledge", [])],
                skills={str(k): int(v) for k, v in dict(raw.get("skills", {})).items()},
                disclosure_policy=str(raw.get("disclosure_policy", "")),
                red_lines=[str(r) for r in raw.get("red_lines", [])],
                intimate_profile=str(raw.get("intimate_profile", "")),
                starting_outfit=[str(o) for o in raw.get("starting_outfit", [])],
            )

    visual_sheets: dict[str, VisualSheet] = {}
    visual_style_en = ""
    visual_negative_extra_en = ""
    visual_prompt_suffix_en = ""
    visual_policy = VisualPolicy()
    visual_path = pack_dir / "visual.yaml"
    if visual_path.is_file():
        visual_data = yaml.safe_load(visual_path.read_text(encoding="utf-8")) or {}
        visual_style_en = str(visual_data.get("visual_style_en", "")).strip()
        visual_negative_extra_en = str(visual_data.get("negative_extra_en", "")).strip()
        visual_prompt_suffix_en = str(visual_data.get("prompt_suffix_en", "")).strip()
        raw_policy = dict(visual_data.get("visual_policy") or {})
        visual_policy = VisualPolicy(
            protected_base_prompts=bool(raw_policy.get("protected_base_prompts", False)),
            single_character_default=bool(raw_policy.get("single_character_default", False)),
            multi_character_mode=str(raw_policy.get("multi_character_mode", "shared_action")),
            speaker_action_focus=bool(raw_policy.get("speaker_action_focus", False)),
            include_sheet_negative=bool(raw_policy.get("include_sheet_negative", False)),
            sanitize_identity_layers=bool(raw_policy.get("sanitize_identity_layers", False)),
            concise_role_prompts=bool(raw_policy.get("concise_role_prompts", False)),
            max_role_prompt_words=int(raw_policy.get("max_role_prompt_words", 12)),
            avoid_facial_expressions=bool(raw_policy.get("avoid_facial_expressions", False)),
            visual_en_primary=bool(raw_policy.get("visual_en_primary", False)),
            dedupe_across_layers=bool(raw_policy.get("dedupe_across_layers", False)),
            max_scene_tags=int(raw_policy.get("max_scene_tags", 0)),
            role_prompt_optional=bool(raw_policy.get("role_prompt_optional", False)),
            preserve_revealing_outfit_traits=bool(raw_policy.get("preserve_revealing_outfit_traits", False)),
            revealing_outfit_priority=bool(raw_policy.get("revealing_outfit_priority", False)),
            visual_director_enabled=bool(raw_policy.get("visual_director_enabled", False)),
            structured_camera=bool(raw_policy.get("structured_camera", False)),
            camera_variety_enabled=bool(raw_policy.get("camera_variety_enabled", False)),
            camera_history_size=int(raw_policy.get("camera_history_size", 0)),
            crawling_preferred_views=tuple(
                str(v) for v in raw_policy.get("crawling_preferred_views", [])
            ),
            avoid_repeating_camera=bool(raw_policy.get("avoid_repeating_camera", False)),
            explicit_pose_tags_rear=tuple(
                str(v) for v in raw_policy.get("explicit_pose_tags_rear", [])
            ),
            explicit_pose_tags_front=tuple(
                str(v) for v in raw_policy.get("explicit_pose_tags_front", [])
            ),
        )
        for raw in visual_data.get("characters", []):
            _require("id" in raw and "base_prompt" in raw, f"visual sheet incompleta in {visual_path}")
            visual_sheets[raw["id"]] = VisualSheet(
                character_id=raw["id"],
                base_prompt=str(raw["base_prompt"]).strip(),
                negative_prompt=str(raw.get("negative_prompt", "")).strip(),
                character_lora_en=str(
                    raw.get("character_lora_en", raw.get("character_lora_prompt", ""))
                ).strip(),
                role_prompt_en=str(raw.get("role_prompt_en", raw.get("character_context_en", ""))).strip(),
                style_en=str(raw.get("style_en", "")).strip(),
                starting_outfit_en=tuple(str(o).strip() for o in raw.get("starting_outfit_en", []) if str(o).strip()),
            )

    known_ids = {"player", *npc_canon.keys()}
    for sheet in visual_sheets.values():
        _require(
            sheet.character_id in known_ids,
            f"visual sheet per personaggio sconosciuto: {sheet.character_id!r}",
        )

    story_markers = {
        raw["id"]: StoryMarkerDef(
            id=raw["id"],
            summary=str(raw.get("summary", "")),
            concludes_slice=bool(raw.get("concludes_slice", False)),
        )
        for raw in world_data.get("story_markers", [])
        if "id" in raw
    }
    pressures = {
        raw["id"]: PressureDef(
            id=raw["id"],
            summary=str(raw.get("summary", "")),
            escalation_hint=str(raw.get("escalation_hint", "")),
        )
        for raw in world_data.get("pressures", [])
        if "id" in raw
    }

    world_facts = {
        raw["id"]: WorldFactDef(
            id=raw["id"],
            statement=str(raw.get("statement", "")),
            visibility=str(raw.get("visibility", "contextual")),
            does_not_imply=[str(d) for d in raw.get("does_not_imply", [])],
        )
        for raw in world_data.get("world_facts", [])
        if "id" in raw
    }
    relationships = [
        RelationshipDef(
            from_id=str(raw["from"]),
            to_id=str(raw["to"]),
            statement=str(raw.get("statement", "")),
            known_by=[str(k) for k in raw.get("known_by", [])],
            forbidden_inferences=[str(f) for f in raw.get("forbidden_inferences", [])],
        )
        for raw in world_data.get("relationships", [])
        if "from" in raw and "to" in raw
    ]

    known_ids = {"player", *npc_canon.keys()}
    missions: dict[str, MissionDef] = {}
    for index, raw in enumerate(world_data.get("missions", [])):
        path = f"{world_path}: missions[{index}]"
        try:
            validate_worldpack_mission_shape(
                raw,
                location_ids=set(locations),
                known_ids=known_ids,
                path=path,
            )
        except SchemaError as exc:
            raise WorldPackError(str(exc)) from exc
        mission = MissionDef(
            id=str(raw["id"]),
            location_id=str(raw["location_id"]),
            name=str(raw["name"]),
            description=str(raw["description"]),
            prerequisites=[str(v) for v in raw.get("prerequisites", [])],
            state=str(raw.get("state", "locked")),
            objectives=[dict(v) for v in raw.get("objectives", [])],
            success_conditions=[dict(v) for v in raw.get("success_conditions", [])],
            failure_conditions=[dict(v) for v in raw.get("failure_conditions", [])],
            rewards=[dict(v) for v in raw.get("rewards", [])],
            consequences=[dict(v) for v in raw.get("consequences", [])],
            transitions=[dict(v) for v in raw.get("transitions", [])],
            alternative_solutions=[dict(v) for v in raw.get("alternative_solutions", [])],
        )
        _require(mission.id not in missions, f"missione duplicata: {mission.id!r}")
        missions[mission.id] = mission

    return WorldPack(
        id=str(world_data.get("id", pack_dir.name)),
        title=str(world_data.get("title", pack_dir.name)),
        premise=str(world_data.get("premise", "")),
        start_time_phase=str(world_data.get("start_time_phase", "giorno")),
        start_location_id=start_location,
        player_start=dict(world_data.get("player_start", {})),
        locations=locations,
        npc_canon=npc_canon,
        visual_sheets=visual_sheets,
        visual_style_en=visual_style_en,
        visual_negative_extra_en=visual_negative_extra_en,
        visual_prompt_suffix_en=visual_prompt_suffix_en,
        visual_policy=visual_policy,
        story_markers=story_markers,
        pressures=pressures,
        world_facts=world_facts,
        relationships=relationships,
        missions=missions,
        opening_narration=str(world_data.get("opening_narration", "")),
        open_end=bool(world_data.get("open_end", False)),
        riserva_dice=int(world_data.get("riserva_dice", 0)),
        interactive_creation=bool(world_data.get("interactive_creation", True)),
    )
