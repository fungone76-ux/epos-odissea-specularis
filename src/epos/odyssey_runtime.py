"""Runtime integration for Odissea Specularis.

Campaign-specific mathematics stays outside the generic EPOS engine:

- mission difficulty is authoritative before Python validates and rolls;
- retry and named Odyssey effects are applied before resolution;
- structured confrontations are translated into campaign outcomes for the
  existing mission tracker without asking the LLM to decide persistence.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from .contract import CheckProposal, ConfrontProposal, GmPhaseResponse
from .models import WorldState
from .odyssey_mission_tracker import OdysseyMissionTracker
from .rules import Outcome, Roll
from .turn_service import TurnResult
from .worldpack import WorldPack


def _is_mission_check(
    tracker: OdysseyMissionTracker,
    proposal: CheckProposal,
) -> bool:
    return proposal.skill in tracker.required_skills()


def effective_mission_difficulty(
    state: WorldState,
    pack: WorldPack,
    proposal: CheckProposal,
) -> int:
    """Return the authoritative pre-roll difficulty for an Odyssey check."""

    tracker = OdysseyMissionTracker(state, pack=pack)
    if not _is_mission_check(tracker, proposal):
        return proposal.difficulty

    mission = tracker.current_mission()
    difficulty = mission.difficulty
    location_id = tracker.current_location_id()

    if location_id == "loc_circe" and state.flags.get("moly_possessed", False):
        difficulty = min(difficulty, 3)

    difficulty -= int(state.flags.get("retry_difficulty_offset", 0))

    if proposal.skill == "pontos" and state.flags.get("poseidon_curse_active", False):
        difficulty += 1

    if (
        location_id == "loc_calipso"
        and state.flags.get("odyssey_kleos", 0) >= 4
        and not state.flags.get("calipso_auto_pass_used", False)
    ):
        difficulty = 1
    if (
        location_id == "loc_itaca"
        and int(state.flags.get("itaca_phase", 0)) == 0
        and state.flags.get("phaeacian_ship", False)
    ):
        difficulty = 1

    return max(1, min(6, int(difficulty)))


def normalize_odyssey_phase_response(
    state: WorldState,
    pack: WorldPack,
    response: GmPhaseResponse,
) -> GmPhaseResponse:
    """Replace only campaign mathematics in a phase-one GM response."""

    if response.mode != "check_proposal" or response.check is None:
        return response
    difficulty = effective_mission_difficulty(state, pack, response.check)
    if difficulty == response.check.difficulty:
        return response
    return replace(response, check=replace(response.check, difficulty=difficulty))


class OdysseyRuleAwareGameMaster:
    """Transparent GM adapter applying Odyssey rules before validation."""

    def __init__(self, inner: Any):
        self.inner = inner
        self._confront_context: dict[tuple[str, int], ConfrontProposal] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def _remember_confront(
        self,
        state: WorldState,
        response: GmPhaseResponse,
    ) -> GmPhaseResponse:
        if response.mode == "confront_proposal" and response.confront is not None:
            self._confront_context[(state.session_id, state.turn)] = response.confront
        return response

    def pop_confront_context(
        self,
        session_id: str,
        turn: int,
    ) -> ConfrontProposal | None:
        return self._confront_context.pop((session_id, turn), None)

    def propose(self, state: WorldState, pack: WorldPack, player_text: str) -> GmPhaseResponse:
        response = self.inner.propose(state, pack, player_text)
        response = normalize_odyssey_phase_response(state, pack, response)
        return self._remember_confront(state, response)

    def propose_validated(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        validator: Callable[[GmPhaseResponse], Any],
    ) -> GmPhaseResponse:
        propose_validated = getattr(self.inner, "propose_validated", None)
        if propose_validated is None:
            response = self.propose(state, pack, player_text)
            validator(response)
            return response

        def validate_adjusted(response: GmPhaseResponse) -> Any:
            adjusted = normalize_odyssey_phase_response(state, pack, response)
            return validator(adjusted)

        response = propose_validated(state, pack, player_text, validate_adjusted)
        response = normalize_odyssey_phase_response(state, pack, response)
        return self._remember_confront(state, response)


def _confront_as_mission_check(
    result: TurnResult,
    proposal: ConfrontProposal | None,
) -> TurnResult | None:
    """Build a tracker-only check view from a resolved confrontation."""

    confront = result.confront_result
    if confront is None or result.mode != "confront" or proposal is None:
        return None

    outcome = {
        "player": Outcome.FULL_SUCCESS,
        "npc": Outcome.FAILURE,
        "stall": Outcome.PARTIAL_SUCCESS,
    }.get(confront.winner, Outcome.FAILURE)
    check = CheckProposal(
        action_kind="social",
        skill=proposal.skill,
        difficulty=1,
        target_ids=[proposal.target_id],
        opposition="npc_resistance",
        reason=proposal.reason or "Esito autorevole di un confronto strutturato.",
        stakes={
            "critical_failure": proposal.stakes.get("lose", result.stake),
            "failure": proposal.stakes.get("lose", result.stake),
            "partial_success": proposal.stakes.get("stall", result.stake),
            "full_success": proposal.stakes.get("win", result.stake),
        },
    )
    roll = Roll(pool_size=0, difficulty=1, dice=(), outcome=outcome)
    return replace(
        result,
        mode="check",
        proposal=check,
        roll=roll,
        stake=check.stakes[outcome.value],
    )


def process_odyssey_turn(
    state: WorldState,
    pack: WorldPack,
    result: TurnResult,
    gm: OdysseyRuleAwareGameMaster | None = None,
) -> dict[str, Any]:
    """Canonical Odyssey post-turn processor used by CLI and GUI."""

    proposal = gm.pop_confront_context(state.session_id, result.turn) if gm else None
    tracker = OdysseyMissionTracker(state, pack=pack)
    synthetic = _confront_as_mission_check(result, proposal)
    return tracker.process_turn(synthetic or result)
