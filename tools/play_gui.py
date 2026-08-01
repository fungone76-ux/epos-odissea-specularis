"""Launcher dell'app desktop epos.

    python tools/play_gui.py --new --pack worlds/odyssey_specularis --provider demo
    python tools/play_gui.py --load SESSION_ID --provider demo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from epos.dotenv import load_dotenv  # noqa: E402
from epos.gm import DemoGameMaster, OpenAICompatibleGameMaster  # noqa: E402
from epos.renderers import renderer_from_env  # noqa: E402
from epos.state_store import StateStore  # noqa: E402
from epos.turn_service import TurnService  # noqa: E402
from epos.worldpack import load_pack  # noqa: E402


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description="App desktop epos")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--new", action="store_true")
    group.add_argument("--load", metavar="SESSION_ID")
    parser.add_argument("--pack", default="worlds/odyssey_specularis")
    parser.add_argument("--provider", choices=["demo", "live"], default="demo")
    parser.add_argument("--saves", default="saves")
    args = parser.parse_args()

    pack = load_pack(args.pack)
    gm = DemoGameMaster() if args.provider == "demo" else OpenAICompatibleGameMaster()
    service = TurnService(
        gm=gm,
        pack=pack,
        store=StateStore(args.saves),
        renderer=renderer_from_env(),
    )

    if args.new:
        state = service.new_session()
    else:
        state = service.load_session(args.load)

    try:
        from epos.gui import EposGameWindow
    except ImportError as exc:
        raise SystemExit(
            "PySide6 non installato. Esegui: pip install PySide6\n"
            "(oppure: pip install -e .[gui])"
        ) from exc

    window = EposGameWindow(service, state, title=pack.title)
    window.run()


if __name__ == "__main__":
    main()
