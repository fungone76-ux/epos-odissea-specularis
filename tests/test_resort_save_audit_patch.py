from types import SimpleNamespace

from epos.models import Outfit, outfit_state
from epos.resort_save_audit_patch import (
    _placeholder_target_with_stale_presence,
    _scene_has_real_npc_participation,
    reconcile_resort_presence,
)


class FakeState:
    def __init__(self, *, location_id, npcs, last_scene=""):
        self.location_id = location_id
        self.npcs = npcs
        self.last_scene = last_scene

    def present_npc_ids(self):
        return [npc_id for npc_id, npc in self.npcs.items() if npc.present]


def _npc(name, location_id, present=False):
    return SimpleNamespace(
        name=name,
        location_id=location_id,
        present=present,
    )


def _visual(**overrides):
    values = {
        "summary": "",
        "visual_en": "",
        "tags_en": [],
        "speaker_character": "",
        "actor_character": "",
        "reactor_character": "",
        "focus_character": "",
        "visible_characters": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _scene(**overrides):
    values = {
        "narration": "",
        "dialogue": [],
        "npc_actions": [],
        "initiatives": [],
        "visual": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_reconciles_single_same_location_npc_from_turn_12_state():
    state = FakeState(
        location_id="loc_wild_beach",
        npcs={"luna": _npc("Luna", "loc_wild_beach", present=False)},
        last_scene="Luna si gira lentamente sulla spiaggia selvaggia.",
    )

    assert reconcile_resort_presence(state, "raccontami di te") == "luna"
    assert state.npcs["luna"].present is True


def test_resolves_npc_id_placeholder_to_unambiguous_luna():
    state = FakeState(
        location_id="loc_wild_beach",
        npcs={"luna": _npc("Luna", "loc_wild_beach", present=False)},
        last_scene="Luna è con il giocatore sulla spiaggia.",
    )
    scene = _scene(
        narration="Luna inizia a raccontare qualcosa di sé.",
        visual=_visual(
            focus_character="npc_id",
            visible_characters=["npc_id"],
            visual_en="Luna speaking on a wild Mediterranean beach",
        ),
    )

    assert _placeholder_target_with_stale_presence(state, scene) == "luna"
    assert state.npcs["luna"].present is True


def test_visual_actor_counts_as_real_npc_reaction_for_turn_11_shape():
    state = FakeState(
        location_id="loc_suite",
        npcs={"maria": _npc("Maria", "loc_suite", present=True)},
    )
    scene = _scene(
        narration="Maria si avvicina lentamente.",
        visual=_visual(
            focus_character="maria",
            actor_character="maria",
            visible_characters=["maria"],
        ),
    )

    assert _scene_has_real_npc_participation(state, scene) is True


def test_luxury_travel_suit_is_not_bottomless():
    state = outfit_state(
        Outfit(
            worn=["luxury travel suit", "tailored shirt", "elegant shoes"],
            removed=[],
        )
    )

    assert state["torso_slot"]
    assert state["lower_body_slot"]
    assert state["nudity_mode"] == "clothed"
