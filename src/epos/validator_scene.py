"""Final scene validation orchestration."""

from __future__ import annotations

from .contract import FinalScene
from .entity_ids import player_aliases_for_state
from .models import WorldState
from .validator_common import ValidationErrorDetail, ValidationReport, _add_problem
from .validator_mutations import _validate_mutation
from .validator_scene_visual import (
    _validate_player_outfit_visual_consistency,
    _validate_visible_character_text,
)
from .worldpack import WorldPack

MAX_EMOTIONAL_IMPACT = 3


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
