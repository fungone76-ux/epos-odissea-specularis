"""Riparazione deterministica delle scene proposte dalla LLM.

Stessa filosofia del normalizzatore outfit: il runtime ripara ciò che può
invece di rifiutare la scena e bruciare un turno (proposta + tiro già
risolti). Due interventi, entrambi conservativi:

1. **Identificativi di personaggio** — la LLM tende a usare i NOMI
   ("ulisse", "Polifemo") dove il contratto vuole gli ID canonici
   ("player", "polifemo"). La mappa alias -> id è derivata dallo stato
   e dal registry player, mai inventata. Campi coperti: mutation.target,
   dialogue.to,
   memory witnesses, visual focus/visible/speaker/actor/reactor/
   multi_character_participants, disclosure npc_id, initiative source,
   intentions/npc_actions.
2. **Disclosure invalide** — un evento il cui fatto non è posseduto
   dall'NPC (confronto normalizzato, vedi disclosure._normalize_fact)
   viene SCARTATO singolarmente invece di far fallire l'intera scena:
   il dialogo e la narrazione restano, semplicemente non avviene il
   trasferimento di conoscenza al giocatore.
"""

from __future__ import annotations

from dataclasses import replace

from .contract import FinalScene
from .disclosure import fact_is_possessed
from .entity_ids import normalize_scene_entity_ids
from .models import WorldState
from .worldpack import WorldPack


def repair_scene_character_ids(
    state: WorldState, scene: FinalScene
) -> tuple[FinalScene, list[str]]:
    result = normalize_scene_entity_ids(
        state,
        scene,
        phase="scene_repair",
        source_payload="repair_scene",
    )
    notes = [
        f"{entry.field_path}: {entry.original_value!r} -> {entry.normalized_value!r}"
        for entry in result.entries
    ]
    return result.value, notes


def drop_invalid_disclosure_events(
    state: WorldState, pack: WorldPack, scene: FinalScene
) -> tuple[FinalScene, list[str]]:
    """Scarta gli eventi di disclosure che l'NPC non può sostenere.

    Il confronto sul fatto è normalizzato (maiuscole, spazi, punteggiatura
    finale): un fatto davvero posseduto non viene più rifiutato per un
    punto. Se resta invalido, si scarta il SINGOLO evento — la scena
    resta, manca solo il trasferimento di conoscenza.
    """

    if not scene.disclosure_events:
        return scene, []
    kept = []
    notes: list[str] = []
    for event in scene.disclosure_events:
        npc = state.npcs.get(event.npc_id)
        if npc is None or not npc.present:
            notes.append(f"disclosure scartata: NPC assente {event.npc_id!r}")
            continue
        if not fact_is_possessed(state, pack, event.npc_id, event.fact):
            notes.append(
                f"disclosure scartata: {event.npc_id} non possiede "
                f"{event.fact[:60]!r} (confronto normalizzato)"
            )
            continue
        kept.append(event)
    if len(kept) == len(scene.disclosure_events):
        return scene, []
    return replace(scene, disclosure_events=kept), notes


def repair_scene(
    state: WorldState, pack: WorldPack, scene: FinalScene
) -> tuple[FinalScene, list[str]]:
    """Pipeline di riparazione scena: id di personaggio + disclosure."""

    scene, id_notes = repair_scene_character_ids(state, scene)
    scene, disclosure_notes = drop_invalid_disclosure_events(state, pack, scene)
    return scene, [*id_notes, *disclosure_notes]
