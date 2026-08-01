"""Runner da terminale per epos.

    python tools/play.py --new --pack worlds/odyssey_specularis --provider demo
    python tools/play.py --load SESSION_ID --provider demo

Comandi in gioco:
    :state     mostra stato, relazioni, thread, risorse
    :xp        assegna esperienza (nuova abilità o potenziamento)
    :rerender  rigenera l'immagine dell'ultimo turno (senza richiamare il GM)
    :quit      esce lasciando la sessione salvata
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epos.creation import (  # noqa: E402
    CreationAnswers,
    CreationError,
    CreationService,
    award_experience,
)
from epos.dotenv import load_dotenv  # noqa: E402
from epos.gm import DemoGameMaster, OpenAICompatibleGameMaster  # noqa: E402
from epos.models import CREATION_SKILL_BUDGET, MAX_SKILL_RATING  # noqa: E402
from epos.renderers import renderer_from_env  # noqa: E402
from epos.state_store import StateStore  # noqa: E402
from epos.turn_service import PlayerDecision, TurnService  # noqa: E402
from epos.worldpack import load_pack  # noqa: E402

OUTCOME_LABELS = {
    "full_success": "SUCCESSO PIENO",
    "partial_success": "SUCCESSO PARZIALE",
    "failure": "FALLIMENTO",
    "critical_failure": "FALLIMENTO CRITICO",
}


# ---------------------------------------------------------------------------
# Creazione interattiva
# ---------------------------------------------------------------------------


def creation_wizard(pack) -> CreationAnswers:
    print("\n=== CREAZIONE DEL PERSONAGGIO ===")
    print("\nChi è? (una frase: nome e cosa fa o sa fare)")
    identity = input("> ").strip()
    print("\nChe aspetto ha? (una frase: età, fisico, stile)")
    appearance = input("> ").strip()

    print(f"\nCosa sa fare? Distribuisci {CREATION_SKILL_BUDGET} punti: "
          "ogni abilità costa 1, ogni potenziamento +1.")
    skills: dict[str, int] = {}
    service = CreationService(pack)
    while True:
        used = sum(1 + r for r in skills.values())
        remaining = CREATION_SKILL_BUDGET - used
        print(f"\nAbilità attuali: {skills or '(nessuna)'} — punti restanti: {remaining}")
        if remaining <= 0:
            break
        entry = input("Aggiungi (nome [+potenziamenti]) o INVIO per finire > ").strip()
        if not entry:
            if skills:
                break
            continue
        if "+" in entry:
            name, plus = entry.rsplit("+", 1)
            name = name.strip()
            enh = min(int(plus or 0), MAX_SKILL_RATING - 1)
        else:
            name, enh = entry.strip(), 0
        skills[name] = enh

    talent = None
    if skills:
        print(f"\nScegli il talento tra le tue abilità (INVIO per nessuno): {list(skills)}")
        chosen = input("> ").strip()
        if chosen in skills:
            talent = chosen

    print("\nInnesco (opzionale): una situazione specifica a cui il tuo personaggio "
          "reagirà. Lascia vuoto per saltare.")
    trigger = input("> ").strip() or None

    answers = CreationAnswers(
        identity=identity, appearance=appearance, skills=skills,
        talent=talent, trigger=trigger,
    )
    problems = service.validate(answers)
    if problems:
        raise CreationError("; ".join(problems))
    return answers


# ---------------------------------------------------------------------------
# Provider CLI
# ---------------------------------------------------------------------------


def cli_decision(proposal, rating, difficulty, state) -> PlayerDecision:
    pool = 1 + rating
    print("\n--- PROPOSTA DI PROVA ---")
    print(f"  Azione:      {proposal.action_kind} (abilità: {proposal.skill}, rating {rating})")
    print(f"  Difficoltà:  {difficulty}   Pool base: {pool}d6")
    print(f"  Motivo:      {proposal.reason}")
    for outcome, stake in proposal.stakes.items():
        print(f"  {OUTCOME_LABELS.get(outcome, outcome):20s} → {stake}")

    decision = PlayerDecision()
    if state.riserva > 0:
        if input(f"Usare un dado di riserva? ({state.riserva} disponibili) [s/N] > ").strip().lower() == "s":
            decision.use_riserva = True
    price = input("Dado temerario? Dichiara un prezzo o INVIO per no > ").strip()
    if price:
        decision.dado_temerario_price = price
    if state.player.trigger:
        if input(f"Attivare l'innesco «{state.player.trigger}»? [s/N] > ").strip().lower() == "s":
            decision.use_trigger = True

    while True:
        choice = input("Scegli: [roll] tira i dadi, [safe] esito sicuro > ").strip().lower()
        if choice in ("roll", "safe"):
            decision.choice = choice
            return decision
        print("Scelta non valida.")


def cli_narration(context: str) -> str:
    print(f"\n--- NARRAZIONE DEL GIOCATORE ---\n{context}")
    return input("> ").strip()


def cli_split(proposal, player_pool, npc_pool) -> int:
    print("\n--- CONFRONTO ---")
    print(f"  Contesa con {proposal.target_id} (abilità: {proposal.skill})")
    print(f"  Tuoi dadi: {player_pool} — suoi dadi: {npc_pool}")
    for key, stake in proposal.stakes.items():
        print(f"  {key:6s} → {stake}")
    print("La mano sinistra decide CHI VINCE, la destra CHI NARRA.")
    while True:
        raw = input(f"Dadi nella mano sinistra (0-{player_pool}) > ").strip()
        if raw.isdigit() and 0 <= int(raw) <= player_pool:
            return int(raw)
        print("Numero non valido.")


def cli_temerario(roll) -> str | None:
    label = OUTCOME_LABELS[roll.outcome.value]
    price = input(
        f"\n{label}. Tiro temerario? Dichiara un prezzo per ritirare o INVIO > "
    ).strip()
    return price or None


# ---------------------------------------------------------------------------
# Presentazione
# ---------------------------------------------------------------------------


def show_state(state) -> None:
    print("\n--- STATO ---")
    print(f"Turno {state.turn} | {state.time_phase} | location: {state.location_id}")
    if state.player.identity:
        print(f"Chi sono: {state.player.identity}")
    print(f"Abilità: {state.player.skills} | talento: {state.player.talent or '-'}")
    print(f"Innesco: {state.player.trigger or '-'} | Riserva: {state.riserva} dadi")
    print(f"Inventario: {', '.join(state.player.inventory) or '(vuoto)'}")
    print(f"Risorse: {state.player.resources}")
    if state.player.knowledge:
        print(f"So che: {len(state.player.knowledge)} fatti appresi")
    for npc in state.npcs.values():
        presence = "presente" if npc.present else f"altrove ({npc.location_id})"
        print(f"\n{npc.name} [{npc.id}] — {presence}")
        rel = npc.relationships.get("player")
        if rel:
            non_zero = {k: v for k, v in rel.to_dict().items() if v != 0}
            if non_zero:
                print(f"  Relazione: {non_zero}")
        if npc.current_intention:
            print(f"  Intenzione: {npc.current_intention}")
    open_threads = [t for t in state.active_threads if t.status == "open"]
    if open_threads:
        print("\nThread aperti:")
        for thread in open_threads:
            print(f"  [{thread.type}] {thread.summary}")
    if state.story_markers:
        print(f"\nTappe: {', '.join(state.story_markers)}")


def show_turn(result) -> None:
    if result.confront_result is not None:
        r = result.confront_result
        print(f"\n>>> Confronto: tu {r.player_left}+{r.player_right} vs {r.npc_left}+{r.npc_right}"
              f" → vince: {r.winner}, narra: {r.narrator}")
    if result.roll is not None:
        dice = " ".join(str(d) for d in result.roll.dice) or "(esito sicuro)"
        print(f"\n>>> Tiro: [{dice}] → {OUTCOME_LABELS[result.roll.outcome.value]}")
    if result.player_narration:
        print(f"\n(la tua narrazione: {result.player_narration})")
    print(f"\n{result.narration}")
    for line in result.dialogue:
        target = f" (a {line['to']})" if line.get("to") else ""
        print(f"\n{line['speaker']}{target}: «{line['text']}»")
    if result.render_record is not None:
        record = result.render_record
        if record.status == "complete":
            print(f"\n[immagine: {record.image_path}]")
        elif record.status == "failed":
            print(f"\n[rendering fallito: {record.error} — usa :rerender per riprovare]")
        else:
            print("\n[immagine pending — EPOS_RENDER_MODE non attivo o :rerender]")


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Runner epos")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--new", action="store_true", help="nuova sessione")
    group.add_argument("--load", metavar="SESSION_ID", help="carica una sessione")
    parser.add_argument("--pack", default="worlds/odyssey_specularis", help="cartella del world-pack")
    parser.add_argument("--provider", choices=["demo", "live"], default="demo")
    parser.add_argument("--saves", default="saves", help="cartella dei salvataggi")
    parser.add_argument("--no-creation", action="store_true",
                        help="salta la creazione interattiva e usa il player del pack")
    args = parser.parse_args()

    pack = load_pack(args.pack)
    gm = DemoGameMaster() if args.provider == "demo" else OpenAICompatibleGameMaster()
    service = TurnService(
        gm=gm,
        pack=pack,
        store=StateStore(args.saves),
        renderer=renderer_from_env(),
        decision_provider=cli_decision,
        narration_provider=cli_narration,
        split_provider=cli_split,
        temerario_provider=cli_temerario,
    )

    if args.new:
        answers = None
        if pack.interactive_creation and not args.no_creation:
            answers = creation_wizard(pack)
        state = service.new_session(creation_answers=answers)
        print(f"\nNuova sessione: {state.session_id}")
        print(f"\n{state.last_scene}\n")
    else:
        state = service.load_session(args.load)
        print(f"Sessione caricata: {state.session_id} (turno {state.turn})")
        if service.has_pending_checkpoint(state.session_id):
            print("Turno interrotto rilevato: riprendo dal tiro già eseguito.")
            print("Riscrivi la tua azione di quel turno per completare la narrazione.")

    print("Comandi: :state, :xp, :rerender, :quit")

    while True:
        try:
            text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            text = ":quit"
        if not text:
            continue
        if text == ":quit":
            print(f"Sessione salvata: {state.session_id}")
            return
        if text == ":state":
            show_state(state)
            continue
        if text.startswith(":xp"):
            skill = text[3:].strip()
            try:
                new_rating = award_experience(state.player, skill)
                service.store.save_state(state)
                print(f"Esperienza assegnata: {skill} ora ha rating {new_rating}.")
            except CreationError as exc:
                print(f"Esperienza non assegnata: {exc}")
            continue
        if text == ":rerender":
            record = service.rerender(state)
            if record.status == "complete":
                print(f"Immagine rigenerata: {record.image_path}")
            else:
                print(f"Rerender {record.status}: {record.error or ''}")
            continue
        try:
            if service.has_pending_checkpoint(state.session_id):
                result = service.resume_pending(state, text)
                if result is None:
                    result = service.play(state, text)
            else:
                result = service.play(state, text)
            show_turn(result)
        except Exception as exc:  # il turno non applicato non corrompe lo stato
            print(f"\n[turno non applicato: {exc}]")


if __name__ == "__main__":
    main()
