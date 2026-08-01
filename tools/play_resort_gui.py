#!/usr/bin/env python3
"""Launcher GUI live per Seven Nights at Azure Crown.

Uso:
    python tools/play_resort_gui.py --live
    python tools/play_resort_gui.py --live --save salvataggio.json

La GUI usa input libero e risposte reali dell'LLM. Python resta autorevole per
missioni, punteggi, calendario, relazioni, segreti, intro, POV, schedule,
guardaroba e rendering.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication

from epos.dotenv import load_dotenv
from epos.gm import DemoGameMaster, OpenAICompatibleGameMaster
from epos.models import WorldState
from epos.renderers import renderer_from_env
from epos.resort_application import ResortGameApplicationService
from epos.resort_gui import ResortGameWindow
from epos.resort_intro import initialise_resort_intro, intro_active
from epos.resort_production_turn_service import ResortProductionTurnService
from epos.resort_runtime import (
    advance_resort_time,
    initialise_resort_state,
    load_resort_pack,
    process_resort_turn,
)
from epos.resort_schedule import (
    apply_resort_schedule,
    load_resort_schedule_config,
    record_outfit_overrides_from_turn,
    schedule_key,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seven Nights at Azure Crown — GUI")
    parser.add_argument("--live", action="store_true", help="Usa il GM OpenAI-compatibile configurato")
    parser.add_argument("--pack", default="worlds/resort_world", help="Path del world-pack Resort")
    parser.add_argument("--save", help="Path di un salvataggio JSON esistente")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")

    pack_dir = Path(args.pack)
    if not pack_dir.is_absolute():
        pack_dir = root / pack_dir
    resort_pack = load_resort_pack(pack_dir)
    schedule_config = load_resort_schedule_config(pack_dir, resort_pack.world)

    gm = OpenAICompatibleGameMaster() if args.live else DemoGameMaster()

    def process_campaign_turn(state, result):
        changes = process_resort_turn(state, resort_pack, result)
        record_outfit_overrides_from_turn(state, result)
        if not intro_active(state):
            previous_key = schedule_key(state)
            advanced = advance_resort_time(state, force=False)
            if advanced:
                schedule_changes = apply_resort_schedule(
                    state,
                    schedule_config,
                    previous_key=previous_key,
                )
                if schedule_changes:
                    changes = dict(changes or {})
                    changes["schedule"] = schedule_changes
        return changes

    service = ResortProductionTurnService(
        gm=gm,
        pack=resort_pack.world,
        renderer=renderer_from_env(),
        post_turn_processor=process_campaign_turn,
    )

    if args.save:
        data = json.loads(Path(args.save).read_text(encoding="utf-8"))
        state = initialise_resort_state(WorldState.from_dict(data))
    else:
        state = service.new_session()
        initialise_resort_state(state)
    initialise_resort_intro(state)
    service.store.save_state(state)

    app = QApplication(sys.argv)
    window = ResortGameWindow(service, state, resort_pack)
    window.app_service = ResortGameApplicationService(service)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
