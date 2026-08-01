"""Regole di risoluzione: la matematica del gioco è autorevole Python."""

import random

import pytest

from epos.rules import (
    Outcome,
    RuleError,
    choice_is_meaningful,
    outcome_of_dice,
    pool_size_for,
    resolve_check,
    roll_dice,
    safe_outcome_for,
    validate_difficulty,
)


class TestDifficulty:
    def test_valid_range(self):
        for d in range(1, 7):
            assert validate_difficulty(d) == d

    @pytest.mark.parametrize("d", [0, 7, -1, 99])
    def test_out_of_range_rejected(self, d):
        with pytest.raises(RuleError):
            validate_difficulty(d)


class TestPool:
    def test_base_die_only(self):
        assert pool_size_for(0) == 1

    def test_skill_adds_dice(self):
        assert pool_size_for(2) == 3

    def test_boosts_add_dice(self):
        assert pool_size_for(1, boosts=2) == 4

    def test_cap_at_hard_limit(self):
        from epos.rules import POOL_HARD_CAP

        assert pool_size_for(5, boosts=99) == POOL_HARD_CAP

    def test_negative_rating_ignored(self):
        assert pool_size_for(-2) == 1


class TestOutcomeOfDice:
    def test_critical_failure_all_ones(self):
        assert outcome_of_dice((1, 1, 1), 3) is Outcome.CRITICAL_FAILURE

    def test_critical_failure_single_die_one(self):
        assert outcome_of_dice((1,), 3) is Outcome.CRITICAL_FAILURE

    def test_full_success_two_qualified(self):
        assert outcome_of_dice((3, 5, 1), 3) is Outcome.FULL_SUCCESS

    def test_partial_success_one_qualified(self):
        assert outcome_of_dice((5, 2, 2), 3) is Outcome.PARTIAL_SUCCESS

    def test_failure_none_qualified(self):
        assert outcome_of_dice((2, 2, 2), 4) is Outcome.FAILURE

    def test_critical_beats_partial(self):
        # tutti 1 è critico anche se la difficoltà è 1
        assert outcome_of_dice((1, 1), 1) is Outcome.CRITICAL_FAILURE

    def test_empty_pool_rejected(self):
        with pytest.raises(RuleError):
            outcome_of_dice((), 3)


class TestSafeOutcome:
    def test_pool_above_difficulty_auto_full(self):
        assert safe_outcome_for(4, 3) is Outcome.FULL_SUCCESS

    def test_pool_equal_difficulty_safe_partial(self):
        assert safe_outcome_for(3, 3) is Outcome.PARTIAL_SUCCESS

    def test_pool_below_difficulty_safe_failure(self):
        assert safe_outcome_for(2, 5) is Outcome.FAILURE


class TestChoiceMeaningful:
    def test_meaningful_when_pool_not_above(self):
        assert choice_is_meaningful(3, 3) is True
        assert choice_is_meaningful(2, 5) is True

    def test_not_meaningful_when_pool_above(self):
        assert choice_is_meaningful(4, 3) is False


class TestResolve:
    def test_safe_choice_no_dice_rolled(self):
        roll = resolve_check(3, 3, "safe")
        assert roll.dice == ()
        assert roll.outcome is Outcome.PARTIAL_SUCCESS

    def test_roll_choice_deterministic_with_seed(self):
        rng = random.Random(42)
        roll = resolve_check(3, 3, "roll", rng)
        assert len(roll.dice) == 3
        assert roll.outcome is outcome_of_dice(roll.dice, 3)

    def test_invalid_choice_rejected(self):
        with pytest.raises(RuleError):
            resolve_check(3, 3, "maybe")

    def test_roll_roundtrip(self):
        roll = roll_dice(4, 2, random.Random(7))
        from epos.rules import Roll

        assert Roll.from_dict(roll.to_dict()) == roll
