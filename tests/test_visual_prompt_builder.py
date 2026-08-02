from __future__ import annotations

from dataclasses import dataclass

from epos.visual import (
    _dedupe_scene_tags_for_pack,
    _dedupe_visual_against_outfit_for_pack,
    _join_nonempty,
)


@dataclass
class _Policy:
    dedupe_across_layers: bool = True
    max_scene_tags: int = 0


@dataclass
class _Pack:
    visual_policy: _Policy


def test_join_nonempty_discards_empty_chunks_and_preserves_order():
    assert _join_nonempty([" base ", "", "  ", "tag", " visual "]) == "base, tag, visual"


def test_scene_tag_dedupe_policy_disabled_is_noop():
    pack = _Pack(_Policy(dedupe_across_layers=False))
    tags = ["chiton", "wild coast", ""]

    kept, removed = _dedupe_scene_tags_for_pack(
        tags, ["very short crimson wool chiton"], "wild coast", pack
    )

    assert kept == tags
    assert removed == []


def test_scene_tag_dedupe_keeps_semantically_distinct_terms():
    pack = _Pack(_Policy())

    kept, removed = _dedupe_scene_tags_for_pack(
        ["bronze bow", "bowing posture", "wild coast"],
        ["recurved bow with bronze tips"],
        "figure bowing before the surf",
        pack,
    )

    assert kept == ["bowing posture", "wild coast"]
    assert removed == ["bronze bow"]


def test_visual_dedupe_against_outfit_policy_disabled_is_noop():
    pack = _Pack(_Policy(dedupe_across_layers=False))
    visual = "wearing a chiton, standing near the surf"

    kept, removed = _dedupe_visual_against_outfit_for_pack(
        visual, ["very short crimson wool chiton"], pack
    )

    assert kept == visual
    assert removed == []
