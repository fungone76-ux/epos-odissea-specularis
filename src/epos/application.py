from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .models import WorldState
from .outfit import format_current_outfit_for_ui
from .renderers import RenderRecord
from .state_store import StateStore
from .turn_service import TurnResult, TurnService
from .worldpack import MissionDef, WorldPack

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class GuiStateView:
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass(frozen=True)
class VisualPromptView:
    turn: int | None
    positive: str
    negative: str

    @property
    def text(self) -> str:
        if self.turn is None:
            return "(nessun visual contract ancora)"
        return f"POSITIVO:\n{self.positive or '-'}\n\nNEGATIVO:\n{self.negative or '-'}"


@dataclass(frozen=True)
class GuiOperationProgress:
    phase: str
    message: str
    busy: bool = True

    @property
    def label(self) -> str:
        return self.message if self.phase == "idle" else f"{self.phase}: {self.message}"


@dataclass(frozen=True)
class GuiServiceProviders:
    decision_provider: Callable[..., Any] | None = None
    narration_provider: Callable[..., str] | None = None
    split_provider: Callable[..., int] | None = None
    temerario_provider: Callable[..., str | None] | None = None
    progress: Callable[[str], None] | None = None


class GameApplicationService:
    """Stable non-Qt facade used by the desktop GUI.

    The facade formats read-only UI data and delegates every world mutation to
    TurnService. It deliberately does not roll dice, apply scene mutations, or
    inspect renderer internals.
    """

    def __init__(self, service: TurnService):
        self.service = service

    @property
    def pack(self) -> WorldPack:
        return self.service.pack

    @property
    def store(self) -> StateStore:
        return self.service.store

    def service_with_providers(self, providers: GuiServiceProviders) -> TurnService:
        return TurnService(
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

    def play(self, state: WorldState, player_text: str, providers: GuiServiceProviders) -> TurnResult:
        service = self.service_with_providers(providers)
        if service.has_pending_checkpoint(state.session_id):
            result = service.resume_pending(state, player_text)
            if result is not None:
                return result
        return service.play(state, player_text)

    def rerender(self, state: WorldState, turn: int | None = None) -> RenderRecord:
        return self.service.rerender(state, turn)

    def save_current(self, state: WorldState) -> None:
        self.store.save_state(state)

    def new_session(self, session_id: str | None = None) -> WorldState:
        return self.service.new_session(session_id=session_id)

    def load_session(self, session_id: str) -> WorldState:
        return self.service.load_session(session_id)

    def list_sessions(self) -> list[str]:
        return self.store.list_sessions()

    def latest_session_id(self) -> str | None:
        sessions = self.list_sessions()
        return sessions[-1] if sessions else None

    def location_name(self, state: WorldState) -> str:
        location = self.pack.locations.get(state.location_id)
        return location.name if location else state.location_id

    def state_view(self, state: WorldState) -> GuiStateView:
        player = state.player
        lines = [
            f"Turno: {state.turn}   -   {state.time_phase}",
            f"Luogo: {self.location_name(state)}",
            "",
        ]
        if player.skills:
            skills = ", ".join(f"{k} {v}" for k, v in player.skills.items())
            lines.append(f"Abilita: {skills}")
        if player.talent:
            lines.append(f"Talento: {player.talent}")
        if player.trigger:
            lines.append(f"Innesco: \"{player.trigger}\"")
        lines.append(f"Riserva: {state.riserva} dadi")
        if player.resources:
            resources = ", ".join(f"{k} {v}" for k, v in player.resources.items())
            lines.append(f"Risorse: {resources}")
        lines.append("")
        outfit_ui = format_current_outfit_for_ui(player)
        if outfit_ui.value == "Indossa":
            lines.append("Indossa:")
            lines.extend(f"  - {item}" for item in outfit_ui.items)
        else:
            lines.append(outfit_ui.value)
            lines.extend(f"  - {item}" for item in outfit_ui.items)
        if player.outfit.removed:
            lines.append("Tolti:")
            lines.extend(f"  - {item}" for item in player.outfit.removed)
        if player.wounds:
            lines.append(f"Ferite: {', '.join(player.wounds)}")
        if player.conditions:
            lines.append(f"Condizioni: {', '.join(player.conditions)}")
        self._append_present_npcs(lines, state)
        self._append_active_threads(lines, state)
        self._append_active_missions(lines, state)
        return GuiStateView(lines)

    def journal_lines(self, state: WorldState) -> list[str]:
        player = state.player
        lines = [f"Turno {state.turn} - {state.time_phase} - {self.location_name(state)}"]
        if player.identity:
            lines.append(f"\nChi sono: {player.identity}")
        lines.append(f"Abilita: {player.skills}")
        if player.knowledge:
            lines.append("\nSo che:")
            lines.extend(f"  - {k}" for k in player.knowledge[-10:])
        for npc in state.npcs.values():
            rel = npc.relationships.get("player")
            non_zero = {k: v for k, v in rel.to_dict().items() if v != 0} if rel else {}
            presence = "presente" if npc.present else npc.location_id
            line = f"\n{npc.name} - {presence}"
            if non_zero:
                line += f"\n  {non_zero}"
            if npc.current_intention:
                line += f"\n  intenzione: {npc.current_intention}"
            lines.append(line)
        if state.story_markers:
            lines.append(f"\nTappe: {', '.join(state.story_markers)}")
        open_threads = [thread for thread in state.active_threads if thread.status == "open"]
        if open_threads:
            lines.append("\nThread attivi:")
            lines.extend(f"  [{thread.type}] {thread.summary}" for thread in open_threads)
        current = self.current_missions(state)
        if current:
            lines.append("\nMissioni attive:")
            lines.extend(f"  {mission.name}: {mission.description}" for mission in current)
        return lines

    def visual_prompt_view(self, state: WorldState) -> VisualPromptView:
        turn = state.turn - 1
        while turn >= 0:
            contract = self.store.load_turn_artifact(state.session_id, turn, "visual_contract")
            if contract:
                package = contract.get("prompt_package", {})
                return VisualPromptView(
                    turn=turn,
                    positive=str(package.get("positive", "")),
                    negative=str(package.get("negative", "")),
                )
            turn -= 1
        return VisualPromptView(turn=None, positive="", negative="")

    def last_turn_image(self, state: WorldState) -> Path | None:
        turn = state.turn - 1
        while turn >= 0:
            path = find_turn_image(self.store, state.session_id, turn)
            if path is not None:
                return path
            turn -= 1
        return None

    def current_missions(self, state: WorldState) -> list[MissionDef]:
        return [m for m in self.pack.missions.values() if m.location_id == state.location_id]

    def upcoming_missions(self, state: WorldState) -> list[MissionDef]:
        current_ids = {m.id for m in self.current_missions(state)}
        target_ids: set[str] = set()
        for mission in self.pack.missions.values():
            if mission.id not in current_ids:
                continue
            for transition in mission.transitions:
                target = transition.get("mission_id") or transition.get("target_mission_id")
                if target:
                    target_ids.add(str(target))
        return [m for m in self.pack.missions.values() if m.id in target_ids]

    def _append_present_npcs(self, lines: list[str], state: WorldState) -> None:
        present = [npc for npc in state.npcs.values() if npc.present]
        if not present:
            return
        lines.append("")
        lines.append("NPC presenti:")
        for npc in present:
            extra = f" - {len(npc.disclosed_facts)} rivelati" if npc.disclosed_facts else ""
            lines.append(f"  - {npc.name}{extra}")

    def _append_active_threads(self, lines: list[str], state: WorldState) -> None:
        open_threads = [thread for thread in state.active_threads if thread.status == "open"]
        if not open_threads:
            return
        lines.append("")
        lines.append("Thread attivi:")
        for thread in open_threads[:6]:
            lines.append(f"  - [{thread.type}] {thread.summary}")

    def _append_active_missions(self, lines: list[str], state: WorldState) -> None:
        current = self.current_missions(state)
        upcoming = self.upcoming_missions(state)
        if not current and not upcoming:
            return
        lines.append("")
        if current:
            lines.append("Missioni attive:")
            lines.extend(f"  - {mission.name}" for mission in current[:4])
        if upcoming:
            lines.append("Missioni prossime:")
            lines.extend(f"  - {mission.name}" for mission in upcoming[:4])


def find_turn_image(store: StateStore, session_id: str, turn: int) -> Path | None:
    record = store.load_turn_artifact(session_id, turn, "render_record")
    if not record or record.get("status") != "complete":
        return None
    path = Path(record.get("image_path") or "")
    if path.exists() and path.suffix.casefold() in SUPPORTED_IMAGE_SUFFIXES:
        return path
    return None
