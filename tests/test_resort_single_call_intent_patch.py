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


def _requirements(hint):
    return {(item.kind, item.value) for item in hint.visual_requirements}


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


def test_explicit_body_part_request_becomes_mandatory_visual_requirement():
    hint = interpret_resort_intent(_Pack(), _State(), "Luna, mostrami i piedi")
    requirements = _requirements(hint)
    assert hint.target_npc == "luna"
    assert ("body_part", "feet") in requirements
    assert ("visibility", "clear_and_unobstructed") in requirements
    assert ("framing", "must_include_all_requested_elements") in requirements


def test_visual_intent_is_generic_for_pose_orientation_and_camera():
    hint = interpret_resort_intent(
        _Pack(),
        _State(),
        "Luna girati di schiena, siediti e fammi vedere il tatuaggio da vicino",
    )
    requirements = _requirements(hint)
    assert ("orientation", "back_view") in requirements
    assert ("pose", "sitting") in requirements
    assert ("body_part", "tattoo") in requirements
    assert ("camera", "close_up") in requirements


def test_visual_intent_supports_outfit_and_full_body_composition():
    hint = interpret_resort_intent(
        _Pack(),
        _State(),
        "Fammi vedere il vestito a figura intera",
    )
    requirements = _requirements(hint)
    assert ("outfit", "outfit") in requirements
    assert ("camera", "full_body") in requirements
