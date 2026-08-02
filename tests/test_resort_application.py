from pathlib import Path

from epos.application import GuiServiceProviders
from epos.gm import DemoGameMaster
from epos.resort_application import ResortGameApplicationService
from epos.resort_intro_turn_service import ResortIntroTurnService
from epos.resort_runtime import load_resort_pack

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


class StubRenderer:
    """Renderer minimo: il test verifica soltanto il clone del servizio GUI."""

    def render(self, prompt_package, output_dir):  # pragma: no cover
        raise AssertionError("Il renderer non deve essere chiamato in questo test")


def test_gui_provider_clone_preserves_resort_intro_service_class():
    resort_pack = load_resort_pack(PACK_DIR)
    service = ResortIntroTurnService(
        gm=DemoGameMaster(),
        pack=resort_pack.world,
        renderer=StubRenderer(),
    )
    app = ResortGameApplicationService(service)

    cloned = app.service_with_providers(GuiServiceProviders())

    assert isinstance(cloned, ResortIntroTurnService)
    assert type(cloned) is ResortIntroTurnService
    assert cloned.renderer is service.renderer
