#!/usr/bin/env python3
"""Launcher CLI dedicato a Seven Nights at Azure Crown.

Uso:
    python tools/play_resort.py --live

Il launcher carica e valida il world-pack Resort. Il GM live produce risposte
LLM reali; Python governa missioni, punteggi, ricompense e POV visivo NPC-only.
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
    campaign_score,
    campaign_score_tier,
    current_day,
    load_resort_pack,
    new_resort_world,
    process_resort_turn,
)
from epos.resort_turn_service import ResortTurnService


def main() -> None:
    parser = argparse.ArgumentParser(description="Seven Nights at Azure Crown — CLI")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Usa il GM OpenAI-compatibile configurato nell'ambiente",
    )
    parser.add_argument(
        "--pack",
        default="worlds/resort_world",
        help="Path del world-pack resort",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    pack_dir = Path(args.pack)
    if not pack_dir.is_absolute():
        pack_dir = root / pack_dir

    resort_pack = load_resort_pack(pack_dir)
    gm = OpenAICompatibleGameMaster() if args.live else DemoGameMaster()

    def process_campaign_turn(state, result):
        return process_resort_turn(state, resort_pack, result)

    service = ResortTurnService(
        gm=gm,
        pack=resort_pack.world,
        renderer=renderer_from_env(),
        post_turn_processor=process_campaign_turn,
    )
    state = new_resort_world(resort_pack)
    service.store.save_state(state)

    print("SEVEN NIGHTS AT AZURE CROWN")
    print(state.last_scene)
    print("Comandi: :state, :quit")

    while True:
        prompt = (
            f"\nGiorno {current_day(state)} — {state.time_phase} — "
            f"{state.location_id} — Punti {campaign_score(state)}\n> "
        )
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
            print(
                {
                    "day": current_day(state),
                    "phase": state.time_phase,
                    "location": state.location_id,
                    "active_missions": state.flags.get("resort_active_missions", []),
                    "mission_status": state.flags.get("resort_mission_status", {}),
                    "completed_missions": state.flags.get("resort_completed_missions", []),
                    "failed_missions": state.flags.get("resort_failed_missions", []),
                    "completed_events": state.flags.get("resort_completed_events", []),
                    "campaign_score": campaign_score(state),
                    "score_tier": campaign_score_tier(state),
                }
            )
            continue

        result = service.play(state, player_text)
        advance_resort_time(state, force=False)
        service.store.save_state(state)

        print(result.narration)
        for line in result.dialogue:
            print(f"{line.get('speaker', 'NPC')}: {line.get('text', '')}")
        changes = result.campaign_changes or {}
        unlocked = changes.get("unlocked_missions", [])
        if unlocked:
            print("Missioni sbloccate:", ", ".join(unlocked))
        for mission_change in changes.get("mission_changes", []):
            sign = "+" if mission_change["score_delta"] >= 0 else ""
            print(
                f"Missione {mission_change['status']}: {mission_change['mission_id']} "
                f"({sign}{mission_change['score_delta']} punti; "
                f"totale {mission_change['score_total']})"
            )


if __name__ == "__main__":
    main()
