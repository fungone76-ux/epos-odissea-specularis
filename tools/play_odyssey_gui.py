#!/usr/bin/env python3
"""Launcher GUI per Odissea Specularis.

Uso:
    python tools/play_odyssey_gui.py
    python tools/play_odyssey_gui.py --live
    python tools/play_odyssey_gui.py --live --save salvataggio.json

--live usa OpenAICompatibleGameMaster (endpoint OpenAI-compatibile:
OpenAI, Gemini, LM Studio, Ollama...). Default: GM demo offline.

La configurazione si legge dal file .env nella radice del progetto
(copia .env.example come .env e inserisci i tuoi valori):
- EPOS_LLM_BASE_URL / EPOS_LLM_MODEL / EPOS_LLM_API_KEY  → GM live
- EPOS_RENDER_MODE=comfy + EPOS_COMFY_URL/WORKFLOW/...   → immagini SD
Le variabili d'ambiente di sistema hanno precedenza sul file .env.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication

from epos.dotenv import load_dotenv
from epos.gm import OpenAICompatibleGameMaster
from epos.models import WorldState
from epos.renderers import renderer_from_env
from epos.turn_service import TurnService
from epos.worldpack import load_pack

from epos.odyssey_gm import OdysseyDemoGameMaster
from epos.odyssey_gui import OdysseyGameWindow
from epos.odyssey_runtime import OdysseyRuleAwareGameMaster, process_odyssey_turn


def main() -> None:
    parser = argparse.ArgumentParser(description="Odissea Specularis — GUI")
    parser.add_argument("--live", action="store_true", help="Usa GM live (richiede env LLM)")
    parser.add_argument("--pack", default="worlds/odyssey_specularis", help="Path del world-pack")
    parser.add_argument("--save", help="Path di un salvataggio esistente")
    args = parser.parse_args()

    # Configurazione da .env nella radice del progetto (se presente)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    pack_dir = Path(args.pack)
    if not pack_dir.is_absolute():
        pack_dir = Path(__file__).parent.parent / pack_dir

    pack = load_pack(pack_dir)

    # GM
    if args.live:
        try:
            base_gm = OpenAICompatibleGameMaster()
        except Exception as exc:
            print(f"Errore configurazione live: {exc}", file=sys.stderr)
            print("Uso il GM demo offline.", file=sys.stderr)
            base_gm = OdysseyDemoGameMaster()
    else:
        base_gm = OdysseyDemoGameMaster()

    # L'adattatore applica le regole matematiche dell'Odissea prima che
    # TurnService validi e risolva la prova. La LLM non decide la difficolta.
    gm = OdysseyRuleAwareGameMaster(base_gm)

    # Service con renderer da EPOS_RENDER_MODE (pending | comfy | novelai)
    def process_campaign_turn(state, result):
        return process_odyssey_turn(state, pack, result, gm=gm)

    service = TurnService(
        gm=gm,
        pack=pack,
        renderer=renderer_from_env(),
        post_turn_processor=process_campaign_turn,
    )

    # Stato: salvataggio esistente oppure nuova sessione
    if args.save:
        data = json.loads(Path(args.save).read_text(encoding="utf-8"))
        state = WorldState.from_dict(data)
        service.store.save_state(state)
    else:
        state = service.new_session()

    app = QApplication(sys.argv)
    window = OdysseyGameWindow(service, state)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
