from types import SimpleNamespace

from epos.resort_single_call_intent_patch import interpret_resort_intent


class _State:
    def __init__(self):
        self.npcs = {
            "luna": SimpleNamespace(name="Luna", present=True),
            "maria": SimpleNamespace(name="Maria", present=False),
        }

    def present_npc_ids(self):
        return [npc_id for npc_id, npc in self.npcs.items() if npc.present]


class _Pack:
    def __init__(self):
        self.locations = {
            "loc_suite": object(),
            "loc_lobby": object(),
            "loc_private_beach": object(),
            "loc_wild_beach": object(),
            "loc_pool": object(),
            "loc_spa": object(),
            "loc_restaurant": object(),
            "loc_lounge": object(),
            "loc_victoria_office": object(),
        }


def test_ask_about_self_targets_single_present_npc():
    hint = interpret_resort_intent(_Pack(), _State(), "Luna, raccontami di te")
    assert hint.intent == "ask_npc_about_self"
    assert hint.target_npc == "luna"
    assert hint.requires_npc_response is True
    assert hint.visual_focus == "luna"


def test_social_request_requires_target_response():
    hint = interpret_resort_intent(_Pack(), _State(), "avvicinati")
    assert hint.intent == "interact_with_npc"
    assert hint.target_npc == "luna"
    assert hint.requires_npc_response is True


def test_wild_beach_beats_generic_beach_alias():
    hint = interpret_resort_intent(_Pack(), _State(), "vado in spiaggia selvaggia")
    assert hint.intent == "move"
    assert hint.location_target == "loc_wild_beach"
    assert hint.requires_location_change is True
    assert hint.requires_visual is False


def test_generic_beach_maps_to_private_beach():
    hint = interpret_resort_intent(_Pack(), _State(), "vorrei andare in spiaggia")
    assert hint.location_target == "loc_private_beach"


def test_relax_with_single_present_npc_requires_response():
    hint = interpret_resort_intent(_Pack(), _State(), "mi rilasso un po'")
    assert hint.intent == "relax"
    assert hint.target_npc == "luna"
    assert hint.requires_npc_response is True
