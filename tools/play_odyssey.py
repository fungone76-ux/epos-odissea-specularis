#!/usr/bin/env python3
"""Launcher interattivo per Odissea Specularis.

Gioca da terminale attraverso le 10 location, tira i dadi,
gestisci le scelte e le meccaniche speciali.
"""

import sys
from pathlib import Path

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from epos.odyssey_engine import OdysseyEngine, MISSIONS


def print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_status(engine: OdysseyEngine) -> None:
    status = engine.game_status()
    print(f"\n  [Turno {status['turn']}]  Kleos: {status['player']['kleos']}")
    print(f"  Location: {status['location']['name']}")
    print(f"  Skills: Sarissa={status['player']['skills'].get('sarissa',0)} | "
          f"Dolos={status['player']['skills'].get('dolos',0)} | "
          f"Eros={status['player']['skills'].get('eros',0)} | "
          f"Thumos={status['player']['skills'].get('thumos',0)} | "
          f"Pontos={status['player']['skills'].get('pontos',0)}")
    effects = status['active_effects']
    active = [k for k, v in effects.items() if v]
    if active:
        print(f"  Effetti attivi: {', '.join(active)}")
    print()


def get_choice(prompt: str, options: list[str]) -> str:
    while True:
        print(f"\n{prompt}")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        choice = input("\n> ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        if choice in options:
            return choice
        print("Scelta non valida. Riprova.")


def main() -> None:
    print_header("ODISSEA SPECULARIS")
    print("Una rilettura adulta e speculare dell'Odissea di Omero.")
    print("Ulisse è donna. I mostri sono donne. I maghi sono uomini.")
    print("Le divinità mantengono il loro sesso canonico.")
    print("Tono: viscerale, erotico, brutale, politico.")
    print("\nPremi INVIO per iniziare...")
    input()

    pack_dir = Path(__file__).parent.parent / "worlds" / "odyssey_specularis"
    engine = OdysseyEngine(pack_dir)

    print_header("PROLOGO")
    print(engine.pack.opening_narration)
    input("\n[INVIO per continuare]")

    while not engine.state.flags.get("game_over", False):
        engine.next_turn()
        loc_id = engine.current_location_id()
        mission = MISSIONS[loc_id]

        print_header(f"LOCATION: {mission.name.upper()}")
        print(mission.description)
        print_status(engine)

        # Mostra opzioni
        options = []
        skill_choices = {}

        # Skill primaria
        p_skill = mission.primary_skill
        p_rating = engine.state.player.skill_rating(p_skill)
        options.append(f"Usa {p_skill.upper()} (rating {p_rating})")
        skill_choices[f"Usa {p_skill.upper()} (rating {p_rating})"] = p_skill

        # Skill alternativa
        if mission.alternative_skill:
            a_skill = mission.alternative_skill
            a_rating = engine.state.player.skill_rating(a_skill)
            options.append(f"Usa {a_skill.upper()} (rating {a_rating})")
            skill_choices[f"Usa {a_skill.upper()} (rating {a_rating})"] = a_skill

        # Scelta sicura
        options.append("Scegli esito sicuro (senza tiro)")
        skill_choices["Scegli esito sicuro (senza tiro)"] = "safe"

        # Special: Moly a Circe
        use_moly = False
        if loc_id == "loc_circe" and engine.state.flags.get("moly_possessed", False):
            options.append("Usa la pianta di MOLY (riduce difficoltà)")
            skill_choices["Usa la pianta di MOLY (riduce difficoltà)"] = "moly"

        # Special: Auto-pass Calipso
        use_auto = False
        if loc_id == "loc_calipso":
            if engine.check_calipso_auto_pass():
                options.append("RICORDA PENELOPE (auto-pass con Kleos >= 4)")
                skill_choices["RICORDA PENELOPE (auto-pass con Kleos >= 4)"] = "auto_pass"
            else:
                print("  [Non hai abbastanza Kleos per ricordare Penelope]")

        # Special: Tiresia prophecy
        if loc_id == "loc_cimmeri" and engine.state.flags.get("tiresia_prophecy", False):
            if not engine.state.flags.get("tiresia_used", False):
                options.append("Attiva PROFEZIA di Tiresia (-1 Sarissa, rivela future)")
                skill_choices["Attiva PROFEZIA di Tiresia (-1 Sarissa, rivela future)"] = "tiresia"

        choice = get_choice("Cosa fai?", options)

        # Gestione scelte speciali
        if choice == "safe":
            result = engine.attempt_mission(use_safe=True)
        elif choice == "moly":
            result = engine.attempt_mission(use_moly=True)
        elif choice == "auto_pass":
            result = engine.attempt_mission(use_auto_pass=True)
        elif choice == "tiresia":
            prophecy = engine.activate_tiresia_prophecy()
            print(f"\n  {prophecy['message']}")
            print(f"  Prezzo: {prophecy['blood_price']}")
            for loc in prophecy['future_locations']:
                print(f"  - {loc['name']}: difficoltà {loc['difficulty']}")
            input("\n[INVIO per continuare]")
            continue
        else:
            skill = skill_choices[choice]
            result = engine.attempt_mission(skill_choice=skill)

        # Risultato
        print(f"\n  Pool: {result.pool_size} dadi")
        print(f"  Dadi: {result.dice}")
        print(f"  Esito: {result.outcome.value.upper()}")
        if result.special_triggered:
            for s in result.special_triggered:
                print(f"  >>> EVENTO SPECIALE: {s}")
        if result.permanent_penalty:
            for skill, amount in result.permanent_penalty.items():
                print(f"  >>> PENALITÀ PERMANENTE: -{amount} {skill.upper()}")
        print(f"\n  {result.message}")

        if result.kleos_gained:
            print(f"  >>> +{result.kleos_gained} KLEOS")

        input("\n[INVIO per continuare]")

    # Fine partita
    print_header("FINE DELLA PARTITA")
    final = engine.game_status()
    if final['victory']:
        print("\n  🏆 VITTORIA!")
        print(f"  Ulisse è tornata a Itaca.")
        print(f"  Kleos finale: {final['player']['kleos']}")
        if final['player']['kleos'] >= 9:
            print("  Epilogo: Itaca è salva. Penelope e Ulisse si ricostruiscono")
            print("  sui resti del palazzo. Le Proche sono cenere. Il mare è calmo.")
        elif final['player']['kleos'] >= 7:
            print("  Epilogo: Itaca è libera, ma le cicatrici sono profonde.")
            print("  Penelope non riconosce più la donna che è tornata.")
        else:
            print("  Epilogo: Vittoria di Pirro. Il palazzo brucia ancora.")
            print("  Il trono è vuoto. Il mare attende il prossimo naufragio.")
    else:
        print("\n  💀 GAME OVER")
        print(f"  Location finale: {final['location']['name']}")
        print(f"  Kleos accumulato: {final['player']['kleos']}")
        print("\n  L'Odissea non ha fine. Solo altri inizi.")

    # Salva
    save_path = Path.home() / "odyssey_save.json"
    engine.save(save_path)
    print(f"\n  Partita salvata in: {save_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nPartita interrotta.")
        sys.exit(0)
    except EOFError:
        print("\n\nInput terminato.")
        sys.exit(0)
