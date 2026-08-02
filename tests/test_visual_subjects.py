from __future__ import annotations

from epos.contract import VisualMoment
from epos.visual import (
    _first_present,
    _focus_for_policy,
    _validated_intimate_participants,
    build_visual_contract,
)
from epos.worldpack import load_pack


PACK = "tests/fixtures/demo_pack"


def _moment(**overrides) -> VisualMoment:
    data = {
        "summary": "subject test",
        "focus_character": "player",
        "visible_characters": ["player"],
        "shared_action": False,
        "moment_type": "action",
        "visual_en": "a deterministic visual moment",
        "tags_en": [],
        "speaker_character": "",
        "actor_character": "player",
        "reactor_character": "",
        "intimate_shared_moment": False,
        "multi_character_reason": "",
        "multi_character_participants": [],
    }
    data.update(overrides)
    return VisualMoment.from_dict(data)


def test_first_present_returns_first_candidate_in_present_set():
    assert _first_present(["corren", "maera", "player"], {"player", "maera"}) == "maera"


def test_first_present_handles_empty_and_absent_candidates():
    assert _first_present(["", "corren"], {"player", "maera"}) is None
    assert _first_present([], {"player"}) is None


def test_focus_for_policy_uses_present_speaker_and_falls_back_when_absent():
    present = {"player", "maera"}

    assert _focus_for_policy(
        _moment(
            moment_type="speech",
            speaker_character="maera",
            visible_characters=["player", "maera"],
            shared_action=True,
        ),
        present,
    ) == ("maera", "speaker")

    assert _focus_for_policy(
        _moment(
            moment_type="speech",
            speaker_character="corren",
            visible_characters=["player"],
        ),
        present,
    ) == ("player", "explicit_visual_focus")


def test_focus_for_policy_prefers_actor_or_reactor_by_moment_type():
    present = {"player", "maera"}

    assert _focus_for_policy(
        _moment(moment_type="action", actor_character="maera", reactor_character="player"),
        present,
    ) == ("maera", "actor")
    assert _focus_for_policy(
        _moment(moment_type="reaction", actor_character="maera", reactor_character="player"),
        present,
    ) == ("player", "reactor")


def test_validated_intimate_participants_filters_absent_and_dedupes_in_order():
    visual = _moment(
        moment_type="intimate",
        visible_characters=["player", "maera", "corren"],
        shared_action=True,
        intimate_shared_moment=True,
        multi_character_reason="shared_intimate_focus",
        multi_character_participants=["maera", "player", "maera", "corren"],
    )

    participants, reason = _validated_intimate_participants(visual, {"player", "maera"})

    assert participants == ["maera", "player"]
    assert reason == "shared_intimate_focus"


def test_validated_intimate_participants_rejects_missing_or_non_intimate_data():
    assert _validated_intimate_participants(
        _moment(
            moment_type="intimate",
            visible_characters=["player", "maera"],
            shared_action=True,
            intimate_shared_moment=True,
            multi_character_participants=["maera", "corren"],
        ),
        {"player"},
    ) == ([], "not_validated_intimate_shared_moment")

    assert _validated_intimate_participants(
        _moment(
            moment_type="action",
            visible_characters=["player", "maera"],
            shared_action=True,
            intimate_shared_moment=True,
            multi_character_participants=["player", "maera"],
        ),
        {"player", "maera"},
    ) == ([], "not_validated_intimate_shared_moment")


def test_speaker_action_focus_policy_disabled_preserves_llm_focus():
    pack = load_pack(PACK)
    state = pack.new_world("visual-subjects-policy-off")

    contract = build_visual_contract(
        state,
        pack,
        _moment(
            focus_character="player",
            visible_characters=["player", "maera"],
            shared_action=True,
            moment_type="speech",
            speaker_character="maera",
        ),
        0,
    )

    assert contract.focus_character == "player"
    assert contract.focus_reason == "llm_focus"
