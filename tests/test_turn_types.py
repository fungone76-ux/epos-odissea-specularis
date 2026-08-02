from epos.turn_service import (
    PlayerDecision,
    TurnResult,
    default_decision,
    default_narration,
    default_post_turn_processor,
    default_split,
    default_temerario,
    npc_confront_rating,
)



def test_turn_modules_reexport_facade_symbols():
    from epos import turn_resolution, turn_service, turn_types

    assert turn_service.PlayerDecision is turn_types.PlayerDecision
    assert turn_service.TurnResult is turn_types.TurnResult
    assert turn_service.default_decision is turn_types.default_decision
    assert turn_service.npc_confront_rating is turn_resolution.npc_confront_rating

def test_turn_service_facade_exports_decision_defaults():
    decision = PlayerDecision()

    assert decision.choice == "roll"
    assert decision.use_riserva is False
    assert decision.dado_temerario_price is None
    assert decision.use_trigger is False


def test_default_turn_providers_preserve_legacy_values():
    assert default_decision(None, 0, 0, None) == PlayerDecision()
    assert default_narration("context") == ""
    assert default_split(None, 3, 2) == 3
    assert default_temerario(None) is None
    assert default_post_turn_processor(None, None) is None


def test_turn_result_defaults_are_independent_containers():
    first = TurnResult(turn=0, mode="no_check", narration="ok")
    second = TurnResult(turn=1, mode="check", narration="ok")

    first.dialogue.append({"speaker": "gm", "text": "ciao"})
    first.scene_mutations.append({"type": "note"})
    first.campaign_changes["x"] = 1

    assert second.dialogue == []
    assert second.scene_mutations == []
    assert second.campaign_changes == {}
    assert second.resumed is False


def test_npc_confront_rating_exact_alias_and_unknown():
    skills = {
        "social": 2,
        "persuasione": 3,
        "manipolazione": 4,
        "scherma": 5,
    }

    assert npc_confront_rating(skills, "social") == 2
    assert npc_confront_rating(skills, "intimate") == 4
    assert npc_confront_rating(skills, "physical") == 5
    assert npc_confront_rating(skills, "unknown") == 0
