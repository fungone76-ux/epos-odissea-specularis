from __future__ import annotations

from epos.visual import _character_gender, _count_anchor_tag, _position_tags


def test_character_gender_reads_canonical_count_tags():
    assert _character_gender("score_9, 1girl, dark hair") == "girl"
    assert _character_gender("score_9, 1woman, dark hair") == "girl"
    assert _character_gender("score_9, 1boy, cloak") == "boy"
    assert _character_gender("score_9, 1man, cloak") == "boy"
    assert _character_gender("score_9, portrait subject") is None


def test_count_anchor_tag_single_two_three_and_unknown_subjects():
    base = {
        "player": "score_9, 1girl, olive skin",
        "maera": "score_9, 1woman, grey apron",
        "corren": "score_9, 1man, stable coat",
        "unknown": "score_9, cloaked figure",
    }

    assert _count_anchor_tag(["player"], base) == "1girl"
    assert _count_anchor_tag(["player", "maera"], base) == "2girls"
    assert _count_anchor_tag(["player", "corren"], base) == "1girl and 1boy"
    assert _count_anchor_tag(["player", "maera", "corren"], base) == (
        "3people, 2girls, 1boy"
    )
    assert _count_anchor_tag(["player", "unknown"], base) == "2people"


def test_position_tags_are_stable_for_common_multi_character_counts():
    assert _position_tags(0) == []
    assert _position_tags(1) == ["position 1"]
    assert _position_tags(2) == ["on the left", "on the right"]
    assert _position_tags(3) == ["on the left", "in the center", "on the right"]
    assert _position_tags(4) == [
        "on the far left",
        "on the left",
        "on the right",
        "on the far right",
    ]
    assert _position_tags(5) == [
        "position 1",
        "position 2",
        "position 3",
        "position 4",
        "position 5",
    ]
