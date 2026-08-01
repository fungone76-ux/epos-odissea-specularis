from pathlib import Path

from epos.application import GameApplicationService, GuiServiceProviders, find_turn_image
from epos.gm import DemoGameMaster
from epos.models import Thread
from epos.state_store import StateStore
from epos.turn_service import TurnService
from epos.worldpack import load_pack

DEMO_PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"
ODYSSEY_PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


def _service(pack_dir: Path, tmp_path):
    pack = load_pack(pack_dir)
    return TurnService(gm=DemoGameMaster(), pack=pack, store=StateStore(tmp_path / "saves"))


def test_state_view_exposes_threads_and_worldpack_missions(tmp_path):
    service = _service(ODYSSEY_PACK, tmp_path)
    state = service.pack.new_world("app-view")
    state.open_thread(
        Thread(
            id="t1",
            type="question",
            participants=["player"],
            summary="chi controlla davvero la rotta",
            opened_turn=state.turn,
        )
    )
    app = GameApplicationService(service)

    text = app.state_view(state).text

    assert "Thread attivi:" in text
    assert "chi controlla davvero la rotta" in text
    assert "Missioni attive:" in text
    assert service.pack.missions


def test_visual_prompt_view_and_image_lookup_are_read_only(tmp_path):
    service = _service(DEMO_PACK, tmp_path)
    state = service.pack.new_world("app-visual")
    app = GameApplicationService(service)
    assert app.visual_prompt_view(state).turn is None

    turn_dir = service.store.turn_dir(state.session_id, 0)
    image = turn_dir / "image.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    service.store.save_turn_artifact(
        state.session_id,
        0,
        "render_record",
        {"status": "complete", "image_path": str(image), "backend": "test"},
    )
    service.store.save_turn_artifact(
        state.session_id,
        0,
        "visual_contract",
        {"prompt_package": {"positive": "sunlit room", "negative": "bad anatomy"}},
    )
    state.turn = 1

    assert find_turn_image(service.store, state.session_id, 0) == image
    assert app.last_turn_image(state) == image
    prompt = app.visual_prompt_view(state)
    assert prompt.turn == 0
    assert "sunlit room" in prompt.text
    assert "bad anatomy" in prompt.text


def test_gui_service_preserves_post_turn_processor(tmp_path):
    pack = load_pack(ODYSSEY_PACK)

    def campaign_processor(state, result):
        state.flags["campaign_processor_called"] = True
        return {"campaign_processor_called": True}

    service = TurnService(
        gm=DemoGameMaster(),
        pack=pack,
        store=StateStore(tmp_path / "saves"),
        post_turn_processor=campaign_processor,
    )
    app = GameApplicationService(service)

    gui_service = app.service_with_providers(GuiServiceProviders())

    assert gui_service.post_turn_processor is campaign_processor
