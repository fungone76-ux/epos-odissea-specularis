"""Runtime integration for Odissea Specularis.

This module keeps campaign-specific rules outside the generic EPOS engine:

- mission difficulty is made authoritative before Python validates and rolls;
- retry and named Odyssey effects are applied before resolution;
- structured confrontations are translated into campaign outcomes for the
  existing mission tracker.

The wrapped Game Master still proposes narrative intent. Python replaces only
campaign mathematics derived from the canonical world state and world-pack.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from .contract import CheckProposal, GmPhaseResponse
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
    """Return the authoritative pre-roll difficulty for an Odyssey check.

    Non-mission checks retain the GM proposal. Mission checks instead use the
    canonical mission definition and current persistent effects.
    """

    tracker = OdysseyMissionTracker(state, pack=pack)
    if not _is_mission_check(tracker, proposal):
        return proposal.difficulty

    mission = tracker.current_mission()
    difficulty = mission.difficulty
    location_id = tracker.current_location_id()

    # Circe: possessing moly lowers the canonical difficulty to 3.
    if location_id == "loc_circe" and state.flags.get("moly_possessed", False):
        difficulty = min(difficulty, 3)

    # Retry/preparation is persistent and must affect the next real roll.
    difficulty -= int(state.flags.get("retry_difficulty_offset", 0))

    # Poseidon's curse explicitly increases Pontos difficulty.
    if proposal.skill == "pontos" and state.flags.get("poseidon_curse_active", False):
        difficulty += 1

    # Canonical automatic advantages are represented as difficulty 1. Given
    # the campaign's relevant trained skills this produces the full-success
    # automatic branch in TurnService without inventing dice.
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
    """Transparent GM adapter that applies Odyssey rules before validation."""

    def __init__(self, inner: Any):
        self.inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def propose(self, state: WorldState, pack: WorldPack, player_text: str) -> GmPhaseResponse:
        response = self.inner.propose(state, pack, player_text)
        return normalize_odyssey_phase_response(state, pack, response)

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
        return normalize_odyssey_phase_response(state, pack, response)


def _confront_as_mission_check(result: TurnResult) -> TurnResult | None:
    """Build a tracker-only check view from a resolved confrontation."""

    confront = result.confront_result
    if confront is None or result.mode != "confront":
        return None

    proposal = getattr(result, "confront_proposal", None)
    # Current TurnResult does not persist the ConfrontProposal separately.
    # Recover the authoritative skill/target from the resolved result fields
    # added by TurnService where available; otherwise no campaign inference.
    skill = getattr(confront, "skill", "")
    target_id = getattr(confront, "target_id", "")
    if not skill or not target_id:
        return None

    outcome = {
        "player": Outcome.FULL_SUCCESS,
        "npc": Outcome.FAILURE,
        "stall": Outcome.PARTIAL_SUCCESS,
    }.get(confront.winner, Outcome.FAILURE)
    check = CheckProposal(
        action_kind="social",
        skill=skill,
        difficulty=1,
        target_ids=[target_id],
        opposition="npc_resistance",
        reason="Esito autorevole di un confronto strutturato.",
        stakes={
            "critical_failure": result.stake,
            "failure": result.stake,
            "partial_success": result.stake,
            "full_success": result.stake,
        },
    )
    roll = Roll(pool_size=0, difficulty=1, dice=(), outcome=outcome)
    return replace(result, mode="check", proposal=check, roll=roll)


def process_odyssey_turn(
    state: WorldState,
    pack: WorldPack,
    result: TurnResult,
) -> dict[str, Any]:
    """Canonical Odyssey post-turn processor used by CLI and GUI."""

    tracker = OdysseyMissionTracker(state, pack=pack)
    synthetic = _confront_as_mission_check(result)
    return tracker.process_turn(synthetic or result)
