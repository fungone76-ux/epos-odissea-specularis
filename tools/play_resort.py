#!/usr/bin/env python3
"""Launcher CLI dedicato a Seven Nights at Azure Crown.

Uso:
    python tools/play_resort.py
    python tools/play_resort.py --live

Il launcher carica e valida world.yaml, npcs.yaml, visual.yaml,
missions.yaml ed events.yaml prima di creare la sessione.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epos.dotenv import load_dotenv
from epos.gm import DemoGameMaster, OpenAICompatibleGameMaster
from epos.renderers import renderer_from_env
from epos.resort_runtime import (
    advance_resort_time,
    current_day,
    load_resort_pack,
    new_resort_world,
    update_luna_disclosure_gates,
    update_mission_unlocks,
)
from epos.turn_service import TurnService


def main() -> None:
    parser = argparse.ArgumentParser(description="Seven Nights at Azure Crown — CLI")
    parser.add_argument("--live", action="store_true", help="Usa il GM OpenAI-compatibile configurato nell'ambiente")
    parser.add_argument("--pack", default="worlds/resort_world", help="Path del world-pack resort")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    pack_dir = Path(args.pack)
    if not pack_dir.is_absolute():
        pack_dir = root / pack_dir

    resort_pack = load_resort_pack(pack_dir)
    gm = OpenAICompatibleGameMaster() if args.live else DemoGameMaster()
    service = TurnService(
        gm=gm,
        pack=resort_pack.world,
        renderer=renderer_from_env(),
    )
    state = new_resort_world(resort_pack)
    service.store.save_state(state)

    print("SEVEN NIGHTS AT AZURE CROWN")
    print(state.last_scene)
    print("Comandi: :state, :quit")

    while True:
        prompt = f"\nGiorno {current_day(state)} — {state.time_phase} — {state.location_id}\n> "
        try:
            player_text = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not player_text:
            continue
        if player_text == ":quit":
            break
        if player_text == ":state":
            print({
                "day": current_day(state),
                "phase": state.time_phase,
                "location": state.location_id,
                "active_missions": state.flags.get("resort_active_missions", []),
                "completed_events": state.flags.get("resort_completed_events", []),
            })
            continue

        result = service.play(state, player_text)
        update_luna_disclosure_gates(state)
        unlocked = update_mission_unlocks(state, resort_pack)
        advance_resort_time(state, force=False)
        service.store.save_state(state)

        print(result.narration)
        if unlocked:
            print("Missioni sbloccate:", ", ".join(unlocked))


if __name__ == "__main__":
    main()
