"""Odyssey Engine — Estensione di EPOS per Odissea Specularis.

Gestisce la progressione sequenziale delle 10 location, le missioni con
prove a dadi, il Kleos, le penalità permanenti e le condizioni di
vittoria/sconfitta speciali.

Layer 1: dipende da epos.models, epos.rules, epos.worldpack.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from epos.models import NpcState, Outfit, PlayerState, WorldState
from epos.rules import (
    Outcome,
    pool_size_for,
    resolve_check,
    roll_dice,
    validate_difficulty,
)
from epos.worldpack import WorldPack, load_pack


class OdysseyError(ValueError):
    """Errore di logica del gioco Odissea."""


# ---------------------------------------------------------------------------
# Definizione delle 10 missioni
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissionDef:
    """Definizione canonica di una missione di location."""

    location_id: str
    name: str
    description: str
    primary_skill: str
    alternative_skill: str | None
    difficulty: int
    test_type: str  # "single" | "dual" | "triple"
    victory_reward: str
    failure_penalty: str
    special_rule: str = ""


MISSIONS: dict[str, MissionDef] = {
    "loc_ciclopi": MissionDef(
        location_id="loc_ciclopi",
        name="La Cieca e il Pasto",
        description="Fuggire dalla caverna di Polifemo accecandola o ingannandola.",
        primary_skill="dolos",
        alternative_skill="sarissa",
        difficulty=3,
        test_type="single",
        victory_reward="+1 Kleos. Sblocca Isola di Eolo.",
        failure_penalty="Riprova con difficoltà -1. Secondo fallimento: morte.",
        special_rule="POSEIDON_CURSE: se usi Sarissa e vinci, attiva la maledizione di Poseidone (-1 Pontos per le prossime 3 location).",
    ),
    "loc_eolo": MissionDef(
        location_id="loc_eolo",
        name="La Pelle di Cinghiale",
        description="Resistere alla curiosità di aprire la pelle di cinghiale prima del tempo.",
        primary_skill="thumos",
        alternative_skill=None,
        difficulty=2,
        test_type="single",
        victory_reward="+1 Kleos. Sacchetto dei Venti: +1 Pontos per le prossime 2 location.",
        failure_penalty="-1 Thumos permanente. Tempesta. Riprova con difficoltà -1.",
        special_rule="",
    ),
    "loc_sirene": MissionDef(
        location_id="loc_sirene",
        name="Il Canto Maschile",
        description="Sopravvivere al canto delle Sirene senza impazzire o annegare.",
        primary_skill="eros",
        alternative_skill="thumos",
        difficulty=4,
        test_type="single",
        victory_reward="+1 Kleos. Sblocca lo Stretto.",
        failure_penalty="-2 Thumos permanenti. Riprova con difficoltà -1.",
        special_rule="",
    ),
    "loc_scilla_cariddi": MissionDef(
        location_id="loc_scilla_cariddi",
        name="Il Passaggio",
        description="Attraversare lo stretto tra Scilla e Cariddi.",
        primary_skill="pontos",
        alternative_skill="sarissa",
        difficulty=5,
        test_type="dual",
        victory_reward="+1 Kleos. Sblocca l'Isola di Circe.",
        failure_penalty="-1 Sarissa permanente. Ferita grave. Riprova con difficoltà -1.",
        special_rule="DUAL: tira Pontos prima. Se fallisci, tira Sarissa per sopravvivere.",
    ),
    "loc_circe": MissionDef(
        location_id="loc_circe",
        name="La Radura Nera",
        description="Ottenere il rituale per l'Ade da Circe senza trasformarsi in bestia.",
        primary_skill="eros",
        alternative_skill="thumos",
        difficulty=5,
        test_type="single",
        victory_reward="+1 Kleos. Rituale per l'Ade sbloccato.",
        failure_penalty="-1 Dolos permanente. Trasformazione parziale. Riprova con difficoltà -1.",
        special_rule="MOLY: se possiedi la pianta di moly (da Ermete), difficoltà diventa 3.",
    ),
    "loc_cimmeri": MissionDef(
        location_id="loc_cimmeri",
        name="Il Sangue delle Ombre",
        description="Versare il sangue e resistere alle ombre affamate per parlare con Tiresia.",
        primary_skill="thumos",
        alternative_skill=None,
        difficulty=6,
        test_type="single",
        victory_reward="+1 Kleos. Tiresia rivela la difficoltà delle prossime 2 location.",
        failure_penalty="-2 Thumos permanenti. Possessione. Riprova con difficoltà -1.",
        special_rule="BLOOD_PRICE: se attivi la profezia di Tiresia, -1 Sarissa permanente.",
    ),
    "loc_calipso": MissionDef(
        location_id="loc_calipso",
        name="La Grotta Profumata",
        description="Ricordare Itaca dopo sette anni di piacere e oblio.",
        primary_skill="thumos",
        alternative_skill="eros",
        difficulty=6,
        test_type="single",
        victory_reward="+1 Kleos. Libertà da Ogygia.",
        failure_penalty="GAME OVER. Dimentichi Itaca per sempre.",
        special_rule="LETHE: nessun riprovo. Se fallisci, è la fine. Se Kleos ≥ 4, puoi auto-passare Thumos narrando un ricordo di Penelope.",
    ),
    "loc_sole": MissionDef(
        location_id="loc_sole",
        name="Il Bestiame D'oro",
        description="Resistere alla fame senza commettere sacrilegio sul bestiame sacro di Helios.",
        primary_skill="thumos",
        alternative_skill=None,
        difficulty=4,
        test_type="single",
        victory_reward="+1 Kleos. Sblocca Scheria.",
        failure_penalty="-2 Pontos permanenti. Folgore di Zeus. Riprova con difficoltà -1.",
        special_rule="",
    ),
    "loc_scheria": MissionDef(
        location_id="loc_scheria",
        name="La Corte dei Feaci",
        description="Commuovere la corte dei Feaci e ottenere il passaggio verso Itaca.",
        primary_skill="dolos",
        alternative_skill="eros",
        difficulty=3,
        test_type="single",
        victory_reward="+1 Kleos. Nave Feacia: auto-success al primo tiro di Itaca.",
        failure_penalty="Scoperta e cacciata. Riprova con difficoltà -1.",
        special_rule="",
    ),
    "loc_itaca": MissionDef(
        location_id="loc_itaca",
        name="Il Massacro",
        description="Il ritorno finale: travestimento, arco, riconoscimento.",
        primary_skill="dolos",
        alternative_skill=None,
        difficulty=6,
        test_type="triple",
        victory_reward="VITTORIA. Il numero di Kleos determina l'epilogo.",
        failure_penalty="GAME OVER. Morte o esilio.",
        special_rule="TRIPLE: tre tiri obbligatori. 1) Dolos ≥ 6 (travestimento). 2) Sarissa ≥ 6 (arco). 3) Eros ≥ 6 (riconoscimento). Se Nave Feacia è attiva, il primo tiro è auto-success.",
    ),
}

# Ordine canonico delle location
LOCATION_ORDER = [
    "loc_ciclopi",
    "loc_eolo",
    "loc_sirene",
    "loc_scilla_cariddi",
    "loc_circe",
    "loc_cimmeri",
    "loc_calipso",
    "loc_sole",
    "loc_scheria",
    "loc_itaca",
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class MissionResult:
    """Risultato di un tentativo di missione."""

    success: bool
    outcome: Outcome
    dice: tuple[int, ...]
    pool_size: int
    difficulty: int
    skill_used: str
    message: str
    permanent_penalty: dict[str, int] = field(default_factory=dict)
    game_over: bool = False
    kleos_gained: int = 0
    special_triggered: list[str] = field(default_factory=list)


class OdysseyEngine:
    """Motore di gioco per Odissea Specularis."""

    def __init__(
        self,
        pack_dir: str | Path,
        state: WorldState | None = None,
        rng: random.Random | None = None,
    ):
        self.pack = load_pack(pack_dir)
        self.rng = rng or random.Random()
        if state is None:
            self.state = self.pack.new_world()
            self._init_odyssey_state()
        else:
            self.state = state

    # -- persistenza --------------------------------------------------------

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.state.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path, pack_dir: str | Path) -> "OdysseyEngine":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        state = WorldState.from_dict(data)
        return cls(pack_dir=pack_dir, state=state)

    # -- inizializzazione ---------------------------------------------------

    def _init_odyssey_state(self) -> None:
        """Imposta le flag e le risorse iniziali specifiche di Odissea."""
        self.state.flags["odyssey_location_index"] = 0
        self.state.flags["odyssey_kleos"] = 0
        self.state.flags["poseidon_curse_active"] = False
        self.state.flags["poseidon_curse_remaining"] = 0
        self.state.flags["wind_bag_active"] = False
        self.state.flags["wind_bag_remaining"] = 0
        self.state.flags["moly_possessed"] = False
        self.state.flags["underworld_passage"] = False
        self.state.flags["tiresia_prophecy"] = False
        self.state.flags["phaeacian_ship"] = False
        self.state.flags["calipso_auto_pass"] = False
        self.state.flags["game_over"] = False
        self.state.flags["victory"] = False
        self.state.flags["retry_difficulty_offset"] = 0
        self.state.flags["location_attempts"] = 0

    # -- utilità ------------------------------------------------------------

    def current_location_id(self) -> str:
        return LOCATION_ORDER[self.state.flags["odyssey_location_index"]]

    def current_mission(self) -> MissionDef:
        return MISSIONS[self.current_location_id()]

    def _get_skill_rating(self, skill: str) -> int:
        return self.state.player.skill_rating(skill)

    def _compute_pool(self, skill: str, boosts: int = 0) -> int:
        """Calcola il pool per un tiro, applicando maledizioni e bonus."""
        rating = self._get_skill_rating(skill)
        # Maledizione di Poseidone
        if (
            self.state.flags.get("poseidon_curse_active", False)
            and skill == "pontos"
        ):
            boosts -= 1
        # Sacchetto dei venti
        if (
            self.state.flags.get("wind_bag_active", False)
            and skill == "pontos"
        ):
            boosts += 1
        return pool_size_for(rating, boosts)

    def _apply_permanent_penalty(self, skill: str, amount: int) -> None:
        """Applica una penalità permanente a una skill del giocatore."""
        current = self.state.player.skills.get(skill, 0)
        new_val = max(0, current - amount)
        self.state.player.skills[skill] = new_val

    def _advance_location(self) -> None:
        """Avanza alla prossima location se possibile."""
        idx = self.state.flags["odyssey_location_index"]
        if idx + 1 < len(LOCATION_ORDER):
            self.state.flags["odyssey_location_index"] = idx + 1
            self.state.flags["retry_difficulty_offset"] = 0
            self.state.flags["location_attempts"] = 0
            next_loc = LOCATION_ORDER[idx + 1]
            self.state.player.location_id = next_loc
            self.state.location_id = next_loc
        else:
            self.state.flags["victory"] = True
            self.state.flags["game_over"] = True

    # -- tiri -------------------------------------------------------------

    def _roll(
        self,
        skill: str,
        difficulty: int,
        boosts: int = 0,
        use_safe: bool = False,
    ) -> tuple[Outcome, tuple[int, ...], int]:
        """Esegue un tiro singolo e restituisce esito, dadi, pool."""
        diff = validate_difficulty(difficulty)
        pool = self._compute_pool(skill, boosts)
        choice = "safe" if use_safe else "roll"
        roll = resolve_check(pool, diff, choice, rng=self.rng)
        return roll.outcome, roll.dice, pool

    # -- missioni -----------------------------------------------------------

    def attempt_mission(
        self,
        skill_choice: str | None = None,
        use_safe: bool = False,
        use_moly: bool = False,
        use_auto_pass: bool = False,
    ) -> MissionResult:
        """Tenta la missione della location corrente.

        Args:
            skill_choice: "primary", "alternative", o nome esatto della skill.
            use_safe: se True, accetta l'esito deterministico senza tiro.
            use_moly: se True e siamo a Circe, riduce difficoltà.
            use_auto_pass: se True e siamo a Calipso con Kleos≥4, auto-pass.
        """
        if self.state.flags.get("game_over", False):
            raise OdysseyError("La partita è terminata.")

        mission = self.current_mission()
        loc_id = mission.location_id
        self.state.flags["location_attempts"] += 1
        attempts = self.state.flags["location_attempts"]

        # Determina skill e difficoltà
        if skill_choice is None or skill_choice == "primary":
            skill = mission.primary_skill
        elif skill_choice == "alternative":
            skill = mission.alternative_skill or mission.primary_skill
        else:
            skill = skill_choice

        diff = mission.difficulty - self.state.flags.get("retry_difficulty_offset", 0)
        diff = max(1, diff)

        # Regole speciali pre-tiro
        special_triggered: list[str] = []

        # Moly a Circe
        if loc_id == "loc_circe" and use_moly and self.state.flags.get("moly_possessed", False):
            diff = max(1, diff - 2)
            special_triggered.append("moly_used")

        # Auto-pass a Calipso
        if loc_id == "loc_calipso" and use_auto_pass and self.state.flags.get("calipso_auto_pass", False):
            outcome = Outcome.FULL_SUCCESS
            dice = ()
            pool = self._compute_pool(skill)
            return self._resolve_mission_result(
                mission, True, outcome, dice, pool, skill, diff,
                special_triggered
            )

        # Nave Feacia a Itaca (primo tiro)
        if loc_id == "loc_itaca" and self.state.flags.get("phaeacian_ship", False):
            # Il primo tiro (Dolos) è auto-success se non ancora usato
            if not self.state.flags.get("itaca_first_roll_done", False):
                self.state.flags["itaca_first_roll_done"] = True
                outcome = Outcome.FULL_SUCCESS
                dice = ()
                pool = self._compute_pool(skill)
                special_triggered.append("phaeacian_ship_auto")
                return self._resolve_mission_result(
                    mission, True, outcome, dice, pool, skill, diff,
                    special_triggered
                )

        # Esecuzione tiro
        outcome, dice, pool = self._roll(skill, diff, use_safe=use_safe)
        success = outcome in (Outcome.FULL_SUCCESS, Outcome.PARTIAL_SUCCESS)

        # Regole speciali post-tiro
        # Poseidon's Curse a Ciclopi se usata Sarissa
        if loc_id == "loc_ciclopi" and success and skill == "sarissa":
            self.state.flags["poseidon_curse_active"] = True
            self.state.flags["poseidon_curse_remaining"] = 3
            special_triggered.append("poseidon_curse_activated")

        return self._resolve_mission_result(
            mission, success, outcome, dice, pool, skill, diff,
            special_triggered
        )

    def _resolve_mission_result(
        self,
        mission: MissionDef,
        success: bool,
        outcome: Outcome,
        dice: tuple[int, ...],
        pool: int,
        skill: str,
        difficulty: int,
        special_triggered: list[str],
    ) -> MissionResult:
        """Costruisce il MissionResult e applica effetti permanenti."""
        loc_id = mission.location_id
        penalties: dict[str, int] = {}
        kleos = 0
        game_over = False
        message = ""

        if success:
            kleos = 1
            self.state.flags["odyssey_kleos"] = self.state.flags.get("odyssey_kleos", 0) + 1
            message = f"Missione '{mission.name}' superata! {mission.victory_reward}"

            # Ricompense speciali
            if loc_id == "loc_eolo":
                self.state.flags["wind_bag_active"] = True
                self.state.flags["wind_bag_remaining"] = 2
            elif loc_id == "loc_circe":
                self.state.flags["underworld_passage"] = True
            elif loc_id == "loc_cimmeri":
                self.state.flags["tiresia_prophecy"] = True
            elif loc_id == "loc_scheria":
                self.state.flags["phaeacian_ship"] = True

            # Avanzamento
            self._advance_location()

        else:
            # Fallimento
            message = f"Missione '{mission.name}' fallita. {mission.failure_penalty}"

            # Penalità permanenti
            if loc_id == "loc_eolo":
                penalties["thumos"] = 1
                self._apply_permanent_penalty("thumos", 1)
            elif loc_id == "loc_sirene":
                penalties["thumos"] = 2
                self._apply_permanent_penalty("thumos", 2)
            elif loc_id == "loc_scilla_cariddi":
                penalties["sarissa"] = 1
                self._apply_permanent_penalty("sarissa", 1)
            elif loc_id == "loc_circe":
                penalties["dolos"] = 1
                self._apply_permanent_penalty("dolos", 1)
            elif loc_id == "loc_cimmeri":
                penalties["thumos"] = 2
                self._apply_permanent_penalty("thumos", 2)
            elif loc_id == "loc_sole":
                penalties["pontos"] = 2
                self._apply_permanent_penalty("pontos", 2)

            # Game Over immediati
            if loc_id == "loc_calipso":
                game_over = True
                self.state.flags["game_over"] = True
                message = "GAME OVER. Hai dimenticato Itaca. Calipso ti tiene per sempre."
            elif loc_id == "loc_itaca":
                game_over = True
                self.state.flags["game_over"] = True
                message = "GAME OVER. Le Proche ti hanno uccisa. Itaca è perduta."
            elif loc_id == "loc_ciclopi" and attempts >= 2:
                game_over = True
                self.state.flags["game_over"] = True
                message = "GAME OVER. Polifemo ti ha divorata."
            else:
                # Riprova con difficoltà ridotta
                self.state.flags["retry_difficulty_offset"] = self.state.flags.get("retry_difficulty_offset", 0) + 1

        # Decrementa contatori temporanei
        if self.state.flags.get("poseidon_curse_remaining", 0) > 0:
            self.state.flags["poseidon_curse_remaining"] -= 1
            if self.state.flags["poseidon_curse_remaining"] <= 0:
                self.state.flags["poseidon_curse_active"] = False

        if self.state.flags.get("wind_bag_remaining", 0) > 0:
            self.state.flags["wind_bag_remaining"] -= 1
            if self.state.flags["wind_bag_remaining"] <= 0:
                self.state.flags["wind_bag_active"] = False

        return MissionResult(
            success=success,
            outcome=outcome,
            dice=dice,
            pool_size=pool,
            difficulty=difficulty,
            skill_used=skill,
            message=message,
            permanent_penalty=penalties,
            game_over=game_over,
            kleos_gained=kleos,
            special_triggered=special_triggered,
        )

    # -- tiro a tre mani (Itaca) ------------------------------------------

    def attempt_itaca_triple(
        self,
        dolos_safe: bool = False,
        sarissa_safe: bool = False,
        eros_safe: bool = False,
    ) -> list[MissionResult]:
        """Esegue i tre tiri obbligatori di Itaca.

        Returns:
            Lista di 3 MissionResult. Se il primo fallisce, il secondo e terzo
            vengono comunque eseguiti per completezza narrativa, ma la vittoria
            è impossibile.
        """
        if self.current_location_id() != "loc_itaca":
            raise OdysseyError("Non sei a Itaca.")

        results: list[MissionResult] = []
        mission = MISSIONS["loc_itaca"]

        # Tiro 1: Dolos (travestimento)
        r1 = self.attempt_mission(
            skill_choice="dolos",
            use_safe=dolos_safe,
        )
        results.append(r1)
        if r1.game_over:
            return results

        # Tiro 2: Sarissa (arco)
        r2 = self.attempt_mission(
            skill_choice="sarissa",
            use_safe=sarissa_safe,
        )
        results.append(r2)
        if r2.game_over:
            return results

        # Tiro 3: Eros (riconoscimento)
        r3 = self.attempt_mission(
            skill_choice="eros",
            use_safe=eros_safe,
        )
        results.append(r3)

        return results

    # -- interazioni speciali -----------------------------------------------

    def activate_tiresia_prophecy(self) -> dict[str, Any]:
        """Attiva la profezia di Tiresia: rivela difficoltà future, paga sangue."""
        if not self.state.flags.get("tiresia_prophecy", False):
            raise OdysseyError("Non hai ancora ottenuto il passaggio per l'Ade.")
        if self.state.flags.get("tiresia_used", False):
            raise OdysseyError("Hai già usato la profezia di Tiresia.")

        self.state.flags["tiresia_used"] = True
        self._apply_permanent_penalty("sarissa", 1)

        idx = self.state.flags["odyssey_location_index"]
        future = []
        for i in range(idx + 1, min(idx + 3, len(LOCATION_ORDER))):
            loc = LOCATION_ORDER[i]
            future.append({
                "location": loc,
                "name": MISSIONS[loc].name,
                "difficulty": MISSIONS[loc].difficulty,
            })

        return {
            "message": "Tiresia beve il tuo sangue e parla. Vedi il futuro.",
            "blood_price": "-1 Sarissa permanente",
            "future_locations": future,
        }

    def give_moly(self) -> None:
        """Ermete dona la pianta di moly a Ulisse."""
        self.state.flags["moly_possessed"] = True

    def check_calipso_auto_pass(self) -> bool:
        """Verifica se Ulisse può auto-passare Calipso con un ricordo."""
        kleos = self.state.flags.get("odyssey_kleos", 0)
        if kleos >= 4:
            self.state.flags["calipso_auto_pass"] = True
            return True
        return False

    # -- stato di gioco -----------------------------------------------------

    def game_status(self) -> dict[str, Any]:
        """Restituisce lo stato corrente del gioco."""
        loc_id = self.current_location_id()
        mission = MISSIONS[loc_id]
        player = self.state.player

        return {
            "turn": self.state.turn,
            "location": {
                "id": loc_id,
                "name": mission.name,
                "description": mission.description,
            },
            "player": {
                "name": player.name,
                "skills": dict(player.skills),
                "kleos": self.state.flags.get("odyssey_kleos", 0),
                "inventory": list(player.inventory),
                "conditions": list(player.conditions),
            },
            "active_effects": {
                "poseidon_curse": self.state.flags.get("poseidon_curse_active", False),
                "wind_bag": self.state.flags.get("wind_bag_active", False),
                "moly": self.state.flags.get("moly_possessed", False),
                "phaeacian_ship": self.state.flags.get("phaeacian_ship", False),
            },
            "game_over": self.state.flags.get("game_over", False),
            "victory": self.state.flags.get("victory", False),
            "attempts_at_location": self.state.flags.get("location_attempts", 0),
        }

    def next_turn(self) -> None:
        """Avanza il turno di gioco."""
        self.state.turn += 1
