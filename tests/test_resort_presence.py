from types import SimpleNamespace

from epos.contract import FinalScene
from epos.entity_ids import normalize_scene_entity_ids
from epos.models import Outfit, outfit_state
from epos.resort_presence import (
    scene_has_real_npc_participation,
    reconcile_resort_presence,
)


class FakeState:
    def __init__(self, *, location_id, npcs, last_scene=""):
        self.location_id = location_id
        self.npcs = npcs
        self.last_scene = last_scene
        self.player = SimpleNamespace(name=None)

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
        "summary": "Una NPC reagisce nella scena.",
        "visual_en": "A resort NPC reacts clearly in the current location.",
        "tags_en": ["NPC reaction"],
        "speaker_character": "",
        "actor_character": "",
        "reactor_character": "",
        "focus_character": "",
        "visible_characters": [],
        "shared_action": False,
        "moment_type": "action",
        "intimate_shared_moment": False,
        "multi_character_reason": "",
        "multi_character_participants": [],
    }
    values.update(overrides)
    return values


def _scene(**overrides):
    values = {
        "narration": "",
        "dialogue": [],
        "npc_actions": [],
        "intentions": [],
        "initiatives": [],
        "disclosure_events": [],
        "mutations": [],
        "memory_events": [],
        "visual": None,
    }
    values.update(overrides)
    return FinalScene.from_dict(values)


def test_reconciles_single_same_location_npc_from_turn_12_state():
    state = FakeState(
        location_id="loc_wild_beach",
        npcs={"luna": _npc("Luna", "loc_wild_beach", present=False)},
        last_scene="Luna si gira lentamente sulla spiaggia selvaggia.",
    )

    assert reconcile_resort_presence(state, "raccontami di te") == "luna"
    assert state.npcs["luna"].present is True


def test_reconciliation_then_canonical_normalizer_resolves_npc_id_placeholder():
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

    assert reconcile_resort_presence(state, "raccontami di te") == "luna"
    result = normalize_scene_entity_ids(state, scene, phase="test")

    assert result.value.visual.focus_character == "luna"
    assert result.value.visual.visible_characters == ["luna"]
    assert any(entry.alias_rule == "scene_placeholder_npc_id" for entry in result.entries)


def test_visual_actor_counts_as_real_npc_reaction_for_turn_11_shape():
    state = FakeState(
        location_id="loc_suite",
        npcs={"maria": _npc("Maria", "loc_suite", present=True)},
    )
    scene = _scene(
        narration="Maria si avvicina lentamente.",
        visual=_visual(
            summary="Maria si avvicina nella suite.",
            visual_en="Maria approaches slowly inside the luxury suite.",
            tags_en=["Maria", "approaching", "luxury suite"],
            focus_character="maria",
            actor_character="maria",
            visible_characters=["maria"],
        ),
    )

    assert scene_has_real_npc_participation(state, scene) is True


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
