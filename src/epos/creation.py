"""Creazione interattiva del personaggio, secondo il manuale EVENT.

Tre domande: Chi è? / Che aspetto ha? / Cosa sa fare?
Sei punti da distribuire tra abilità libere (1 punto) e potenziamenti
(+1 punto ciascuno, max rating 5). Una abilità può essere sottolineata
come talento. Opzionale: un innesco pre-scritto.

L'aspetto dichiarato genera la character sheet visiva della sessione.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import CREATION_SKILL_BUDGET, MAX_SKILL_RATING, PlayerState
from .worldpack import VisualSheet, WorldPack


class CreationError(ValueError):
    """Risposte di creazione invalide."""


@dataclass
class CreationAnswers:
    identity: str = ""  # "Chi è?" — una frase
    appearance: str = ""  # "Che aspetto ha?" — una frase
    skills: dict[str, int] = field(default_factory=dict)  # tag -> potenziamenti
    talent: str | None = None
    trigger: str | None = None
    visual_base_prompt: str | None = None  # se assente, deriva da appearance


def skill_points_used(skills: dict[str, int]) -> int:
    """Ogni abilità costa 1, ogni potenziamento costa 1."""

    return sum(1 + max(0, rating) for rating in skills.values())


class CreationService:
    def __init__(self, pack: WorldPack):
        self.pack = pack

    def validate(self, answers: CreationAnswers) -> list[str]:
        problems: list[str] = []
        if not answers.identity.strip():
            problems.append("manca la risposta a 'Chi è?'")
        if not answers.appearance.strip():
            problems.append("manca la risposta a 'Che aspetto ha?'")
        if not answers.skills:
            problems.append("serve almeno un'abilità")
        for skill, rating in answers.skills.items():
            if not skill.strip():
                problems.append("abilità senza nome")
            if not 0 <= rating <= MAX_SKILL_RATING - 1:
                problems.append(
                    f"potenziamenti di {skill!r} fuori range 0-{MAX_SKILL_RATING - 1}"
                )
        used = skill_points_used(answers.skills)
        if used > CREATION_SKILL_BUDGET:
            problems.append(
                f"budget abilità superato: {used}/{CREATION_SKILL_BUDGET} punti"
            )
        if answers.talent is not None and answers.talent not in answers.skills:
            problems.append(f"il talento {answers.talent!r} non è tra le abilità")
        return problems

    def create(
        self, answers: CreationAnswers
    ) -> tuple[PlayerState, VisualSheet]:
        """Produce lo stato iniziale del giocatore e la sua sheet visiva."""

        problems = self.validate(answers)
        if problems:
            raise CreationError("; ".join(problems))

        # il rating nello stato conta i dadi bonus: abilità (1) + potenziamenti
        skills = {tag: 1 + enh for tag, enh in answers.skills.items()}

        base = dict(self.pack.player_start)
        player = PlayerState(
            name=base.get("name"),
            location_id=self.pack.start_location_id,
            identity=answers.identity.strip(),
            appearance=answers.appearance.strip(),
            skills=skills,
            talent=answers.talent,
            trigger=answers.trigger,
            inventory=list(base.get("inventory", [])),
            conditions=list(base.get("conditions", [])),
            outfit=type(self.pack.new_world().player.outfit)(
                worn=list(base.get("outfit", []))
            ),
            resources=dict(base.get("resources", {})),
        )
        sheet = VisualSheet(
            character_id="player",
            base_prompt=(answers.visual_base_prompt or answers.appearance).strip(),
        )
        return player, sheet


def award_experience(state_player: PlayerState, skill: str) -> int:
    """Esperienza (manuale): una nuova abilità o un potenziamento.

    Restituisce il nuovo rating dell'abilità scelta."""

    skill = skill.strip()
    if not skill:
        raise CreationError("abilità vuota")
    current = state_player.skill_rating(skill)
    if current >= MAX_SKILL_RATING:
        raise CreationError(f"{skill!r} è già al massimo ({MAX_SKILL_RATING})")
    state_player.skills[skill] = current + 1 if skill in state_player.skills else 1
    return state_player.skill_rating(skill)
