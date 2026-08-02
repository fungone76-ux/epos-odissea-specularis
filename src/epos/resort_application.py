"""GUI application facade for the Azure Crown Resort.

The generic GameApplicationService rebuilds a plain TurnService when Qt
providers are attached. That silently discards ResortIntroTurnService and all
its intro orchestration. This facade preserves the concrete service class.
"""

from __future__ import annotations

from .application import GameApplicationService, GuiServiceProviders
from .turn_service import TurnService


class ResortGameApplicationService(GameApplicationService):
    """Clone GUI providers without downgrading the Resort service subclass."""

    def service_with_providers(self, providers: GuiServiceProviders) -> TurnService:
        service_class = type(self.service)
        return service_class(
            gm=self.service.gm,
            pack=self.service.pack,
            store=self.service.store,
            renderer=self.service.renderer,
            rng=self.service.rng,
            decision_provider=providers.decision_provider,
            narration_provider=providers.narration_provider,
            split_provider=providers.split_provider,
            temerario_provider=providers.temerario_provider,
            post_turn_processor=self.service.post_turn_processor,
            progress=providers.progress,
        )
