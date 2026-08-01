"""Regole di risoluzione epos.

Sistema proprietario a pool di d6, ispirato alla tradizione dei giochi
narrativi ma definito interamente qui. Quattro esiti canonici:

- FULL_SUCCESS      — due o più dadi pari o superiori alla difficoltà
- PARTIAL_SUCCESS   — esattamente un dado pari o superiore alla difficoltà
- FAILURE           — nessun dado qualificato
- CRITICAL_FAILURE  — tutti i dadi mostrano 1 (precedenza sul fallimento)

Scelta sicura (decisione pre-tiro, deterministica):
- pool > difficoltà  → successo pieno automatico, niente scelta
- pool == difficoltà → il giocatore sceglie: parziale sicuro oppure tiro
- pool < difficoltà  → il giocatore sceglie: fallimento sicuro oppure tiro

Layer 0: nessuna dipendenza da altri moduli epos.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 6
DIE_SIDES = 6

# Il manuale non pone un tetto al pool: il budget di creazione lo limita di
# fatto. Il tetto tecnico copre i bonus cumulabili (riserva, trigger, temerario).
POOL_HARD_CAP = 10


class Outcome(str, Enum):
    CRITICAL_FAILURE = "critical_failure"
    FAILURE = "failure"
    PARTIAL_SUCCESS = "partial_success"
    FULL_SUCCESS = "full_success"


OUTCOME_ORDER = (
    Outcome.CRITICAL_FAILURE,
    Outcome.FAILURE,
    Outcome.PARTIAL_SUCCESS,
    Outcome.FULL_SUCCESS,
)


class RuleError(ValueError):
    """Parametri di prova fuori dalle regole."""


@dataclass(frozen=True)
class Roll:
    """Un tiro eseguito. Immutabile e persistibile: è il risultato autorevole."""

    pool_size: int
    difficulty: int
    dice: tuple[int, ...]
    outcome: Outcome

    def to_dict(self) -> dict:
        return {
            "pool_size": self.pool_size,
            "difficulty": self.difficulty,
            "dice": list(self.dice),
            "outcome": self.outcome.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Roll":
        return cls(
            pool_size=data["pool_size"],
            difficulty=data["difficulty"],
            dice=tuple(data["dice"]),
            outcome=Outcome(data["outcome"]),
        )


def validate_difficulty(difficulty: int) -> int:
    difficulty = int(difficulty)
    if not MIN_DIFFICULTY <= difficulty <= MAX_DIFFICULTY:
        raise RuleError(f"Difficoltà {difficulty} fuori range {MIN_DIFFICULTY}-{MAX_DIFFICULTY}")
    return difficulty


def pool_size_for(skill_rating: int, boosts: int = 0) -> int:
    """1d6 base + 1d6 per abilità riconducibile + 1d6 per potenziamento.

    `skill_rating` somma abilità (1) e potenziamenti dell'abilità scelta;
    `boosts` copre bonus situazionali (riserva, trigger, dado temerario).
    """

    pool = 1 + max(0, int(skill_rating)) + max(0, int(boosts))
    return min(pool, POOL_HARD_CAP)


def safe_outcome_for(pool_size: int, difficulty: int) -> Outcome:
    """Esito garantito accettabile senza tirare, dato il confronto pool/difficoltà."""

    validate_difficulty(difficulty)
    if pool_size > difficulty:
        return Outcome.FULL_SUCCESS
    if pool_size == difficulty:
        return Outcome.PARTIAL_SUCCESS
    return Outcome.FAILURE


def choice_is_meaningful(pool_size: int, difficulty: int) -> bool:
    """La scelta roll/safe ha senso solo quando il pool non supera la difficoltà."""

    return pool_size <= difficulty


def outcome_of_dice(dice: tuple[int, ...], difficulty: int) -> Outcome:
    if not dice:
        raise RuleError("Pool vuoto: almeno un dado è obbligatorio")
    if all(d == 1 for d in dice):
        return Outcome.CRITICAL_FAILURE
    qualified = sum(1 for d in dice if d >= difficulty)
    if qualified >= 2:
        return Outcome.FULL_SUCCESS
    if qualified == 1:
        return Outcome.PARTIAL_SUCCESS
    return Outcome.FAILURE


def roll_dice(
    pool_size: int,
    difficulty: int,
    rng: random.Random | None = None,
    open_end: bool = False,
    talent: bool = False,
) -> Roll:
    """Esegue il tiro.

    open_end: ogni 6 aggiunge un dado al tiro (a catena), come da regola
    opzionale del manuale.
    talent: si ritira il dado più basso una sola volta; il nuovo risultato
    sostituisce il precedente anche se inferiore.
    """

    validate_difficulty(difficulty)
    if pool_size < 1:
        raise RuleError("Pool vuoto: almeno un dado è obbligatorio")
    rng = rng or random.Random()
    dice = [rng.randint(1, DIE_SIDES) for _ in range(pool_size)]
    if open_end:
        added = 0
        index = 0
        while index < len(dice):
            if dice[index] == DIE_SIDES and len(dice) < POOL_HARD_CAP * 2:
                dice.append(rng.randint(1, DIE_SIDES))
                added += 1
            index += 1
    if talent and dice:
        lowest = min(range(len(dice)), key=lambda i: dice[i])
        dice[lowest] = rng.randint(1, DIE_SIDES)
    dice_tuple = tuple(dice)
    return Roll(
        pool_size=pool_size,
        difficulty=difficulty,
        dice=dice_tuple,
        outcome=outcome_of_dice(dice_tuple, difficulty),
    )


def resolve_check(
    pool_size: int,
    difficulty: int,
    choice: str,
    rng: random.Random | None = None,
    open_end: bool = False,
    talent: bool = False,
) -> Roll:
    """Risoluzione autorevole della prova.

    choice = "safe" accetta l'esito deterministico senza tiro.
    choice = "roll" esegue il tiro. Il risultato è sempre un Roll:
    anche l'esito sicuro viene rappresentato con dadi vuoti simbolici.

    difficulty <= 0 indica un successo automatico concesso dalla fiction
    (es. Nave Feacia a Itaca, auto-pass di Calipso): nessun tiro necessario.
    """

    if difficulty <= 0:
        if pool_size < 1:
            raise RuleError("Pool vuoto: almeno un dado è obbligatorio")
        return Roll(
            pool_size=pool_size,
            difficulty=difficulty,
            dice=(),
            outcome=Outcome.FULL_SUCCESS,
        )

    validate_difficulty(difficulty)
    if pool_size < 1:
        raise RuleError("Pool vuoto: almeno un dado è obbligatorio")
    if choice == "safe":
        return Roll(
            pool_size=pool_size,
            difficulty=difficulty,
            dice=(),
            outcome=safe_outcome_for(pool_size, difficulty),
        )
    if choice == "roll":
        return roll_dice(pool_size, difficulty, rng, open_end=open_end, talent=talent)
    raise RuleError(f"Scelta non valida: {choice!r} (atteso 'roll' o 'safe')")


def reckless_reroll(roll: Roll, rng: random.Random | None = None) -> Roll:
    """Tiro temerario: ritira l'intero pool e SOVRASCRIVE il tiro precedente,
    anche se il risultato è peggiore. Il prezzo scommesso è onorato dal GM
    in caso di fallimento: è materia narrativa, non di questa funzione."""

    return roll_dice(roll.pool_size, roll.difficulty, rng)


# ---------------------------------------------------------------------------
# Confronto (interazioni): due mani, due poste in gioco
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfrontResult:
    """Esito autorevole di un confronto.

    winner:   chi vince il confronto (mano sinistra) — player | npc | stall
    narrator: chi narra l'esito (mano destra) — player | npc | shared
    """

    player_pool: int
    npc_pool: int
    player_left: int
    player_right: int
    npc_left: int
    npc_right: int
    winner: str
    narrator: str
    player_left_dice: tuple[int, ...] = ()
    npc_left_dice: tuple[int, ...] = ()
    player_right_dice: tuple[int, ...] = ()
    npc_right_dice: tuple[int, ...] = ()

    def to_dict(self) -> dict:
        return {
            "player_pool": self.player_pool,
            "npc_pool": self.npc_pool,
            "player_left": self.player_left,
            "player_right": self.player_right,
            "npc_left": self.npc_left,
            "npc_right": self.npc_right,
            "winner": self.winner,
            "narrator": self.narrator,
            "player_left_dice": list(self.player_left_dice),
            "npc_left_dice": list(self.npc_left_dice),
            "player_right_dice": list(self.player_right_dice),
            "npc_right_dice": list(self.npc_right_dice),
        }


def _hand_dice(count: int, rng: random.Random) -> tuple[int, ...]:
    return tuple(rng.randint(1, DIE_SIDES) for _ in range(count))


def _resolve_hand(
    a_count: int,
    b_count: int,
    rng: random.Random,
) -> tuple[str, tuple[int, ...], tuple[int, ...]]:
    """Chi punta più dadi vince la mano. In parità si tirano i dadi puntati
    e vince il singolo più alto. Ulteriore parità: stallo."""

    a_dice: tuple[int, ...] = ()
    b_dice: tuple[int, ...] = ()
    if a_count != b_count:
        return ("a" if a_count > b_count else "b"), a_dice, b_dice
    if a_count > 0:
        a_dice = _hand_dice(a_count, rng)
        b_dice = _hand_dice(b_count, rng)
        a_best, b_best = max(a_dice), max(b_dice)
        if a_best != b_best:
            return ("a" if a_best > b_best else "b"), a_dice, b_dice
    return "stall", a_dice, b_dice


def npc_split_strategy(npc_pool: int) -> int:
    """Divisione euristica dell'NPC: privilegia vincere il confronto,
    ma tiene un dado dietro per la posta narrativa quando può."""

    if npc_pool <= 2:
        return npc_pool  # tutto in attacco: non può permettersi la narrazione
    return (npc_pool + 1) // 2


def confront(
    player_pool: int,
    npc_pool: int,
    player_left: int,
    rng: random.Random | None = None,
    npc_left: int | None = None,
) -> ConfrontResult:
    """Risoluzione autorevole del confronto a due mani.

    player_left: dadi puntati dal giocatore nella mano sinistra (vittoria);
    i restanti vanno alla destra (narrazione). `npc_left` è iniettabile per
    i test; di default vale la strategia euristica.
    """

    rng = rng or random.Random()
    if player_pool < 1 or npc_pool < 1:
        raise RuleError("Il confronto richiede almeno un dado per parte")
    if not 0 <= player_left <= player_pool:
        raise RuleError(f"split del giocatore invalido: {player_left} su {player_pool}")
    if npc_left is None:
        npc_left = npc_split_strategy(npc_pool)
    if not 0 <= npc_left <= npc_pool:
        raise RuleError(f"split dell'NPC invalido: {npc_left} su {npc_pool}")

    player_right = player_pool - player_left
    npc_right = npc_pool - npc_left

    left_result, pl_dice, nl_dice = _resolve_hand(player_left, npc_left, rng)
    right_result, pr_dice, nr_dice = _resolve_hand(player_right, npc_right, rng)

    winner = {"a": "player", "b": "npc", "stall": "stall"}[left_result]
    narrator = {"a": "player", "b": "npc", "stall": "shared"}[right_result]

    return ConfrontResult(
        player_pool=player_pool,
        npc_pool=npc_pool,
        player_left=player_left,
        player_right=player_right,
        npc_left=npc_left,
        npc_right=npc_right,
        winner=winner,
        narrator=narrator,
        player_left_dice=pl_dice,
        npc_left_dice=nl_dice,
        player_right_dice=pr_dice,
        npc_right_dice=nr_dice,
    )
