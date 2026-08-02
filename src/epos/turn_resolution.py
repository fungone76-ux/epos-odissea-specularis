"""Pure helpers for deterministic turn resolution."""

from __future__ import annotations


# Le abilita degli NPC nei pack sono in lingua libera (persuasione, scherma...),
# mentre la proposta di confronto usa le skill canoniche del giocatore
# (social, physical...). Mappa canonico -> nomi liberi equivalenti: il rating
# dell'NPC e il migliore tra corrispondenza esatta e alias, mai inventato.
NPC_SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "social": (
        "persuasione",
        "comando_sala",
        "comando",
        "diplomazia",
        "intimidazione",
        "inganno",
        "manipolazione",
        "lettura_persone",
    ),
    "physical": ("combattimento", "scherma", "forza", "atletica", "resistenza"),
    "stealth": ("furtivita", "furtivit\u00e0", "sotterfugo", "inganno"),
    "investigate": ("indagine", "osservazione", "lettura_persone", "erboristeria", "conoscenza"),
    "intimate": ("seduzione", "manipolazione", "intimit\u00e0", "intimita"),
    "power": ("potere", "potere_acqua", "magia", "erboristeria"),
}


def npc_confront_rating(canon_skills: dict[str, int], skill: str) -> int:
    """Rating di un NPC in un confronto: esatto prima, alias poi, altrimenti 0."""

    if skill in canon_skills:
        return canon_skills[skill]
    return max(
        (int(canon_skills[alias]) for alias in NPC_SKILL_ALIASES.get(skill, ()) if alias in canon_skills),
        default=0,
    )