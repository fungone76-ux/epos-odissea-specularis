"""Odyssey Mission Tracker — integrato nel ciclo EPOS post-commit.

Monitora le 10 missioni sequenziali. Dopo ogni turno (post-commit),
verifica se la prova risolta corrisponde alla missione attiva.
Se passata, avanza location. Se fallita, applica penalita.
Genera intuizioni dopo 3 turni senza progresso.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from epos.models import PressureState, WorldState
from epos.turn_service import TurnResult
from epos.worldpack import MissionDef as PackMissionDef, WorldPack


def _norm_text(text: str) -> str:
    return " ".join(str(text).casefold().split())


def _effect_message(effect_id: str) -> str:
    messages = {
        "wind_bag": "Sacchetto dei Venti attivo (+1 pool Pontos per 2 location)",
        "underworld_passage": "Rituale per l'Ade ottenuto",
        "tiresia_prophecy": "Profezia di Tiresia sbloccata",
        "phaeacian_ship": "Nave Feacia ottenuta",
    }
    return messages.get(effect_id, effect_id)


def _pressure_message(pressure_id: str) -> str:
    messages = {
        "press_poseidone": "Maledizione di Poseidone attivata! +1 difficolta Pontos per 3 location.",
    }
    return messages.get(pressure_id, f"Pressione avanzata: {pressure_id}")


def _skill_delta_message(skill: str, delta: int) -> str:
    if not skill or delta == 0:
        return ""
    label = skill.capitalize()
    if delta < 0:
        amount = abs(delta)
        suffix = "permanente" if amount == 1 else "permanenti"
        return f"-{amount} {label} {suffix}"
    return f"+{delta} {label}"


def _terminal_failure_reason(location_id: str) -> str:
    reasons = {
        "loc_ciclopi": "Polifemo ti ha divorata.",
        "loc_calipso": "Hai dimenticato Itaca. Calipso ti tiene per sempre.",
        "loc_itaca": "Le Proche ti hanno uccisa. Itaca e perduta.",
    }
    return reasons.get(location_id, "La partita e terminata.")


# ---------------------------------------------------------------------------
# Definizione missioni
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissionDef:
    location_id: str
    name: str
    description: str
    primary_skill: str
    alternative_skill: str | None
    difficulty: int
    victory_reward: str
    failure_penalty: str
    special_rule: str = ""
    # NPC che la prova deve avere come target per completare la missione.
    # None = qualunque prova con la skill giusta completa (missioni
    # "ambientali": Eolo, Sirene, Scilla, Sole, Scheria).
    required_target: str | None = None
    rewards: tuple[dict[str, Any], ...] = ()
    consequences: tuple[dict[str, Any], ...] = ()
    failure_conditions: tuple[dict[str, Any], ...] = ()
    transitions: tuple[dict[str, Any], ...] = ()
    source_mission_id: str = ""


MISSIONS: dict[str, MissionDef] = {
    "loc_ciclopi": MissionDef(
        location_id="loc_ciclopi",
        name="La Cieca e il Pasto",
        description="Fuggire dalla caverna di Polifemo accecandola o ingannandola.",
        primary_skill="dolos",
        alternative_skill="sarissa",
        difficulty=3,
        victory_reward="Sblocca Isola di Eolo.",
        failure_penalty="Riprova con difficolta -1. Secondo fallimento: morte.",
        special_rule="POSEIDON_CURSE: se usi Sarissa e vinci, -1 Pontos per 3 location.",
        required_target="polifemo",
    ),
    "loc_eolo": MissionDef(
        location_id="loc_eolo",
        name="La Pelle di Cinghiale",
        description="Resistere alla curiosita di aprire la pelle di cinghiale.",
        primary_skill="thumos",
        alternative_skill=None,
        difficulty=2,
        victory_reward="Sacchetto dei Venti: +1 Pontos per 2 location.",
        failure_penalty="-1 Thumos permanente. Tempesta.",
        special_rule="",
    ),
    "loc_sirene": MissionDef(
        location_id="loc_sirene",
        name="Il Canto Maschile",
        description="Sopravvivere al canto delle Sirene senza impazzire.",
        primary_skill="eros",
        alternative_skill="thumos",
        difficulty=4,
        victory_reward="Sblocca lo Stretto.",
        failure_penalty="-2 Thumos permanenti.",
        special_rule="",
    ),
    "loc_scilla_cariddi": MissionDef(
        location_id="loc_scilla_cariddi",
        name="Il Passaggio",
        description="Attraversare lo stretto tra Scilla e Cariddi.",
        primary_skill="pontos",
        alternative_skill="sarissa",
        difficulty=5,
        victory_reward="Sblocca l'Isola di Circe.",
        failure_penalty="-1 Sarissa permanente. Ferita grave.",
        special_rule="DUAL: tira Pontos prima. Se fallisci, tira Sarissa per sopravvivere.",
    ),
    "loc_circe": MissionDef(
        location_id="loc_circe",
        name="La Radura Nera",
        description="Ottenere il rituale per l'Ade da Circe senza trasformarsi in bestia.",
        primary_skill="eros",
        alternative_skill="thumos",
        difficulty=5,
        victory_reward="Rituale per l'Ade sbloccato.",
        failure_penalty="-1 Dolos permanente. Trasformazione parziale.",
        special_rule="MOLY: se possiedi la pianta di moly, difficolta diventa 3.",
        required_target="circe",
    ),
    "loc_cimmeri": MissionDef(
        location_id="loc_cimmeri",
        name="Il Sangue delle Ombre",
        description="Versare il sangue e resistere alle ombre affamate per parlare con Tiresia.",
        primary_skill="thumos",
        alternative_skill=None,
        difficulty=6,
        victory_reward="Tiresia rivela la difficolta delle prossime 2 location.",
        failure_penalty="-2 Thumos permanenti. Possessione.",
        special_rule="BLOOD_PRICE: se attivi la profezia, -1 Sarissa permanente.",
        required_target="tiresia",
    ),
    "loc_calipso": MissionDef(
        location_id="loc_calipso",
        name="La Grotta Profumata",
        description="Ricordare Itaca dopo sette anni di piacere e oblio.",
        primary_skill="thumos",
        alternative_skill="eros",
        difficulty=6,
        victory_reward="Liberta da Ogygia.",
        failure_penalty="GAME OVER. Dimentichi Itaca per sempre.",
        special_rule="LETHE: nessun riprovo. Se fallisci, e la fine. Se Kleos >= 4, auto-pass Thumos.",
        required_target="calipso",
    ),
    "loc_sole": MissionDef(
        location_id="loc_sole",
        name="Il Bestiame D'oro",
        description="Resistere alla fame senza commettere sacrilegio sul bestiame sacro di Helios.",
        primary_skill="thumos",
        alternative_skill=None,
        difficulty=4,
        victory_reward="Sblocca Scheria.",
        failure_penalty="-2 Pontos permanenti. Folgore di Zeus.",
        special_rule="",
    ),
    "loc_scheria": MissionDef(
        location_id="loc_scheria",
        name="La Corte dei Feaci",
        description="Commuovere la corte dei Feaci e ottenere il passaggio verso Itaca.",
        primary_skill="dolos",
        alternative_skill="eros",
        difficulty=3,
        victory_reward="Nave Feacia: auto-success al primo tiro di Itaca.",
        failure_penalty="Scoperta e cacciata.",
        special_rule="",
    ),
    "loc_itaca": MissionDef(
        location_id="loc_itaca",
        name="Il Massacro",
        description="Il ritorno finale: travestimento, arco, riconoscimento.",
        primary_skill="dolos",
        alternative_skill=None,
        difficulty=6,
        victory_reward="VITTORIA. Il Kleos determina l'epilogo.",
        failure_penalty="GAME OVER. Morte o esilio.",
        special_rule="TRIPLE: tre tiri obbligatori. 1) Dolos 2) Sarissa 3) Eros. Nave Feacia = auto-pass primo.",
    ),
}

LOCATION_ORDER = [
    "loc_ciclopi", "loc_eolo", "loc_sirene", "loc_scilla_cariddi",
    "loc_circe", "loc_cimmeri", "loc_calipso", "loc_sole",
    "loc_scheria", "loc_itaca",
]


def missions_from_pack(pack: WorldPack) -> dict[str, MissionDef]:
    """Converte le missioni YAML del world-pack nella vista runtime Odissea.

    Il tracker lavora per location per compatibilita con il flusso storico,
    ma i dati canonici provengono da ``world.yaml`` quando disponibili.
    """

    if not pack.missions:
        return dict(MISSIONS)
    missions: dict[str, MissionDef] = {}
    for mission in pack.missions.values():
        missions[mission.location_id] = _runtime_mission_from_pack(mission)
    return missions


def location_order_from_pack(pack: WorldPack) -> list[str]:
    if not pack.missions:
        return list(LOCATION_ORDER)
    return [mission.location_id for mission in pack.missions.values()]


def _runtime_mission_from_pack(mission: PackMissionDef) -> MissionDef:
    objective = dict(mission.objectives[0]) if mission.objectives else {}
    required_skills = [str(v) for v in objective.get("required_skills", [])]
    primary_skill = required_skills[0] if required_skills else "dolos"
    alternative_skill = required_skills[1] if len(required_skills) > 1 else None
    difficulty = int(objective.get("difficulty", 1))
    reward_text = _condition_text(mission.success_conditions) or _reward_text(mission.rewards)
    failure_text = _failure_text(mission.failure_conditions) or _consequence_text(mission.consequences)
    special_rule = _consequence_text(mission.consequences)
    return MissionDef(
        location_id=mission.location_id,
        name=mission.name,
        description=mission.description,
        primary_skill=primary_skill,
        alternative_skill=alternative_skill,
        difficulty=difficulty,
        victory_reward=reward_text,
        failure_penalty=failure_text,
        special_rule=special_rule,
        required_target=objective.get("target"),
        rewards=tuple(dict(v) for v in mission.rewards),
        consequences=tuple(dict(v) for v in mission.consequences),
        failure_conditions=tuple(dict(v) for v in mission.failure_conditions),
        transitions=tuple(dict(v) for v in mission.transitions),
        source_mission_id=mission.id,
    )


def _condition_text(conditions: list[dict[str, Any]]) -> str:
    for condition in conditions:
        if condition.get("type") == "stake_contains" and condition.get("text"):
            return str(condition["text"])
    return ""


def _reward_text(rewards: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for reward in rewards:
        if reward.get("type") == "resource_delta":
            chunks.append(f"{reward.get('resource')} {reward.get('delta'):+}")
        elif reward.get("type") == "resource_set":
            chunks.append(f"{reward.get('resource')}={reward.get('value')}")
        elif reward.get("type") == "effect":
            chunks.append(str(reward.get("id", "effect")))
        elif reward.get("type") == "victory":
            chunks.append("VITTORIA")
    return "; ".join(chunks)


def _failure_text(failures: list[dict[str, Any]]) -> str:
    parts = []
    for failure in failures:
        kind = str(failure.get("type", "failure"))
        parts.append(kind + (" terminale" if failure.get("terminal") else ""))
    return "; ".join(parts)


def _consequence_text(consequences: list[dict[str, Any]]) -> str:
    parts = []
    for consequence in consequences:
        kind = str(consequence.get("type", "consequence"))
        detail = consequence.get("pressure_id") or consequence.get("resource") or consequence.get("skill") or consequence.get("condition") or consequence.get("reason")
        parts.append(f"{kind}:{detail}" if detail else kind)
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Intuizioni progressive
# ---------------------------------------------------------------------------

INTUITIONS: dict[str, list[str]] = {
    "loc_ciclopi": [
        "Polifemo e fuori con le pecore. La caverna e aperta.",
        "Il fuoco ha un palo di olivo. E affilato come una lancia.",
        "Polifemo chiede il tuo nome. Non conosce la menzogna.",
    ],
    "loc_eolo": [
        "Eolo tiene i venti in una pelle di cinghiale. Sembra fragile.",
        "La curiosita e piu pericolosa della tempesta.",
        "Se apri la pelle prima del tempo, i venti ti spazzano via.",
    ],
    "loc_sirene": [
        "Il canto arriva prima degli scogli. Tre voci maschili.",
        "Le ossa bianche sugli scogli sono di chi ha ascoltato.",
        "La verita che promettono non vale il prezzo del tuo spirito.",
    ],
    "loc_scilla_cariddi": [
        "Lo stretto e una mascella. A sinistra il vortice, a destra le teste.",
        "Cariddi inghiotte tutto. Scilla afferra chi passa troppo vicino.",
        "Non puoi vincere. Puoi solo sopravvivere sacrificando qualcosa.",
    ],
    "loc_circe": [
        "Il palazzo nero e circondato da lupi e leoni. Sono uomini trasformati.",
        "Circe offre vino. Un sorso e dimentichi il mare.",
        "Ermete ha una pianta bianca. Il moly. L'unico antidoto.",
    ],
    "loc_cimmeri": [
        "La nebbia grigia non si alza mai. Campi di asfodeli.",
        "Le ombre affamate si radunano dove il sangue cola.",
        "Tiresia aspetta. Parla solo dopo il pagamento.",
    ],
    "loc_calipso": [
        "Sette anni di cedro, seta e sesso infinito.",
        "Calipso piange ogni notte dopo l'amplesso.",
        "Se dimentichi Itaca, resti per sempre. Ricorda Penelope.",
    ],
    "loc_sole": [
        "Le vacche dorate pascolano. Il ventre urla.",
        "Helio guarda dal cielo. Il sacrilegio porta la folgore.",
        "Mangerai alghe. Mangerai sassi. Ma non toccherai il sacro.",
    ],
    "loc_scheria": [
        "Arete tiene corte. Le parole valgono piu delle frecce.",
        "Non dire il tuo nome. Il nome e l'ultima cosa che hai.",
        "Commuovi la regina. Ottieni il passaggio verso Itaca.",
    ],
    "loc_itaca": [
        "Il porto di Phorcys. La terra sa di sale e memoria.",
        "Eumea ti riconosce al tatto. Non agli occhi.",
        "L'arco e nascosto. Le Proche sono cento. Penelope aspetta.",
    ],
}


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

class OdysseyMissionTracker:
    """Tracker delle missioni dell'Odissea. Si integra con WorldState.

    Viene chiamato DOPO il commit del TurnService, in _on_result della GUI.
    Modifica direttamente lo stato (location, skills, flags) e restituisce
    un report dei cambiamenti da mostrare al giocatore.
    """

    def __init__(
        self,
        state: WorldState,
        pack: WorldPack | None = None,
        missions: dict[str, MissionDef] | None = None,
        location_order: list[str] | None = None,
    ):
        self.state = state
        self.missions = dict(missions) if missions is not None else (
            missions_from_pack(pack) if pack is not None else dict(MISSIONS)
        )
        self.location_order = list(location_order) if location_order is not None else (
            location_order_from_pack(pack) if pack is not None else list(LOCATION_ORDER)
        )
        self._init_flags()

    def _init_flags(self) -> None:
        """Inizializza le flag di missione nello stato."""
        flags = self.state.flags
        flags.setdefault("odyssey_location_index", 0)
        flags.setdefault("odyssey_kleos", 0)
        flags.setdefault("poseidon_curse_active", False)
        flags.setdefault("poseidon_curse_remaining", 0)
        flags.setdefault("wind_bag_active", False)
        flags.setdefault("wind_bag_remaining", 0)
        flags.setdefault("moly_possessed", False)
        flags.setdefault("underworld_passage", False)
        flags.setdefault("tiresia_prophecy", False)
        flags.setdefault("phaeacian_ship", False)
        flags.setdefault("calipso_auto_pass", False)
        flags.setdefault("calipso_auto_pass_used", False)
        flags.setdefault("game_over", False)
        flags.setdefault("victory", False)
        flags.setdefault("mission_attempts", 0)
        flags.setdefault("turns_without_progress", 0)
        flags.setdefault("retry_difficulty_offset", 0)
        flags.setdefault("itaca_phase", 0)  # 0=travestimento, 1=arco, 2=letto
        flags.setdefault("last_skill_used", "")  # Per feedback al giocatore
        flags.setdefault("last_skill_relevant", False)  # Per feedback al giocatore
        flags.setdefault("action_history", [])  # Ultime 3 azioni (skill, esito, rilevanza)

    # -- skill richieste ------------------------------------------------------

    # Itaca e una missione a 3 fasi: la skill richiesta dipende dalla fase.
    ITACA_PHASE_SKILLS = ("dolos", "sarissa", "eros")
    ITACA_PHASE_NAMES = ("Travestimento", "L'Arco", "Il Letto d'Ulivo")

    def required_skills(self) -> tuple[str, ...]:
        """Skill che fanno avanzare la missione corrente."""
        loc_id = self.current_location_id()
        mission = self.missions[loc_id]
        if loc_id == "loc_itaca":
            phase = min(self.state.flags.get("itaca_phase", 0), 2)
            return (self.ITACA_PHASE_SKILLS[phase],)
        skills = [mission.primary_skill]
        if mission.alternative_skill:
            skills.append(mission.alternative_skill)
        return tuple(skills)

    # -- query ----------------------------------------------------------------

    def current_location_id(self) -> str:
        idx = self.state.flags.get("odyssey_location_index", 0)
        return self.location_order[idx] if idx < len(self.location_order) else self.location_order[-1]

    def current_mission(self) -> MissionDef:
        return self.missions[self.current_location_id()]

    def is_game_over(self) -> bool:
        return self.state.flags.get("game_over", False)

    def is_victory(self) -> bool:
        return self.state.flags.get("victory", False)

    def get_kleos(self) -> int:
        return self.state.flags.get("odyssey_kleos", 0)

    def get_intuition(self) -> str:
        """Restituisce l'intuizione appropriata in base ai turni senza progresso."""
        loc_id = self.current_location_id()
        turns = self.state.flags.get("turns_without_progress", 0)
        hints = INTUITIONS.get(loc_id, [])
        if not hints:
            return ""
        if turns < 3:
            return ""
        idx = min((turns - 3) // 2, len(hints) - 1)
        return hints[idx]

    def get_emotional_state(self) -> str:
        """Stato emotivo di Ulisse basato su Thumos e condizioni."""
        thumos = self.state.player.skill_rating("thumos")
        if thumos <= 1:
            return "Spezzata. Il mare sembra casa. Non ricordi perche resisti."
        if thumos <= 2:
            return "Esausta. Ogni passo pesa. La memoria si sfrangia."
        if thumos <= 3:
            return "Stanca, ma ancora lucida. Il fuoco di Itaca brucia lontano."
        if thumos <= 4:
            return "Determinata. Le cicatrici ti ricordano chi sei."
        return "Temprata. Vent'anni di guerra e mare non ti hanno piegato."

    def can_attempt_mission(self) -> tuple[bool, str]:
        """Verifica se il giocatore puo tentare la missione."""
        if self.is_game_over():
            return False, "La partita e terminata."
        if self.is_victory():
            return False, "Hai vinto."
        thumos = self.state.player.skill_rating("thumos")
        if thumos <= 0:
            return False, "Sei troppo esausta per agire. Riposa o cerca aiuto."
        return True, ""

    # -- post-turno -----------------------------------------------------------

    def process_turn(self, result: TurnResult) -> dict[str, Any]:
        """Processa il risultato di un turno EPOS (post-commit).

        Ritorna un dict con i cambiamenti da mostrare al giocatore.
        """
        if self.is_game_over() or self.is_victory():
            return {"status": "ended"}

        loc_id = self.current_location_id()
        mission = self.missions[loc_id]
        changes: dict[str, Any] = {"status": "ongoing"}

        # Verifica se il turno contiene una prova rilevante per la missione
        if result.roll is not None and result.proposal is not None:
            skill = result.proposal.skill
            outcome = result.roll.outcome.value
            self.state.flags["last_skill_used"] = skill

            required = self.required_skills()

            # Registra l'azione nel log (max 3, la piu recente in coda)
            history = self.state.flags.setdefault("action_history", [])
            history.append({
                "skill": skill,
                "outcome": outcome,
                "relevant": skill in required,
            })
            del history[:-3]

            if skill in required:
                # E una prova della missione!
                self.state.flags["last_skill_relevant"] = True
                self.state.flags["mission_attempts"] += 1

                if outcome in ("full_success", "partial_success"):
                    # La missione si completa solo se la prova prende di mira
                    # l'obiettivo (es. ingannare POLIFEMO, non solo avvicinarsi
                    # alla caverna). Un successo con la skill giusta ma senza
                    # target e PREPARAZIONE: -1 difficolta al vero tentativo.
                    target = mission.required_target
                    targets = list(result.proposal.target_ids or [])
                    if target and target not in targets:
                        offset = min(
                            self.state.flags.get("retry_difficulty_offset", 0) + 1,
                            max(mission.difficulty - 1, 0),
                        )
                        self.state.flags["retry_difficulty_offset"] = offset
                        self.state.flags["turns_without_progress"] = 0
                        changes["preparation"] = True
                        changes["target_npc"] = target
                        changes["message"] = (
                            f"Azione riuscita, ma la missione non e ancora compiuta: "
                            f"devi affrontare {target.upper()} direttamente. "
                            f"La preparazione ti avvantaggia (difficolta -1 al "
                            f"prossimo tentativo di missione)."
                        )
                    elif loc_id == "loc_itaca" and self.state.flags.get("itaca_phase", 0) < 2:
                        # Itaca a 3 fasi: successo parziale di percorso, avanza la fase
                        phase = self.state.flags["itaca_phase"]
                        self.state.flags["itaca_phase"] = phase + 1
                        self.state.flags["turns_without_progress"] = 0
                        self.state.flags["retry_difficulty_offset"] = 0
                        changes["itaca_phase_advanced"] = True
                        changes["itaca_phase_completed"] = self.ITACA_PHASE_NAMES[phase]
                        changes["itaca_phase_next"] = self.ITACA_PHASE_NAMES[phase + 1]
                        changes["itaca_next_skill"] = self.ITACA_PHASE_SKILLS[phase + 1]
                    elif self._mission_completion_validated(mission, result):
                        # Missione superata!
                        changes["mission_completed"] = True
                        changes["mission_name"] = mission.name
                        self._complete_mission(mission, result, changes)
                    else:
                        offset = min(
                            self.state.flags.get("retry_difficulty_offset", 0) + 1,
                            max(mission.difficulty - 1, 0),
                        )
                        self.state.flags["retry_difficulty_offset"] = offset
                        self.state.flags["turns_without_progress"] = 0
                        changes["preparation"] = True
                        changes["message"] = (
                            "Azione riuscita, ma la missione non e ancora compiuta: "
                            "il successo del check non autorizza una conclusione "
                            "senza posta finale o transizione mission_complete."
                        )
                else:
                    # Fallimento
                    self.state.flags["turns_without_progress"] += 1
                    self._apply_failure_penalty(mission, changes)
            else:
                # Prova non rilevante per la missione
                self.state.flags["last_skill_relevant"] = False
                self.state.flags["turns_without_progress"] += 1
                changes["wrong_skill"] = True
                changes["used_skill"] = skill
                changes["required_skills"] = " o ".join(required)
                changes["message"] = f"Hai usato {skill.upper()}, ma la missione richiede {changes['required_skills'].upper()}. Nessun progresso."
        else:
            # Nessuna prova (no_check) — NON incrementa turni senza progresso
            self.state.flags["last_skill_used"] = ""
            self.state.flags["last_skill_relevant"] = False
            pass

        # Decrementa contatori temporanei
        self._tick_effects()

        # Verifica stato emotivo
        thumos = self.state.player.skill_rating("thumos")
        if thumos <= 0 and not self.is_game_over():
            self.state.flags["game_over"] = True
            changes["game_over"] = True
            changes["reason"] = "Thumos esaurito. La follia ti ha preso."

        return changes

    def _mission_completion_validated(self, mission: MissionDef, result: TurnResult) -> bool:
        """Outcome del check e transizione missione sono separati.

        Una missione si chiude solo se la scena contiene una mutazione
        mission_complete validata oppure se la posta risolta e' esplicitamente
        la ricompensa canonica della missione. Un full_success preparatorio
        resta progresso locale, non completamento missione.
        """

        if self._has_explicit_mission_complete(mission, result):
            return True
        stake = _norm_text(result.stake)
        reward = _norm_text(mission.victory_reward)
        return bool(stake and reward and reward in stake)

    @staticmethod
    def _has_explicit_mission_complete(mission: MissionDef, result: TurnResult) -> bool:
        for mutation in result.scene_mutations:
            if mutation.get("type") != "mission_complete":
                continue
            target = str(mutation.get("target", ""))
            if target in (mission.location_id, mission.name):
                objectives = dict(mutation.get("payload") or {}).get("completed_objectives", [])
                return bool(objectives)
        return False

    def _complete_mission(self, mission: MissionDef, result: TurnResult, changes: dict) -> None:
        """Completa la missione attiva applicando i dati del world-pack."""
        self.state.flags["turns_without_progress"] = 0
        self.state.flags["mission_attempts"] = 0
        self.state.flags["retry_difficulty_offset"] = 0

        self._apply_success_rewards(mission, changes)
        self._apply_success_consequences(mission, result, changes)

        # Speciale runtime: Calipso registra l'eventuale auto-pass consumato.
        if mission.location_id == "loc_calipso":
            self.state.flags["calipso_auto_pass_used"] = True

        self._advance_from_mission_transition(mission, changes)

    def _apply_success_rewards(self, mission: MissionDef, changes: dict) -> None:
        if not mission.rewards:
            self.state.flags["odyssey_kleos"] += 1
            return

        applied: list[dict[str, Any]] = []
        for reward in mission.rewards:
            reward_type = str(reward.get("type", ""))
            if reward_type == "resource_delta":
                resource = str(reward.get("resource", ""))
                delta = int(reward.get("delta", 0))
                if resource == "kleos":
                    self.state.flags["odyssey_kleos"] = self.state.flags.get("odyssey_kleos", 0) + delta
                elif resource:
                    resources = self.state.player.resources
                    resources[resource] = int(resources.get(resource, 0)) + delta
                applied.append(dict(reward))
            elif reward_type == "resource_set":
                resource = str(reward.get("resource", ""))
                value = reward.get("value", 1)
                if resource:
                    self.state.flags[resource] = bool(value) if value in (0, 1, True, False) else value
                    applied.append(dict(reward))
                    changes["effect"] = _effect_message(resource)
            elif reward_type == "flag_set":
                flag = str(reward.get("flag", ""))
                if flag:
                    self.state.flags[flag] = reward.get("value", True)
                    applied.append(dict(reward))
                    changes["effect"] = _effect_message(flag)
            elif reward_type == "effect":
                effect_id = str(reward.get("id", ""))
                if effect_id:
                    self._apply_effect_reward(effect_id, reward, changes)
                    applied.append(dict(reward))
            elif reward_type == "story_marker_add":
                marker_id = str(reward.get("marker_id", ""))
                if marker_id:
                    markers = self.state.flags.setdefault("story_markers", [])
                    if marker_id not in markers:
                        markers.append(marker_id)
                    applied.append(dict(reward))
            elif reward_type == "victory":
                self.state.flags["victory"] = True
                self.state.flags["game_over"] = True
                changes["victory"] = True
                changes["final_kleos"] = self.state.flags.get("odyssey_kleos", 0)
                changes["epilogue"] = self._get_epilogue()
                applied.append(dict(reward))
        if applied:
            changes["rewards_applied"] = applied

    def _apply_effect_reward(self, effect_id: str, reward: dict[str, Any], changes: dict) -> None:
        duration = int(reward.get("duration_locations", 0))
        self.state.flags[f"{effect_id}_active"] = True
        if duration > 0:
            self.state.flags[f"{effect_id}_remaining"] = duration
        changes["effect"] = _effect_message(effect_id)

    def _apply_success_consequences(
        self, mission: MissionDef, result: TurnResult, changes: dict
    ) -> None:
        applied: list[dict[str, Any]] = []
        for consequence in mission.consequences:
            if not self._consequence_condition_met(consequence, result):
                continue
            consequence_type = str(consequence.get("type", ""))
            if consequence_type == "pressure_advance":
                pressure_id = str(consequence.get("pressure_id", consequence.get("pressure", "")))
                if pressure_id:
                    self._advance_pressure(pressure_id)
                    changes["special"] = _pressure_message(pressure_id)
                    applied.append(dict(consequence))
            elif consequence_type == "skill_delta":
                self._reduce_skill(str(consequence.get("skill", "")), -int(consequence.get("delta", 0)))
                applied.append(dict(consequence))
            elif consequence_type == "condition_add":
                condition = str(consequence.get("condition", ""))
                if condition and condition not in self.state.player.conditions:
                    self.state.player.conditions.append(condition)
                applied.append(dict(consequence))
        if applied:
            changes["consequences_applied"] = applied

    @staticmethod
    def _consequence_condition_met(consequence: dict[str, Any], result: TurnResult) -> bool:
        when = str(consequence.get("when", ""))
        if when == "sarissa_success":
            return bool(result.proposal and result.proposal.skill == "sarissa")
        return False

    def _advance_pressure(self, pressure_id: str) -> None:
        pressure = self.state.pressures.setdefault(pressure_id, PressureState())
        pressure.level += 1
        pressure.last_advanced_turn = self.state.turn

    def _advance_from_mission_transition(self, mission: MissionDef, changes: dict) -> None:
        next_loc = ""
        if mission.transitions:
            next_loc = str(mission.transitions[0].get("location_id", ""))
        idx = self.state.flags["odyssey_location_index"]
        if next_loc and next_loc in self.location_order:
            next_idx = self.location_order.index(next_loc)
            if next_idx != idx:
                self.state.flags["odyssey_location_index"] = next_idx
                self.state.player.location_id = next_loc
                self.state.location_id = next_loc
                self.state.flags["itaca_phase"] = 0
                changes["location_changed"] = True
                changes["new_location"] = next_loc
                changes["new_location_name"] = self.missions[next_loc].name
            return
        if self.state.flags.get("victory"):
            return
        if idx + 1 < len(self.location_order):
            next_loc = self.location_order[idx + 1]
            self.state.flags["odyssey_location_index"] = idx + 1
            self.state.player.location_id = next_loc
            self.state.location_id = next_loc
            self.state.flags["itaca_phase"] = 0
            changes["location_changed"] = True
            changes["new_location"] = next_loc
            changes["new_location_name"] = self.missions[next_loc].name
            return
        self.state.flags["victory"] = True
        self.state.flags["game_over"] = True
        changes["victory"] = True
        changes["final_kleos"] = self.state.flags.get("odyssey_kleos", 0)
        changes["epilogue"] = self._get_epilogue()

    def _apply_failure_penalty(self, mission: MissionDef, changes: dict) -> None:
        """Applica penalita di fallimento dai dati missione YAML."""
        attempts = self.state.flags["mission_attempts"]

        # Retry: difficolta -1 per il prossimo tentativo, finche il fallimento
        # non termina comunque la partita. Conserva il comportamento storico.
        self.state.flags["retry_difficulty_offset"] += 1
        changes["retry"] = "Difficolta ridotta di 1 per il prossimo tentativo."

        self._apply_failure_consequences(mission, changes)
        self._apply_failure_terminal_conditions(mission, attempts, changes)

    def _apply_failure_consequences(self, mission: MissionDef, changes: dict) -> None:
        applied: list[dict[str, Any]] = []
        penalties: list[str] = []
        for consequence in mission.consequences:
            if consequence.get("when"):
                continue
            consequence_type = str(consequence.get("type", ""))
            if consequence_type == "skill_delta":
                skill = str(consequence.get("skill", ""))
                delta = int(consequence.get("delta", 0))
                self._apply_skill_delta(skill, delta)
                penalties.append(_skill_delta_message(skill, delta))
                applied.append(dict(consequence))
            elif consequence_type == "condition_add":
                condition = str(consequence.get("condition", ""))
                if condition and condition not in self.state.player.conditions:
                    self.state.player.conditions.append(condition)
                if condition:
                    penalties.append(condition)
                applied.append(dict(consequence))
            elif consequence_type == "blood_price":
                skill = str(consequence.get("skill", ""))
                delta = int(consequence.get("delta", 0))
                self._apply_skill_delta(skill, delta)
                penalties.append(_skill_delta_message(skill, delta))
                applied.append(dict(consequence))
            elif consequence_type == "game_over":
                self.state.flags["game_over"] = True
                changes["game_over"] = True
                changes["reason"] = str(consequence.get("reason", "La partita e terminata."))
                applied.append(dict(consequence))
        if penalties:
            changes["penalty"] = "; ".join(p for p in penalties if p)
        if applied:
            changes["failure_consequences_applied"] = applied

    def _apply_failure_terminal_conditions(
        self, mission: MissionDef, attempts: int, changes: dict
    ) -> None:
        for condition in mission.failure_conditions:
            condition_type = str(condition.get("type", ""))
            if condition.get("terminal") and condition_type in {"failure", "critical_failure"}:
                self.state.flags["game_over"] = True
                changes["game_over"] = True
                changes.setdefault("reason", _terminal_failure_reason(mission.location_id))
            elif condition_type == "second_failure" and attempts >= 2:
                self.state.flags["game_over"] = True
                changes["game_over"] = True
                changes.setdefault("reason", _terminal_failure_reason(mission.location_id))

    def _apply_skill_delta(self, skill: str, delta: int) -> None:
        if not skill or delta == 0:
            return
        current = self.state.player.skills.get(skill, 0)
        self.state.player.skills[skill] = max(0, current + delta)

    def _reduce_skill(self, skill: str, amount: int) -> None:
        """Riduce permanentemente una skill del giocatore."""
        current = self.state.player.skills.get(skill, 0)
        new_val = max(0, current - amount)
        self.state.player.skills[skill] = new_val

    def _tick_effects(self) -> None:
        """Decrementa contatori temporanei."""
        if self.state.flags.get("poseidon_curse_remaining", 0) > 0:
            self.state.flags["poseidon_curse_remaining"] -= 1
            if self.state.flags["poseidon_curse_remaining"] <= 0:
                self.state.flags["poseidon_curse_active"] = False

        if self.state.flags.get("wind_bag_remaining", 0) > 0:
            self.state.flags["wind_bag_remaining"] -= 1
            if self.state.flags["wind_bag_remaining"] <= 0:
                self.state.flags["wind_bag_active"] = False

    def _get_epilogue(self) -> str:
        """Restituisce l'epilogo in base al Kleos finale."""
        kleos = self.state.flags.get("odyssey_kleos", 0)
        if kleos >= 9:
            return (
                "Il palazzo brucia ancora. Ma il fuoco e loro. "
                "Ulisse e Penelope si ricostruiscono sui resti. "
                "Le Proche sono cenere. Il mare e calmo. "
                "Telemaca torna tre giorni dopo. Trova i genitori "
                "seduti sulle rovine, mano nella mano, in silenzio. "
                "Non serve parlare. Vent'anni si cancellano in un tocco."
            )
        elif kleos >= 7:
            return (
                "Itaca e libera, ma le cicatrici sono profonde. "
                "Penelope non riconosce piu la donna che e tornata. "
                "Ulisse ha ucciso troppo facilmente. Ha guardato Antinoo "
                "morire con gli stessi occhi che usava a Troia. "
                "Il letto d'ulivo e intatto. Ma il sonno, quello, "
                "non torna piu."
            )
        else:
            return (
                "Vittoria di Pirro. Il palazzo brucia ancora. "
                "Il trono e vuoto. Il mare attende il prossimo naufragio. "
                "Penelope e vivo, ma non lo guarda piu. "
                "Ulisse ha vinto la guerra. Ha perso la pace."
            )

    # -- speciali -------------------------------------------------------------

    def give_moly(self) -> None:
        """Ermete dona la pianta di moly."""
        self.state.flags["moly_possessed"] = True

    def check_calipso_auto_pass(self) -> bool:
        """Verifica se Ulisse puo auto-passare Calipso."""
        kleos = self.state.flags.get("odyssey_kleos", 0)
        if kleos >= 4:
            self.state.flags["calipso_auto_pass"] = True
            return True
        return False

    def activate_tiresia_prophecy(self) -> dict[str, Any]:
        """Attiva la profezia di Tiresia."""
        if not self.state.flags.get("tiresia_prophecy", False):
            return {"error": "Non hai ancora ottenuto il passaggio per l'Ade."}
        if self.state.flags.get("tiresia_used", False):
            return {"error": "Hai gia usato la profezia di Tiresia."}

        self.state.flags["tiresia_used"] = True
        self._reduce_skill("sarissa", 1)

        idx = self.state.flags["odyssey_location_index"]
        future = []
        for i in range(idx + 1, min(idx + 3, len(self.location_order))):
            loc = self.location_order[i]
            future.append({
                "location": loc,
                "name": self.missions[loc].name,
                "difficulty": self.missions[loc].difficulty,
            })

        return {
            "message": "Tiresia beve il tuo sangue e parla. Vedi il futuro.",
            "blood_price": "-1 Sarissa permanente",
            "future_locations": future,
        }

    # -- stato completo -------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Restituisce lo stato completo del tracker."""
        loc_id = self.current_location_id()
        mission = self.missions[loc_id]
        can_attempt, block_reason = self.can_attempt_mission()

        # Calcola difficolta effettiva (con retry offset)
        effective_diff = max(1, mission.difficulty - self.state.flags.get("retry_difficulty_offset", 0))

        # Info skill usata nel turno precedente
        last_skill = self.state.flags.get("last_skill_used", "")
        last_relevant = self.state.flags.get("last_skill_relevant", False)

        # Skill richieste ORA (a Itaca dipendono dalla fase)
        required = self.required_skills()
        itaca_phase = self.state.flags.get("itaca_phase", 0)

        return {
            "location_id": loc_id,
            "location_name": mission.name,
            "mission_description": mission.description,
            "mission_skill": required[0],
            "mission_alt_skill": required[1] if len(required) > 1 else None,
            "mission_target": mission.required_target,
            "mission_difficulty": mission.difficulty,
            "effective_difficulty": effective_diff,
            "retry_offset": self.state.flags.get("retry_difficulty_offset", 0),
            "itaca_phase": itaca_phase if loc_id == "loc_itaca" else None,
            "itaca_phase_name": self.ITACA_PHASE_NAMES[min(itaca_phase, 2)] if loc_id == "loc_itaca" else None,
            "action_history": list(self.state.flags.get("action_history", [])),
            "kleos": self.get_kleos(),
            "intuition": self.get_intuition(),
            "emotional_state": self.get_emotional_state(),
            "can_attempt": can_attempt,
            "block_reason": block_reason,
            "turns_without_progress": self.state.flags.get("turns_without_progress", 0),
            "mission_attempts": self.state.flags.get("mission_attempts", 0),
            "last_skill_used": last_skill,
            "last_skill_relevant": last_relevant,
            "game_over": self.is_game_over(),
            "victory": self.is_victory(),
            "active_effects": {
                "poseidon_curse": self.state.flags.get("poseidon_curse_active", False),
                "wind_bag": self.state.flags.get("wind_bag_active", False),
                "moly": self.state.flags.get("moly_possessed", False),
                "phaeacian_ship": self.state.flags.get("phaeacian_ship", False),
            },
        }
