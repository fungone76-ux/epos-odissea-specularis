"""Odyssey Demo GameMaster."""

from __future__ import annotations

import re
from typing import Any

from epos.contract import CheckProposal, FinalScene, GmPhaseResponse
from epos.gm import DemoGameMaster
from epos.models import WorldState
from epos.worldpack import WorldPack

from .odyssey_mission_tracker import location_order_from_pack, missions_from_pack


# Parole che indicano azione rischiosa (coniugazioni comuni incluse)
_ACTION_WORDS = (
    "tento", "tenti", "tenta", "tentiamo", "tentate", "tentano",
    "provo", "provi", "prova", "proviamo", "provate", "provano",
    "cerco", "cerchi", "cerca", "cerchiamo", "cercate", "cercano",
    "mi avvicino", "mi avvicini", "si avvicina",
    "mi intrufolo", "sgattaiolo",
    "forzo", "forzi", "forza", "forziamo", "forzate", "forzano",
    "scasso", "scassi", "scassiamo", "scassate", "scassano",
    "inseguo", "insegui", "insegue", "inseguiamo", "inseguite", "inseguono",
    "attacco", "attacchi", "attacca", "attacchiamo", "attaccate", "attaccano",
    "colpisco", "colpisci", "colpisce", "colpiamo", "colpite", "colpiscono",
    "rubo", "rubi", "ruba", "rubiamo", "rubate", "rubano",
    "nascondo", "nascondi", "nasconde", "nascondiamo", "nascondete", "nascondono",
    "mi nascondo", "mi nascondi", "si nasconde",
    "seduco", "seduci", "seduce", "seduciamo", "seducete", "seducono",
    "minaccio", "minacci", "minaccia", "minacciamo", "minacciate", "minacciano",
    "inganno", "inganni", "inganna", "inganniamo", "ingannate", "ingannano",
    "mento", "menti", "mente", "mentiamo", "mentite", "mentono",
    "uso", "usi", "usa", "usiamo", "usate", "usano",
    "mi concentro", "ti concentri", "si concentra",
    "resisto", "resisti", "resiste", "resistiamo", "resistete", "resistono",
    "sopporto", "sopporti", "sopporta", "sopportiamo", "sopportate", "sopportano",
    "navigo", "navighi", "naviga", "navighiamo", "navigate", "navigano",
    "attraverso", "attraversi", "attraversa", "attraversiamo", "attraversate", "attraversano",
    "acceco", "accechi", "acceca", "accechiamo", "accechete", "accecano",
    "uccido", "uccidi", "uccide", "uccidiamo", "uccidete", "uccidono",
    "fingo", "fingi", "finge", "fingiamo", "fingete", "fingono",
    "travesto", "travesti", "traveste", "travestiamo", "travestite", "travestono",
    "tendo", "tendi", "tende", "tendiamo", "tendete", "tendono",
    "tiro", "tiri", "tira", "tiramo", "tirate", "tirano",
    "scaglio", "scagli", "scaglia", "scagliamo", "scagliate", "scagliano",
    "offro", "offri", "offre", "offriamo", "offrite", "offrono",
    "bevo", "bevi", "beve", "beviamo", "bevete", "bevono",
    "mangio", "mangi", "mangia", "mangiamo", "mangiate", "mangiano",
    "tocco", "tocchi", "tocca", "tocchiamo", "tocchete", "toccano",
    "apro", "apri", "apre", "apriamo", "aprite", "aprono",
    "stringo", "stringi", "stringe", "stringiamo", "stringete", "stringono",
    "lascio", "lasci", "lascia", "lasciamo", "lasciate", "lasciano",
    "prendo", "prendi", "prende", "prendiamo", "prendete", "prendono",
    "dico", "dici", "dice", "diciamo", "dicete", "dicono",
    "parlo", "parli", "parla", "parliamo", "parlate", "parlano",
    "entro", "entri", "entra", "entriamo", "entrate", "entrano",
    "esco", "esci", "esce", "usciamo", "uscite", "escono",
    "fuggo", "fuggi", "fugge", "fuggiamo", "fuggete", "fuggono",
    "corro", "corri", "corre", "corriamo", "correte", "corrono",
    "salto", "salti", "salta", "saltiamo", "saltate", "saltano",
    "cado", "cadi", "cade", "cadiamo", "cadete", "cadono",
    "rialzo", "rialzi", "rialza", "rialziamo", "rialzate", "rialzano",
    "grido", "grida", "gridiamo", "gridate", "gridano",
    "sussurro", "sussurri", "sussurra", "sussurriamo", "sussurrate", "sussurrano",
    "chiamo", "chiami", "chiama", "chiamiamo", "chiamate", "chiamano",
    "invoco", "invochi", "invoca", "invochiamo", "invocate", "invocano",
    "prego", "preghi", "prega", "preghiamo", "pregate", "pregano",
)

_SKILL_KEYWORDS = {
    "sarissa": (
        "attacco", "attacchi", "attacca", "attacchiamo", "attaccate", "attaccano",
        "colpisco", "colpisci", "colpisce", "colpiamo", "colpite", "colpiscono",
        "forzo", "forzi", "forza", "forziamo", "forzate", "forzano",
        "inseguo", "insegui", "insegue", "inseguiamo", "inseguite", "inseguono",
        "sollevo", "sollevi", "solleva", "solleviamo", "sollevate", "sollevano",
        "spingo", "spingi", "spinge", "spingiamo", "spingete", "spingono",
        "arco", "frecce", "freccia", "uccido", "uccidi", "uccide", "uccidiamo", "uccidete", "uccidono",
        "acceco", "accechi", "acceca", "accechiamo", "accechete", "accecano",
        "pugnale", "lotta", "combattimento", "violenza", "palo", "olivo", "fuoco", "brucio", "bruci", "brucia",
        "colpire", "assalto", "fendente", "tiro", "tiri", "tira", "scaglio", "scagli", "scaglia",
        "trafiggo", "trafiggi", "trafigge", "colpo", "spada", "lancia", "mazza", "bastone", "daga",
    ),
    "dolos": (
        "inganno", "inganni", "inganna", "inganniamo", "ingannate", "ingannano",
        "mento", "menti", "mente", "mentiamo", "mentite", "mentono",
        "truffa", "truffo", "truffi", "truffiamo", "truffate", "truffano",
        "travestimento", "travesto", "travesti", "traveste", "travestiamo", "travestite", "travestono",
        "nascondo", "nascondi", "nasconde", "nascondiamo", "nascondete", "nascondono",
        "fingo", "fingi", "finge", "fingiamo", "fingete", "fingono",
        "simulo", "simuli", "simula", "simuliamo", "simulate", "simulano",
        "parlo", "parli", "parla", "parliamo", "parlate", "parlano",
        "dico", "dici", "dice", "diciamo", "dicete", "dicono",
        "chiedo", "chiedi", "chiede", "chiediamo", "chiedete", "chiedono",
        "persuado", "persuadi", "persuade", "persuadiamo", "persuadete", "persuadono",
        "seduco", "seduci", "seduce", "seduciamo", "seducete", "seducono",
        "minaccio", "minacci", "minaccia", "minacciamo", "minacciate", "minacciano",
        "storia", "bugia", "bugie", "falso", "falsa", "nome", "nessuno",
        "fingere", "simulare", "travestire", "mendicante", "mendico", "mendica",
        "bugiarda", "bugiardo", "fingi", "simuli", "travesti",
        "offro", "offri", "offre", "offriamo", "offrite", "offrono",
        "propongo", "proponi", "propone", "proponiamo", "proponete", "propongono",
        "suggerisco", "suggerisci", "suggerisce", "suggeriamo", "suggerite", "suggeriscono",
        "consiglio", "consigli", "consiglia", "consigliamo", "consigliate", "consigliano",
        "negozio", "negozi", "negozia", "negoziamo", "negoziate", "negoziano",
    ),
    "eros": (
        "seduco", "seduci", "seduce", "seduciamo", "seducete", "seducono",
        "bacio", "baci", "bacia", "baciamo", "baciate", "baciano",
        "tocco", "tocchi", "tocca", "tocchiamo", "tocchete", "toccano",
        "abbraccio", "abbracci", "abbraccia", "abbracciamo", "abbracciate", "abbracciano",
        "desiderio", "desideri", "desidera", "desideriamo", "desiderate", "desiderano",
        "piacere", "piaci", "piace", "piacciamo", "piacete", "piacciono",
        "letto", "amplesso", "carnale", "corpo", "bellezza", "tentazione",
        "sedurre", "baciare", "toccare", "abbracciare", "desiderare",
        "abbracci", "baci", "carezza", "carezze", "nudo", "nuda",
        "spoglio", "spoglia", "spogli", "spogliamo", "spogliate", "spogliano",
        "tentare", "tento", "tenti", "tenta", "tentiamo", "tentate", "tentano",
    ),
    "thumos": (
        "resisto", "resisti", "resiste", "resistiamo", "resistete", "resistono",
        "resistenza", "volonta", "coraggio", "pazienza",
        "diguno", "digiuno", "digiuni", "digiuna", "digiuniamo", "digiunate", "digiunano",
        "sopporto", "sopporti", "sopporta", "sopportiamo", "sopportate", "sopportano",
        "non cedo", "non cedi", "non cede", "non cediamo", "non cedete", "non cedono",
        "ricordo", "ricordi", "ricorda", "ricordiamo", "ricordate", "ricordano",
        "memoria", "fede", "fedelta", "resistere", "sopportare",
        "aspetto", "aspetti", "aspetta", "aspettiamo", "aspettate", "aspettano",
        "non apro", "non apri", "non apre", "non apriamo", "non aprite", "non aprono",
        "non tocco", "non tocchi", "non tocca", "non tocchiamo", "non toccate", "non toccano",
        "non mangio", "non mangi", "non mangia", "non mangiamo", "non mangiate", "non mangiano",
        "non bevo", "non bevi", "non beve", "non beviamo", "non bevete", "non bevono",
        "non dimentico", "non dimentichi", "non dimentica", "non dimentichiamo", "non dimenticate", "non dimenticano",
        "paziente", "calma", "calmo", "freddo", "testa", "mente",
        "concentrazione", "meditare", "medito", "mediti", "medita", "meditiamo", "meditate", "meditano",
        "pregare", "prego", "preghi", "prega", "preghiamo", "pregate", "pregano",
    ),
    "pontos": (
        "navigo", "navighi", "naviga", "navighiamo", "navigate", "navigano",
        "timone", "vela", "mare", "nave", "porto",
        "attraverso", "attraversi", "attraversa", "attraversiamo", "attraversate", "attraversano",
        "passaggio", "stretto", "vortice", "tempesta", "vento",
        "navigare", "timoniere", "veliero", "attraversare",
        "superare", "supero", "superi", "supera", "superiamo", "superate", "superano",
        "oltrepassare", "oltrepasso", "oltrepassi", "oltrepassa", "oltrepassiamo", "oltrepassate", "oltrepassano",
        "passare", "passo", "passi", "passa", "passiamo", "passate", "passano",
        "remo", "remi", "rema", "remiamo", "remate", "remano",
        "remare", "galleggiare", "galleggio", "galleggi", "galleggia", "galleggiamo", "galleggiate", "galleggiano",
        "affondare", "affondo", "affondi", "affonda", "affondiamo", "affondate", "affondano",
    ),
}


class OdysseyDemoGameMaster(DemoGameMaster):
    """GM demo per Odissea Specularis."""

    @staticmethod
    def _has_word(text: str, words) -> bool:
        """Verifica se il testo contiene almeno una delle parole.
        
        Usa word boundary per parole senza accenti, ma per parole con accenti
        (come volonta, fedelta) usa un match piu flessibile.
        """
        lowered = text.lower()
        for w in words:
            w_lower = w.lower()
            # Se la parola ha accenti, non usare word boundary
            if any(c in w_lower for c in "àèéìòù"):
                if w_lower in lowered:
                    return True
            else:
                if re.search(rf"\b{re.escape(w_lower)}\b", lowered):
                    return True
        return False

    def propose(self, state: WorldState, pack: WorldPack, player_text: str) -> GmPhaseResponse:
        text = player_text.lower()

        missions = missions_from_pack(pack)
        location_order = location_order_from_pack(pack)
        loc_idx = state.flags.get("odyssey_location_index", 0)
        if loc_idx >= len(location_order):
            # Vittoria: nessuna prova, solo scena narrativa
            scene = self._fallback_scene(state, pack, player_text)
            return GmPhaseResponse(mode="no_check", scene=scene)

        loc_id = location_order[loc_idx]
        mission = missions[loc_id]

        if self._has_word(text, _ACTION_WORDS):
            # Determina quale skill ha usato il giocatore
            matched_skills = []
            for sk, hints in _SKILL_KEYWORDS.items():
                if self._has_word(text, hints):
                    matched_skills.append(sk)

            wrong_skill_hint = ""

            # Se il giocatore non ha matchato nessuna skill, usa la primary della missione
            if not matched_skills:
                skill = mission.primary_skill
            else:
                # Se il giocatore ha matchato piu skill, scegli quella piu pertinente
                # alla missione attuale
                if mission.primary_skill in matched_skills:
                    skill = mission.primary_skill
                elif mission.alternative_skill and mission.alternative_skill in matched_skills:
                    skill = mission.alternative_skill
                else:
                    # Il giocatore ha usato skill NON rilevanti per la missione:
                    # redirigi sulla skill della missione e spiega perche.
                    required = mission.primary_skill.upper()
                    if mission.alternative_skill:
                        required += f" o {mission.alternative_skill.upper()}"
                    used = ", ".join(s.upper() for s in matched_skills)
                    wrong_skill_hint = (
                        f"Le tue parole suggeriscono {used}, ma qui non serve: "
                        f"questa prova richiede {required}. "
                    )
                    skill = mission.primary_skill

            # Difficolta della missione (con retry offset)
            difficulty = max(1, mission.difficulty - state.flags.get("retry_difficulty_offset", 0))

            # Special: Poseidon's Curse (+1 diff a Pontos)
            if (state.flags.get("poseidon_curse_active", False)
                and skill == "pontos"):
                difficulty += 1

            # Special: Wind Bag (+1 pool Pontos, applicato come -1 difficolta:
            # il GM non puo modificare il pool, l'effetto sul tiro e equivalente)
            if (state.flags.get("wind_bag_active", False)
                and skill == "pontos"):
                difficulty = max(1, difficulty - 1)

            # Special: Moly a Circe
            if loc_id == "loc_circe" and state.flags.get("moly_possessed", False):
                if self._has_word(text, ("moly", "pianta", "ermete", "antidoto")):
                    difficulty = max(1, difficulty - 2)

            # Special: Calipso auto-pass
            if loc_id == "loc_calipso" and state.flags.get("calipso_auto_pass", False):
                if self._has_word(text, ("ricordo", "penelope", "itaca", "casa", "telaio")):
                    difficulty = 0  # auto-success

            # Special: Itaca a 3 fasi
            if loc_id == "loc_itaca":
                itaca_phase = state.flags.get("itaca_phase", 0)
                if itaca_phase == 0:
                    skill = "dolos"
                    # Nave Feacia = auto-pass primo tiro
                    if state.flags.get("phaeacian_ship", False):
                        difficulty = 0
                elif itaca_phase == 1:
                    skill = "sarissa"
                elif itaca_phase == 2:
                    skill = "eros"
                # L'hint deve citare la skill della fase corrente, non la primary
                if wrong_skill_hint:
                    used = wrong_skill_hint.split("suggeriscono ")[1].split(",")[0]
                    wrong_skill_hint = (
                        f"Le tue parole suggeriscono {used}, ma questa fase "
                        f"richiede {skill.upper()}. "
                    )

            present = state.present_npc_ids()
            target = present[:1] if present else []

            stakes = {
                "full_success": mission.victory_reward,
                "partial_success": f"Riesci, ma con un costo. {mission.victory_reward}",
                "failure": mission.failure_penalty,
                "critical_failure": f"Disastro. {mission.failure_penalty}",
            }

            proposal = CheckProposal(
                action_kind=skill,
                skill=skill,
                difficulty=difficulty,
                target_ids=target,
                opposition="npc_resistance" if present else "environment",
                reason=f"{wrong_skill_hint}Missione: {mission.name}. {mission.description}",
                stakes=stakes,
            )
            return GmPhaseResponse(mode="check_proposal", check=proposal)

        # Nessuna azione rischiosa: scena narrativa
        scene = self._fallback_scene(state, pack, player_text)
        return GmPhaseResponse(mode="no_check", scene=scene)

    def _fallback_scene(self, state: WorldState, pack: WorldPack, player_text: str) -> Any:
        """Scena di fallback per azioni narrative (no_check)."""
        location_order = location_order_from_pack(pack)
        loc_idx = state.flags.get("odyssey_location_index", 0)
        loc_id = location_order[loc_idx] if loc_idx < len(location_order) else location_order[-1]
        location = pack.locations.get(loc_id)
        location_name = location.name if location else loc_id
        present = state.present_npc_ids()

        scene_dict = {
            "narration": f"Nella quiete di {location_name}, il tuo gesto non passa inosservato. {player_text.strip()}",
            "dialogue": [],
            "npc_actions": [{"npc_id": npc_id, "action": "osserva il giocatore"} for npc_id in present],
            "intentions": [{"npc_id": npc_id, "intention": "valutare le intenzioni"} for npc_id in present],
            "mutations": [],
            "memory_events": [{"summary": f"Osservazione a {location_name}", "witnesses": present, "level": "immediate", "emotional_impact": 0, "public": True}] if present else [],
            "visual": {
                "summary": f"{location_name} — osservazione",
                "focus_character": present[0] if present else "player",
                "visible_characters": [present[0]] if present else ["player"],
                "shared_action": False,
                "moment_type": "reaction",
                "speaker_character": "",
                "actor_character": "",
                "reactor_character": present[0] if present else "player",
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": [],
                "visual_en": f"ancient Greek {location_name}, quiet observation scene, cinematic",
                "tags_en": ["mythological", "adult", "observation"],
            },
        }
        return FinalScene.from_dict(scene_dict)

    def narrate(self, state: WorldState, pack: WorldPack, player_text: str,
                proposal: Any, roll: Any, stake: str, extras: dict[str, Any] | None = None) -> Any:
        from epos.contract import FinalScene

        location_order = location_order_from_pack(pack)
        loc_idx = state.flags.get("odyssey_location_index", 0)
        loc_id = location_order[loc_idx] if loc_idx < len(location_order) else location_order[-1]
        location = pack.locations.get(loc_id)
        location_name = location.name if location else loc_id
        present = state.present_npc_ids()
        outcome = roll.outcome.value if roll else "no_check"
        skill = proposal.skill if proposal else ""
        choice = extras.get("choice", "roll") if extras else "roll"

        narration_parts = []

        # Narrazione differenziata per skill e esito
        if outcome in ("full_success", "partial_success"):
            if loc_id == "loc_ciclopi":
                if skill == "sarissa":
                    narration_parts.append(
                        "Affondi il palo di olivo arroventato nell'occhio unico di Polifemo. "
                        "L'urlo sveglia le montagne. Il sangue e il latte si mescolano sul pavimento della caverna. "
                        "Tu corri tra le pecore in fuga, accecata dalla furia del gigante."
                    )
                else:  # dolos
                    narration_parts.append(
                        "Polifemo crolla ubriaca. 'Nessuno... buono...' russare. "
                        "Tu prendi il palo di olivo dal fuoco. L'accechi mentre dorme. "
                        "L'urlo sveglia le pecore. Fuggi. La caverna sputa sangue e latte acido dietro di te."
                    )
            elif loc_id == "loc_eolo":
                narration_parts.append(
                    "La pelle di cinghiale resta chiusa. I venti dormono. "
                    "Eolo annuisce, quasi deluso. 'Forse sei diversa dalle altre.'"
                )
            elif loc_id == "loc_sirene":
                if skill == "eros":
                    narration_parts.append(
                        "Seduci le Sirene prima che ti seducano. Le tue parole sono piu dolci del loro canto. "
                        "Ti lasciano passare, confuse e affamate."
                    )
                else:  # thumos
                    narration_parts.append(
                        "Il canto si spezza. Le voci maschili diventano grida di rabbia. "
                        "Tu passi, legata all'albero maestro, sorda e viva."
                    )
            elif loc_id == "loc_scilla_cariddi":
                if skill == "pontos":
                    narration_parts.append(
                        "La nave passa. Scilla afferra aria. Cariddi inghiotte schiuma. "
                        "Sei sanguinante, ma intera. Il mare ti ha lasciata andare."
                    )
                else:  # sarissa
                    narration_parts.append(
                        "Scilla afferra la tua gamba. Tu tagli la testa del mostro con il pugnale. "
                        "Il sangue nero schizza. La nave passa, ferita ma intera."
                    )
            elif loc_id == "loc_circe":
                if skill == "eros":
                    narration_parts.append(
                        "Usi il sesso come arma. Circe crolla sotto di te, sorpreso dalla tua forza. "
                        "Ottieni il rituale per l'Ade."
                    )
                else:  # thumos
                    narration_parts.append(
                        "Circe indietreggia. Il moly brucia la sua magia. "
                        "'Nessuno ha mai resistito,' sussurra. Tu ottieni il rituale."
                    )
            elif loc_id == "loc_cimmeri":
                narration_parts.append(
                    "Le ombre bevono il tuo sangue e parlano. Tiresia emerge. "
                    "'La strada passa per il letto,' dice. 'Per il letto d'ulivo.'"
                )
            elif loc_id == "loc_calipso":
                narration_parts.append(
                    "Calipso piange. 'Vattene,' dice. 'Ma ricordami.' "
                    "La grotta di cedro si apre. Il mare ti aspetta."
                )
            elif loc_id == "loc_sole":
                narration_parts.append(
                    "Le vacche dorate pascolano indifferenti. Tu digiuni. "
                    "Zeus non scaglia la folgore. Hai vinto contro te stessa."
                )
            elif loc_id == "loc_scheria":
                if skill == "dolos":
                    narration_parts.append(
                        "Arete annuisce. 'Una storia degna di un re,' dice. "
                        "La nave feacia ti aspetta. Itaca e a un respiro."
                    )
                else:  # eros
                    narration_parts.append(
                        "Seduci la corte dei Feaci. Arete ti abbraccia come una figlia. "
                        "La nave feacia ti aspetta."
                    )
            elif loc_id == "loc_itaca":
                itaca_phase = state.flags.get("itaca_phase", 0)
                if itaca_phase == 0:
                    narration_parts.append(
                        "Il travestimento da mendicante funziona. Nessuna Proca ti riconosce. "
                        "Entri nel palazzo come un'ombra."
                    )
                elif itaca_phase == 1:
                    narration_parts.append(
                        "L'arco canta. La freccia vola attraverso le dodici asce. "
                        "Antinoo cade. Eurimaco cade. Le Proche cadono."
                    )
                else:  # itaca_phase == 2
                    narration_parts.append(
                        "Penelope ti riconosce nel letto d'ulivo. Vent'anni si cancellano. "
                        "Itaca e salva."
                    )
        elif outcome in ("failure", "critical_failure"):
            if loc_id == "loc_ciclopi":
                if skill == "sarissa":
                    narration_parts.append(
                        "Il palo scivola. Polifemo ti afferra. L'occhio unico ti guarda da troppo vicino. "
                        "Il suo alito sa di latte acido e morte."
                    )
                else:
                    narration_parts.append(
                        "Polifemo non crede alla tua bugia. 'Nessuno non esiste,' grugnisce. "
                        "Ti afferra. L'occhio unico ti guarda da troppo vicino."
                    )
            elif loc_id == "loc_eolo":
                narration_parts.append(
                    "La pelle si apre. I venti esplodono. La nave si schianta. "
                    "Sei sola, di nuovo, su un relitto che affonda."
                )
            elif loc_id == "loc_sirene":
                narration_parts.append(
                    "Il canto ti entra nelle ossa. Ti slacci le cinghie. "
                    "Il mare ti chiama. Gli scogli ti aspettano."
                )
            elif loc_id == "loc_scilla_cariddi":
                narration_parts.append(
                    "Cariddi inghiotte la nave. Scilla afferra la tua gamba. "
                    "Il sangue nero del mostro si mescola al tuo."
                )
            elif loc_id == "loc_circe":
                narration_parts.append(
                    "Il vino brucia. Le dita di Circe ti trasformano. "
                    "Stai diventando una bestia. La mente si dissolve."
                )
            elif loc_id == "loc_cimmeri":
                narration_parts.append(
                    "Le ombre affamate ti sommergono. Tiresia non parla. "
                    "Il sangue non basta. Non basta mai."
                )
            elif loc_id == "loc_calipso":
                narration_parts.append(
                    "Calipso sorride. 'Hai dimenticato,' dice. 'Itaca e un nome. "
                    "Solo un nome.' E ha ragione. Non ricordi piu."
                )
            elif loc_id == "loc_sole":
                narration_parts.append(
                    "La carne divina brucia la lingua. Zeus colpisce. "
                    "Il cielo si spacca. Il mare diventa fuoco."
                )
            elif loc_id == "loc_scheria":
                narration_parts.append(
                    "Arete scuote la testa. 'Una bugia,' dice. 'Cacciatela.' "
                    "I Feaci ti cacciano. Itaca resta lontana."
                )
            elif loc_id == "loc_itaca":
                itaca_phase = state.flags.get("itaca_phase", 0)
                if itaca_phase == 0:
                    narration_parts.append(
                        "Il travestimento fallisce. Una Proca ti riconosce. "
                        "'E quella!' grida. Le altre si alzano."
                    )
                elif itaca_phase == 1:
                    narration_parts.append(
                        "L'arco non tende. Antinoo ride. Le Proche ti sommergono. "
                        "Itaca era un sogno. Solo un sogno."
                    )
                else:
                    narration_parts.append(
                        "Penelope non ti riconosce. 'Non sei lui,' dice. "
                        "Le Proche ti cacciano. Itaca e perduta."
                    )
        else:
            narration_parts.append(f"Nella quiete di {location_name}, il tuo gesto non passa inosservato.")

        # Aggiungi nota per scelta safe vs roll
        if choice == "safe" and outcome in ("full_success", "partial_success"):
            narration_parts.append(
                "Hai agito con cautela, senza rischiare. Il successo e certo, ma il cuore non batte forte."
            )
        elif choice == "safe" and outcome in ("failure", "critical_failure"):
            narration_parts.append(
                "Anche la cautela non basta. A volte il destino non rispetta le scelte sicure."
            )

        # Dialoghi NPC per tutti i personaggi
        dialogue = []
        if present:
            npc = state.npcs[present[0]]
            npc_id = npc.id
            if outcome in ("full_success", "partial_success"):
                if npc_id == "polifemo":
                    dialogue.append({"speaker": npc.name, "text": "Nessuno... mi hai accecato... Nessuno..."})
                elif npc_id == "eolo":
                    dialogue.append({"speaker": npc.name, "text": "Tieni i venti. E non aprire mai."})
                elif npc_id == "circe":
                    dialogue.append({"speaker": npc.name, "text": "Vattene. Ma torna. Un giorno, torna."})
                elif npc_id == "tiresia":
                    dialogue.append({"speaker": npc.name, "text": "Il letto d'ulivo. Ricordalo."})
                elif npc_id == "calipso":
                    dialogue.append({"speaker": npc.name, "text": "Vattene. Ma ricordami."})
                elif npc_id == "arete":
                    dialogue.append({"speaker": npc.name, "text": "Una storia degna di un re."})
                elif npc_id == "penelope":
                    dialogue.append({"speaker": npc.name, "text": "Il letto... non si puo spostare..."})
            else:
                # Fallimento
                if npc_id == "polifemo":
                    dialogue.append({"speaker": npc.name, "text": "Piccola. Ti mangio."})
                elif npc_id == "circe":
                    dialogue.append({"speaker": npc.name, "text": "Un'altra bestia per il mio giardino."})
                elif npc_id == "calipso":
                    dialogue.append({"speaker": npc.name, "text": "Resta. Per sempre."})
                elif npc_id == "arete":
                    dialogue.append({"speaker": npc.name, "text": "Cacciatela."})

        # Determina se la scena e intima (multipersonaggio) o no (monopersonaggio)
        # Regola: multipersonaggio SOLO con interazione intima/fisica reale
        is_intimate = False
        if loc_id == "loc_circe" and skill == "eros":
            is_intimate = True  # Sesso come arma, contatto fisico reale
        elif loc_id == "loc_calipso":
            is_intimate = True  # Sette anni di prigionia, sesso, abbracci
        elif loc_id == "loc_itaca" and skill == "eros":
            is_intimate = True  # Riconoscimento nel letto d'ulivo
        elif loc_id == "loc_scheria" and skill == "eros":
            is_intimate = True  # Arete abbraccia

        if is_intimate:
            # Multipersonaggio: entrambi visibili
            focus_char = present[0] if present else "player"
            visible_chars = present + ["player"] if present else ["player"]
            moment_type = "intimate"
            actor_char = "player"
            reactor_char = ""
            intimate_shared_moment = len(visible_chars) > 1
            multi_character_reason = "explicit_intimate_physical_contact"
            multi_character_participants = visible_chars
        else:
            # Monopersonaggio: il frame mostra l'azione materiale del player.
            focus_char = "player"
            visible_chars = ["player"]
            moment_type = "action"
            actor_char = "player"
            reactor_char = ""
            intimate_shared_moment = False
            multi_character_reason = ""
            multi_character_participants = []

        scene_dict = {
            "narration": " ".join(narration_parts),
            "dialogue": dialogue,
            "npc_actions": [{"npc_id": npc_id, "action": "reagisce alla scena"} for npc_id in present],
            "intentions": [{"npc_id": npc_id, "intention": "valutare le conseguenze"} for npc_id in present],
            "mutations": [],
            "memory_events": [{"summary": f"Turno a {location_name}: {outcome} ({skill})", "witnesses": present, "level": "immediate", "emotional_impact": 0, "public": True}] if present else [],
            "visual": {
                "summary": f"{location_name} — {outcome}",
                "focus_character": focus_char,
                "visible_characters": visible_chars,
                "shared_action": is_intimate,
                "moment_type": moment_type,
                "speaker_character": "",
                "actor_character": actor_char,
                "reactor_character": reactor_char,
                "intimate_shared_moment": intimate_shared_moment,
                "multi_character_reason": multi_character_reason,
                "multi_character_participants": multi_character_participants,
                "visual_en": f"ancient Greek {location_name}, Bronze Age, {outcome} scene, cinematic",
                "tags_en": ["mythological", "adult", "dramatic"],
            },
        }
        return FinalScene.from_dict(scene_dict)
