from types import SimpleNamespace

from epos.models import Outfit
from epos.resort_playable_turn_service import _hosiery_scene


def _state_with_outfit(worn):
    npc = SimpleNamespace(
        name="Victoria Hale",
        outfit=Outfit(worn=list(worn), removed=[]),
    )
    return SimpleNamespace(
        location_id="loc_suite",
        npcs={"victoria": npc},
    )


def _pack():
    return SimpleNamespace(
        locations={"loc_suite": SimpleNamespace(name="suite presidenziale")}
    )


def _mutation_pairs(scene):
    return [
        (mutation.type, mutation.payload.get("item"))
        for mutation in scene.mutations
    ]


def test_hosiery_scene_removes_canonical_footwear_and_wears_requested_item():
    state = _state_with_outfit(
        ["luxury travel suit", "black stilettos"]
    )

    scene = _hosiery_scene(_pack(), state, "victoria", "black pantyhose")

    assert _mutation_pairs(scene) == [
        ("outfit_remove", "black stilettos"),
        ("outfit_wear", "black pantyhose"),
    ]


def test_hosiery_scene_does_not_add_duplicate_hosiery():
    state = _state_with_outfit(
        ["luxury travel suit", "black stilettos", "black pantyhose"]
    )

    scene = _hosiery_scene(_pack(), state, "victoria", "black pantyhose")

    assert _mutation_pairs(scene) == [
        ("outfit_remove", "black stilettos"),
    ]
