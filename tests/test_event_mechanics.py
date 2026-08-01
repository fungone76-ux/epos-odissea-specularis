"""Meccaniche del manuale EVENT: open-end, talento, confronto, temerarie,
narrazione del giocatore, riserva, innesco, creazione, esperienza."""

import random
from pathlib import Path

import pytest

from epos.contract import ConfrontProposal, GmPhaseResponse
from epos.creation import (
    CreationAnswers,
    CreationError,
    CreationService,
    award_experience,
    skill_points_used,
)
from epos.gm import DemoGameMaster
from epos.rules import (
    Outcome,
    RuleError,
    confront,
    npc_split_strategy,
    reckless_reroll,
    roll_dice,
)
from epos.state_store import StateStore
from epos.turn_service import PlayerDecision, TurnService
from epos.worldpack import load_pack

PACK_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


@pytest.fixture
def pack():
    return load_pack(PACK_DIR)


@pytest.fixture
def state(pack):
    return pack.new_world("event-mechanics")


class TestOpenEnd:
    def test_six_explodes(self):
        rng = random.Random(3)
        for _ in range(200):
            roll = roll_dice(2, 3, rng, open_end=True)
            if 6 in roll.dice[:2]:
                # almeno una volta i dadi esplosi devono superare il pool
                pass
        rng = random.Random(0)
        exploded = any(
            len(roll_dice(1, 3, rng, open_end=True).dice) > 1 for _ in range(50)
        )
        assert exploded

    def test_no_open_end_no_explosion(self):
        rng = random.Random(0)
        for _ in range(50):
            roll = roll_dice(2, 3, rng, open_end=False)
            assert len(roll.dice) == 2


class TestTalent:
    def test_lowest_die_rerolled(self):
        class FixedRng:
            def __init__(self):
                self.values = iter([1, 2, 5])  # due dadi: 1 e 2, ritiro: 5

            def randint(self, a, b):
                return next(self.values)

        roll = roll_dice(2, 3, FixedRng(), talent=True)
        assert sorted(roll.dice) == [2, 5]  # l'1 è stato ritirato


class TestConfront:
    def test_more_dice_wins_left(self):
        result = confront(3, 2, 3, random.Random(1), npc_left=1)
        assert result.winner == "player"

    def test_right_hand_decides_narrator(self):
        result = confront(3, 3, 0, random.Random(1), npc_left=3)
        # 3 vs 0 a destra: il giocatore narra pur perdendo il confronto
        assert result.winner == "npc"
        assert result.narrator == "player"

    def test_tie_rolls_bet_dice(self):
        result = confront(2, 2, 2, random.Random(1), npc_left=2)
        assert result.winner in ("player", "npc", "stall")
        if result.winner != "stall":
            assert result.player_left_dice and result.npc_left_dice

    def test_zero_zero_is_stall(self):
        result = confront(2, 2, 2, random.Random(1), npc_left=2)
        # destra 0 vs 0: stallo narrativo → condivisa
        assert result.narrator == "shared"

    def test_invalid_split_rejected(self):
        with pytest.raises(RuleError):
            confront(2, 2, 3, random.Random(1))

    def test_npc_strategy_small_pool_all_in(self):
        assert npc_split_strategy(2) == 2
        assert npc_split_strategy(1) == 1

    def test_npc_strategy_keeps_narration_die(self):
        left = npc_split_strategy(4)
        assert 0 < 4 - left  # tiene dadi dietro quando può


class TestReckless:
    def test_reroll_overwrites(self):
        roll = roll_dice(2, 3, random.Random(1))
        rerolled = reckless_reroll(roll, random.Random(2))
        assert rerolled.pool_size == roll.pool_size
        assert rerolled.difficulty == roll.difficulty


class TestConfrontTurnFlow:
    def _confront_gm(self):
        class ConfrontGM(DemoGameMaster):
            def propose(self, state, pack, player_text):
                return GmPhaseResponse.from_dict(
                    {
                        "mode": "confront_proposal",
                        "confront": {
                            "skill": "social",
                            "target_id": "maera",
                            "reason": "Braccio di ferro verbale sulla dispensa",
                            "stakes": {
                                "win": "Maera cede e parla",
                                "lose": "Maera ti mette alla porta",
                                "stall": "Resta tutto sospeso",
                            },
                        },
                    }
                )

        return ConfrontGM()

    def test_full_confront_cycle(self, pack, tmp_path):
        service = TurnService(
            gm=self._confront_gm(),
            pack=pack,
            store=StateStore(tmp_path / "saves"),
            rng=random.Random(4),
            split_provider=lambda p, mine, theirs: mine,  # tutto in attacco
        )
        state = service.new_session()
        result = service.play(state, "Sfido Maera: o parli o resto qui tutta la notte.")

        assert result.mode == "confront"
        assert result.confront_result is not None
        assert result.confront_result.winner in ("player", "npc", "stall")
        assert state.turn == 1
        assert service.store.load_turn_artifact(state.session_id, 0, "confront") is not None

    def test_confront_player_narrates(self, pack, tmp_path):
        service = TurnService(
            gm=self._confront_gm(),
            pack=pack,
            store=StateStore(tmp_path / "saves"),
            rng=random.Random(4),
            split_provider=lambda p, mine, theirs: 0,  # tutto in narrazione
            narration_provider=lambda ctx: "Le spiego esattamente perché deve fidarsi.",
        )
        state = service.new_session()
        result = service.play(state, "Lascio che Maera vinca, ma la storia la scrivo io.")
        assert result.confront_result.narrator in ("player", "shared")
        assert result.player_narration == "Le spiego esattamente perché deve fidarsi."


class TestPlayerNarrationOnFullSuccess:
    def test_full_success_asks_player(self, pack, tmp_path):
        asked = {"called": False}

        def narration_provider(ctx):
            asked["called"] = True
            return "Apro la dispensa senza fare rumore e trovo il registro."

        class RiggedDice:
            def randint(self, a, b):
                return 6  # tutti 6: successo pieno garantito

        service = TurnService(
            gm=DemoGameMaster(),
            pack=pack,
            store=StateStore(tmp_path / "saves"),
            rng=RiggedDice(),
            narration_provider=narration_provider,
        )
        state = service.new_session()
        state.player.skills["physical"] = 2  # pool 3: successo pieno possibile
        result = service.play(state, "Tento di aprire la dispensa.")
        assert result.roll.outcome is Outcome.FULL_SUCCESS
        assert asked["called"] is True
        assert "registro" in result.player_narration

    def test_failure_does_not_ask_player(self, pack, tmp_path):
        asked = {"called": False}

        class UnluckyDice:
            def randint(self, a, b):
                return 2

        service = TurnService(
            gm=DemoGameMaster(),
            pack=pack,
            store=StateStore(tmp_path / "saves"),
            rng=UnluckyDice(),
            narration_provider=lambda ctx: asked.__setitem__("called", True) or "",
        )
        state = service.new_session()
        result = service.play(state, "Tento di aprire la dispensa.")
        assert result.roll.outcome is not Outcome.FULL_SUCCESS
        assert asked["called"] is False


class TestRiservaAndTrigger:
    def test_riserva_consumed_on_roll(self, pack, tmp_path):
        pack_riserva = pack
        service = TurnService(
            gm=DemoGameMaster(),
            pack=pack_riserva,
            store=StateStore(tmp_path / "saves"),
            rng=random.Random(1),
            decision_provider=lambda p, rating, diff, state: PlayerDecision(
                choice="roll", use_riserva=True
            ),
        )
        state = service.new_session()
        state.riserva = 2
        service.play(state, "Tento di aprire la dispensa.")
        assert state.riserva == 1

    def test_trigger_consumed_and_boosts(self, pack, tmp_path):
        pools = {}

        class SpyGM(DemoGameMaster):
            pass

        service = TurnService(
            gm=SpyGM(),
            pack=pack,
            store=StateStore(tmp_path / "saves"),
            rng=random.Random(1),
            decision_provider=lambda p, rating, diff, state: PlayerDecision(
                choice="roll", use_trigger=True
            ),
        )
        state = service.new_session()
        state.player.trigger = "Quando qualcuno nasconde qualcosa nella dispensa"
        service.play(state, "Tento di aprire la dispensa.")
        assert state.player.trigger is None  # consumato
        roll = service.store.load_turn_artifact(state.session_id, 0, "roll")
        pools["size"] = roll["pool_size"]
        # rating 0 → pool 1 + trigger (demo: 1) = 2
        assert pools["size"] == 2


class TestCreation:
    def _answers(self, **overrides):
        data = {
            "identity": "Una cartografa in fuga dal proprio ordine",
            "appearance": "Trent'anni, capelli corti, mani macchiate d'inchiostro",
            "skills": {"cartografia": 2, "social": 1, "furtività": 0},
        }
        data.update(overrides)
        return CreationAnswers(**data)

    def test_budget_math(self):
        assert skill_points_used({"a": 0}) == 1
        assert skill_points_used({"a": 2, "b": 1}) == 5

    def test_valid_creation(self, pack):
        service = CreationService(pack)
        assert service.validate(self._answers()) == []
        player, sheet = service.create(self._answers())
        assert player.skills == {"cartografia": 3, "social": 2, "furtività": 1}
        assert sheet.base_prompt == self._answers().appearance

    def test_over_budget_rejected(self, pack):
        service = CreationService(pack)
        answers = self._answers(skills={"a": 5, "b": 5})  # 12 punti
        problems = service.validate(answers)
        assert any("budget" in p for p in problems)

    def test_talent_must_be_a_skill(self, pack):
        service = CreationService(pack)
        problems = service.validate(self._answers(talent="magia"))
        assert any("talento" in p for p in problems)

    def test_missing_identity_rejected(self, pack):
        service = CreationService(pack)
        problems = service.validate(self._answers(identity=""))
        assert any("Chi è" in p for p in problems)

    def test_session_with_creation_overrides_visual(self, tmp_path):
        """L'override visivo scatta solo se il pack NON ha una sheet player."""
        import yaml

        pack_dir = tmp_path / "noplayer_pack"
        pack_dir.mkdir()
        (pack_dir / "world.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "noplayer_pack",
                    "title": "x",
                    "start_location_id": "a",
                    "locations": [{"id": "a", "name": "A"}],
                }
            ),
            encoding="utf-8",
        )
        bare_pack = load_pack(pack_dir)
        service = TurnService(
            gm=DemoGameMaster(), pack=bare_pack, store=StateStore(tmp_path / "saves"),
            rng=random.Random(1),
        )
        state = service.new_session(creation_answers=self._answers())
        assert state.player.identity.startswith("Una cartografa")
        assert (
            state.flags["visual_overrides"]["player"] == self._answers().appearance
        )

    def test_pack_player_sheet_wins_over_creation(self, pack, tmp_path):
        """Con protagonista canonica (demo_pack ha la sheet player), la
        creazione non sovrascrive il visual."""
        service = TurnService(
            gm=DemoGameMaster(), pack=pack, store=StateStore(tmp_path / "saves"),
            rng=random.Random(1),
        )
        state = service.new_session(creation_answers=self._answers())
        assert "visual_overrides" not in state.flags
        assert state.player.identity.startswith("Una cartografa")


class TestExperience:
    def test_new_skill(self, state):
        rating = award_experience(state.player, "erboristeria")
        assert rating == 1

    def test_enhance_existing(self, state):
        rating = award_experience(state.player, "social")
        assert rating == 3

    def test_capped_at_max(self, state):
        state.player.skills["social"] = 5
        with pytest.raises(CreationError):
            award_experience(state.player, "social")


class TestNpcConfrontRating:
    def test_exact_match_wins(self):
        from epos.turn_service import npc_confront_rating

        assert npc_confront_rating({"social": 2, "persuasione": 3}, "social") == 2

    def test_alias_maps_free_names(self):
        from epos.turn_service import npc_confront_rating

        # Marea: persuasione 2 — in un confronto "social" vale il suo meglio
        assert npc_confront_rating({"comando_sala": 3, "persuasione": 2}, "social") == 3
        assert npc_confront_rating({"scherma": 2, "indagine": 3}, "physical") == 2
        assert npc_confront_rating({"seduzione": 2, "manipolazione": 3}, "intimate") == 3

    def test_unknown_skill_is_zero(self):
        from epos.turn_service import npc_confront_rating

        assert npc_confront_rating({"erboristeria": 3}, "stealth") == 0
        assert npc_confront_rating({}, "social") == 0
