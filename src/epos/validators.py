"""Validazione: l'arbitro Python tra le proposte della LLM e lo stato.

Principi: adeguatezza, integritÃ , pertinenza, presenza, conoscenza,
persistenza, consenso. Le mutazioni invalide vengono rifiutate con
diagnostica, mai corrette inventando contenuto narrativo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .contract import CheckProposal, ConfrontProposal, FinalScene, Mutation
from .entity_ids import player_aliases_for_state
from .models import (
    KNOWLEDGE_SOURCES,
    RELATIONSHIP_DOMAINS,
    Outfit,
    WorldState,
    outfit_state,
)
from .rules import MAX_DIFFICULTY, MIN_DIFFICULTY
from .worldpack import WorldPack

# Limiti di proporzionalitÃ  per singola mutazione in un turno.
MAX_RELATIONSHIP_DELTA = 15
MAX_RESOURCE_DELTA = 3
MAX_EMOTIONAL_IMPACT = 3


def _scene_implies_full_nudity(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "completely nude",
            "fully naked",
            "no clothing",
            "no clothes",
            "no armor",
            "no dress",
            "no chiton",
            "without clothing",
            "without clothes",
            "bare-skinned",
            "completamente nuda",
            "nuda completa",
        )
    )


def _scene_implies_topless(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in ("topless", "bare chest", "bare breasts", "no top", "no bra")
    )


def _scene_implies_bottomless(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in ("bottomless", "no lower clothing", "no skirt", "no panties")
    )


def _outfit_after_scene(state: WorldState, target: str, mutations: list[Mutation]) -> Outfit | None:
    character = state.player if target == "player" else state.npcs.get(target)
    if character is None:
        return None
    outfit = Outfit(
        worn=list(character.outfit.worn),
        removed=list(character.outfit.removed),
        revision=character.outfit.revision,
    )
    for mutation in mutations:
        if mutation.target != target:
            continue
        item = str(mutation.payload.get("item", ""))
        if mutation.type == "outfit_remove":
            outfit.remove_item(item)
        elif mutation.type == "outfit_wear":
            outfit.wear(item)
    return outfit


def _mentions_unworn_clothing(text: str, state_after: dict[str, Any]) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in ("no chiton", "no armor", "no dress", "no clothing")):
        return False
    worn_text = " ".join(state_after["worn_items"]).lower()
    clothing_words = ("chiton", "armor", "dress", "robe", "peplos", "himation", "skirt", "sandals")
    if not any(word in lowered for word in clothing_words):
        return False
    if any(word in worn_text and word in lowered for word in clothing_words):
        return False
    return any(
        phrase in lowered
        for phrase in ("wearing", "wears", "dressed in", "clad in", " in a ", " in her ")
    )


def _validate_player_outfit_visual_consistency(
    state: WorldState,
    scene: FinalScene,
    problems: list[str],
    errors: list[ValidationErrorDetail],
) -> None:
    if scene.visual is None or "player" not in scene.visual.visible_characters:
        return
    outfit_after = _outfit_after_scene(state, "player", scene.mutations)
    if outfit_after is None:
        return
    current = outfit_state(outfit_after)
    text = " ".join(
        [
            scene.narration,
            scene.visual.summary,
            scene.visual.visual_en,
            *scene.visual.tags_en,
        ]
    )
    if _scene_implies_full_nudity(text) and current["nudity_mode"] != "fully_nude":
        _add_problem(
            problems,
            errors,
            "visual_outfit_state_mismatch",
            "visual.visual_en",
            "visual descrive nudita completa ma lo stato outfit canonico conserva abiti torso/lower",
            outfit_state=current,
        )
    elif _scene_implies_topless(text) and current["torso_slot"]:
        _add_problem(
            problems,
            errors,
            "visual_outfit_state_mismatch",
            "visual.visual_en",
            "visual descrive topless ma lo stato outfit canonico conserva abiti torso",
            outfit_state=current,
        )
    elif _scene_implies_bottomless(text) and current["lower_body_slot"]:
        _add_problem(
            problems,
            errors,
            "visual_outfit_state_mismatch",
            "visual.visual_en",
            "visual descrive bottomless ma lo stato outfit canonico conserva abiti lower-body",
            outfit_state=current,
        )
    elif current["nudity_mode"] == "fully_nude" and _mentions_unworn_clothing(text, current):
        _add_problem(
            problems,
            errors,
            "visual_outfit_state_mismatch",
            "visual.visual_en",
            "visual reintroduce abiti non presenti nello stato outfit canonico",
            outfit_state=current,
        )


@dataclass(frozen=True)
class ValidationErrorDetail:
    code: str
    path: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ValidationWarning:
    code: str
    path: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ValidationReport:
    problems: list[str] = field(default_factory=list)
    errors: list[ValidationErrorDetail] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and not self.errors

    def __post_init__(self) -> None:
        if self.problems and not self.errors:
            object.__setattr__(
                self,
                "errors",
                [
                    ValidationErrorDetail(
                        code=_code_for_problem(problem),
                        path=_path_for_problem(problem),
                        message=problem,
                    )
                    for problem in self.problems
                ],
            )
        if self.errors and not self.problems:
            object.__setattr__(self, "problems", [error.message for error in self.errors])

    def to_dict(self, *, stage: str = "semantic", phase: str = "") -> dict[str, Any]:
        return {
            "valid": self.ok,
            "validation_stage": stage,
            "phase": phase,
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "problems": list(self.problems),
        }


def _code_for_problem(problem: str) -> str:
    text = problem.lower()
    if "testimone assente" in text:
        return "invalid_memory_witness"
    if "memory_event richiede witnesses" in text:
        return "memory_without_witnesses"
    if "personaggio visibile ma assente" in text:
        return "visible_character_not_present"
    if "focus_character deve comparire" in text:
        return "focus_character_not_visible"
    if "target inesistente" in text:
        return "invalid_mutation_target"
    if "destinazione sconosciuta" in text:
        return "invalid_location_reference"
    if "marker" in text:
        return "invalid_story_marker"
    if "target non presente" in text or "target assente" in text:
        return "invalid_mutation_target"
    if "skill" in text:
        return "missing_required_field"
    if "difficolt" in text:
        return "semantic_contract_rejected"
    return "semantic_contract_rejected"


def _path_for_problem(problem: str) -> str:
    text = problem.lower()
    if "memory_event" in text:
        return "memory_events"
    if "visual:" in text:
        return "visual.visible_characters"
    if "dialogo" in text:
        return "dialogue"
    if "relationship_delta" in text:
        return "mutations.relationship_delta"
    if "location_change" in text:
        return "mutations.location_change"
    if "story_marker" in text or "marker" in text:
        return "mutations.story_marker_add"
    if "target" in text:
        return "target_ids"
    if "skill" in text:
        return "skill"
    if "difficolt" in text:
        return "difficulty"
    return ""


def _add_problem(
    problems: list[str],
    errors: list[ValidationErrorDetail],
    code: str,
    path: str,
    message: str,
    **details: Any,
) -> None:
    problems.append(message)
    errors.append(ValidationErrorDetail(code=code, path=path, message=message, details=details))


def validate_check_proposal(
    state: WorldState,
    pack: WorldPack,
    proposal: CheckProposal,
) -> ValidationReport:
    """La proposta del GM non Ã¨ autorevole: Python la sottopone a giudizio."""

    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []

    if not MIN_DIFFICULTY <= proposal.difficulty <= MAX_DIFFICULTY:
        _add_problem(
            problems,
            errors,
            "semantic_contract_rejected",
            "check.difficulty",
            f"difficoltÃ  {proposal.difficulty} fuori range {MIN_DIFFICULTY}-{MAX_DIFFICULTY}",
            value=proposal.difficulty,
            min=MIN_DIFFICULTY,
            max=MAX_DIFFICULTY,
        )

    if not proposal.skill:
        _add_problem(problems, errors, "missing_required_field", "check.skill", "skill della prova non dichiarata")

    for index, target_id in enumerate(proposal.target_ids):
        if target_id not in ("player", *state.npcs.keys()):
            _add_problem(
                problems,
                errors,
                "unknown_npc_id",
                f"check.target_ids[{index}]",
                f"target inesistente: {target_id!r}",
                target_id=target_id,
            )
        elif not state.is_present(target_id):
            _add_problem(
                problems,
                errors,
                "invalid_mutation_target",
                f"check.target_ids[{index}]",
                f"target non presente nella scena: {target_id!r}",
                target_id=target_id,
            )

    if proposal.opposition == "npc_resistance" and not any(
        tid in state.npcs for tid in proposal.target_ids
    ):
        _add_problem(
            problems,
            errors,
            "semantic_contract_rejected",
            "check.opposition",
            "opposizione npc_resistance senza un NPC bersaglio",
        )

    return ValidationReport(problems, errors)


def validate_confront_proposal(
    state: WorldState,
    pack: WorldPack,
    proposal: ConfrontProposal,
) -> ValidationReport:
    """Il confronto richiede un NPC presente e una skill dichiarata."""

    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []
    if proposal.target_id not in state.npcs:
        _add_problem(
            problems,
            errors,
            "unknown_npc_id",
            "confront.target_id",
            f"confronto con NPC inesistente: {proposal.target_id!r}",
            target_id=proposal.target_id,
        )
    elif not state.npcs[proposal.target_id].present:
        _add_problem(
            problems,
            errors,
            "actor_character_not_present",
            "confront.target_id",
            f"confronto con NPC assente: {proposal.target_id!r}",
            target_id=proposal.target_id,
        )
    if not proposal.skill:
        _add_problem(problems, errors, "missing_required_field", "confront.skill", "skill del confronto non dichiarata")
    return ValidationReport(problems, errors)


def _validate_mutation(
    state: WorldState,
    pack: WorldPack,
    mutation: Mutation,
    present_ids: set[str],
) -> list[str]:
    problems: list[str] = []
    target = mutation.target
    target_exists = target == "player" or target in state.npcs or target == "world"

    if mutation.type in (
        "relationship_delta",
        "knowledge_add",
        "condition_add",
        "condition_remove",
        "item_add",
        "item_remove",
        "outfit_wear",
        "outfit_remove",
        "wound_add",
        "resource_delta",
        "emotion_set",
        "intention_set",
    ):
        if not target_exists or target == "world":
            problems.append(f"{mutation.type}: target inesistente {target!r}")
        elif target not in present_ids and mutation.type not in ("intention_set",):
            # presenza: si puÃ² mutare solo chi Ã¨ nella scena (le intenzioni degli
            # NPC presenti sono l'eccezione gestita sopra)
            if not (target in state.npcs and state.npcs[target].present):
                problems.append(f"{mutation.type}: target assente dalla scena {target!r}")

    if mutation.type == "relationship_delta":
        for domain, delta in (mutation.payload or {}).items():
            if domain not in RELATIONSHIP_DOMAINS:
                problems.append(f"relationship_delta: dominio sconosciuto {domain!r}")
            elif abs(int(delta)) > MAX_RELATIONSHIP_DELTA:
                problems.append(
                    f"relationship_delta: delta {delta} oltre il limite Â±{MAX_RELATIONSHIP_DELTA}"
                )

    if mutation.type == "resource_delta":
        for key, delta in (mutation.payload or {}).items():
            if abs(int(delta)) > MAX_RESOURCE_DELTA:
                problems.append(
                    f"resource_delta ({key}): delta {delta} oltre il limite Â±{MAX_RESOURCE_DELTA}"
                )

    if mutation.type == "location_change":
        destination = str(mutation.payload.get("location_id", ""))
        if destination not in pack.locations:
            problems.append(f"location_change: destinazione sconosciuta {destination!r}")

    if mutation.type == "item_remove":
        item = str(mutation.payload.get("item", ""))
        if target == "player" and item not in state.player.inventory:
            problems.append(f"item_remove: {item!r} non nell'inventario del giocatore")

    if mutation.type == "outfit_remove":
        item = str(mutation.payload.get("item", ""))
        character = state.player if target == "player" else state.npcs.get(target, None)
        worn = character.outfit.worn if character is not None else []
        if item not in worn:
            problems.append(
                f"outfit_remove: {item!r} non indossato da {target!r} "
                'â€” usa payload {"item": "<capo esatto da outfit_worn>"}, '
                "una mutazione per capo (mai liste)"
            )

    if mutation.type == "thread_close":
        thread_id = str(mutation.payload.get("thread_id", ""))
        thread = next((t for t in state.active_threads if t.id == thread_id and t.status == "open"), None)
        if thread is None:
            problems.append(f"thread_close: thread {thread_id!r} non aperto")
        elif not str(mutation.payload.get("reason", mutation.reason)).strip():
            problems.append("thread_close: reason obbligatoria")

    if mutation.type == "thread_open":
        if not str(mutation.payload.get("summary", "")).strip():
            problems.append("thread_open: summary obbligatoria")
        if not str(mutation.payload.get("close_condition", "")).strip():
            problems.append("thread_open: close_condition obbligatoria")
        participants = mutation.payload.get("participants", ["player"])
        if not isinstance(participants, list) or not participants:
            problems.append("thread_open: participants obbligatorio")
        else:
            for participant in participants:
                if str(participant) not in present_ids:
                    problems.append(f"thread_open: partecipante assente {participant!r}")

    if mutation.type == "knowledge_add":
        fact = str(mutation.payload.get("fact", "")).strip()
        if not fact:
            problems.append("knowledge_add: fact obbligatorio")
        source = str(mutation.payload.get("source", "contextual")).strip()
        if source not in KNOWLEDGE_SOURCES:
            problems.append(f"knowledge_add: source non valida {source!r}")
        try:
            credibility = float(mutation.payload.get("credibility", 1.0))
        except (TypeError, ValueError):
            problems.append("knowledge_add: credibility deve essere numerica")
        else:
            if not 0.0 <= credibility <= 1.0:
                problems.append("knowledge_add: credibility fuori range 0.0-1.0")

    if mutation.type == "story_marker_add":
        from .spine import validate_story_marker

        marker_id = str(mutation.payload.get("marker_id", ""))
        problems.extend(validate_story_marker(pack, state, marker_id))

    if mutation.type == "mission_complete":
        if not str(mutation.target).strip():
            problems.append("mission_complete: target mission_id obbligatorio")
        objectives = mutation.payload.get("completed_objectives", [])
        if not isinstance(objectives, list) or not objectives:
            problems.append("mission_complete: completed_objectives obbligatorio")

    return problems


def _character_id_for_name(state: WorldState, speaker: str) -> str | None:
    """Risolve lo speaker del dialogo: id diretto o nome dell'NPC."""

    if speaker.strip().casefold() in player_aliases_for_state(state):
        return "player"
    if speaker in state.npcs:
        return speaker
    for npc in state.npcs.values():
        if npc.name == speaker:
            return npc.id
    return None


def _strip_place_owner_mentions(text: str) -> str:
    """Remove NPC-name mentions that identify a place/object, not a visible body."""
    patterns = [
        r"\bpolyphemus['\u2019]?\s+cave\b",
        r"\bcave\s+of\s+polyphemus\b",
        r"\bpolifemo['\u2019]?\s+cave\b",
        r"\bcave\s+of\s+polifemo\b",
        r"\bcaverna\s+di\s+polifemo\b",
        r"\bgrotta\s+di\s+polifemo\b",
    ]
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned

def _validate_visible_character_text(
    state: WorldState,
    scene: FinalScene,
    problems: list[str],
    errors: list[ValidationErrorDetail],
) -> None:
    if scene.visual is None:
        return
    visible = set(scene.visual.visible_characters)
    text = " ".join([scene.visual.summary, scene.visual.visual_en, *scene.visual.tags_en])
    text = _strip_place_owner_mentions(text)
    lowered = text.casefold()
    conflicts: list[str] = []
    for npc_id, npc in state.npcs.items():
        if npc_id in visible:
            continue
        names = {npc_id.casefold(), str(npc.name).casefold()}
        if npc_id == "polifemo":
            names.update({"polyphemus", "cyclops", "giant", "gigante"})
        if any(re.search(rf"\b{re.escape(name)}\b", lowered) for name in names if name):
            conflicts.append(npc_id)
    if conflicts:
        _add_problem(
            problems,
            errors,
            "visible_character_text_conflict",
            "visual.visual_en",
            "visual descrive un secondo personaggio non autorizzato da visible_characters",
            visible_characters=list(scene.visual.visible_characters),
            conflicts=conflicts,
        )


def validate_scene(
    state: WorldState,
    pack: WorldPack,
    scene: FinalScene,
) -> ValidationReport:
    """Valida mutazioni, memoria e coerenza visuale di una scena finale."""

    problems: list[str] = []
    errors: list[ValidationErrorDetail] = []
    present_ids = set(state.present_character_ids())

    for mutation in scene.mutations:
        mutation_problems = _validate_mutation(state, pack, mutation, present_ids)
        problems.extend(mutation_problems)

    # dialoghi: speaker e destinatario devono essere presenti in scena
    for line in scene.dialogue:
        if line.speaker != "player":
            speaker_id = _character_id_for_name(state, line.speaker)
            if speaker_id is None or speaker_id not in present_ids:
                _add_problem(
                    problems,
                    errors,
                    "unknown_npc_id",
                    "dialogue.speaker",
                    f"dialogo di speaker non presente: {line.speaker!r}",
                    speaker=line.speaker,
                )
        if line.to is not None and line.to != "player" and line.to not in present_ids:
            _add_problem(
                problems,
                errors,
                "unknown_npc_id",
                "dialogue.to",
                f"dialogo rivolto a personaggio assente: {line.to!r}",
                target=line.to,
            )

    # iniziative autonome
    from .initiative import validate_initiative
    from .spine import validate_pressure_advance

    for event in scene.initiatives:
        problems.extend(validate_initiative(state, event))
        if event.type == "pressure_advance":
            problems.extend(validate_pressure_advance(pack, state, event))

    # disclosure di segreti e conoscenze
    from .disclosure import validate_disclosure

    for event in scene.disclosure_events:
        problems.extend(validate_disclosure(state, pack, event))

    for memory_index, memory in enumerate(scene.memory_events):
        for witness_index, witness in enumerate(memory.witnesses):
            if witness not in present_ids:
                _add_problem(
                    problems,
                    errors,
                    "invalid_memory_witness",
                    f"memory_events[{memory_index}].witnesses[{witness_index}]",
                    f"memory_event: testimone assente {witness!r} â€” "
                    "un NPC non puÃ² ricordare ciÃ² che non ha osservato",
                    witness=witness,
                    location_id=state.location_id,
                )
        if abs(memory.emotional_impact) > MAX_EMOTIONAL_IMPACT:
            _add_problem(
                problems,
                errors,
                "semantic_contract_rejected",
                f"memory_events[{memory_index}].emotional_impact",
                f"memory_event: impatto emotivo {memory.emotional_impact} "
                f"oltre il limite Â±{MAX_EMOTIONAL_IMPACT}",
                value=memory.emotional_impact,
                max=MAX_EMOTIONAL_IMPACT,
            )

    if scene.visual is None:
        _add_problem(
            problems,
            errors,
            "missing_required_field",
            "visual",
            "visual obbligatorio: ogni turno produce un'immagine",
        )
    else:
        for visible_index, visible in enumerate(scene.visual.visible_characters):
            if visible not in present_ids:
                _add_problem(
                    problems,
                    errors,
                    "visible_character_not_present",
                    f"visual.visible_characters[{visible_index}]",
                    f"visual: personaggio visibile ma assente {visible!r}",
                    character_id=visible,
                    location_id=state.location_id,
                )

    _validate_player_outfit_visual_consistency(state, scene, problems, errors)
    _validate_visible_character_text(state, scene, problems, errors)

    return ValidationReport(problems, errors)
