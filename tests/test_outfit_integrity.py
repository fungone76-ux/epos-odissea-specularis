from epos.models import Outfit, outfit_state


def test_removing_dress_prunes_orphan_descriptors_but_keeps_hosiery():
    outfit = Outfit(
        worn=[
            "fitted ivory VIP attendant mini dress",
            "low neckline",
            "open back",
            "sheer stockings",
            "black pantyhose",
        ]
    )

    outfit.remove_item("fitted ivory VIP attendant mini dress")
    state = outfit_state(outfit)

    assert "fitted ivory VIP attendant mini dress" in state["removed_items"]
    assert "low neckline" not in state["worn_items"]
    assert "open back" not in state["worn_items"]
    assert "sheer stockings" in state["lower_body_slot"]
    assert "black pantyhose" in state["lower_body_slot"]
    assert state["nudity_mode"] == "topless"


def test_invalid_pose_outfit_never_enters_canonical_state():
    outfit = Outfit()

    outfit.wear("provocative pose outfit")

    assert outfit.worn == []
    assert outfit.removed == []
    assert outfit.revision == 0


def test_loading_corrupted_outfit_repairs_pseudo_items_and_orphan_descriptors():
    outfit = Outfit.from_dict(
        {
            "worn": [
                "low neckline",
                "open back",
                "black pantyhose",
                "provocative pose outfit",
            ],
            "removed": [
                "fitted ivory VIP attendant mini dress",
                "provocative pose outfit",
            ],
            "revision": 4,
        }
    )
    state = outfit_state(outfit)

    assert state["worn_items"] == ["black pantyhose"]
    assert state["removed_items"] == ["fitted ivory VIP attendant mini dress"]
    assert state["lower_body_slot"] == ["black pantyhose"]
    assert state["nudity_mode"] == "topless"
    assert state["revision"] == 4


def test_descriptors_remain_while_real_torso_garment_is_worn():
    outfit = Outfit(
        worn=[
            "fitted ivory VIP attendant mini dress",
            "low neckline",
            "open back",
        ]
    )

    state = outfit_state(outfit)

    assert "low neckline" in state["worn_items"]
    assert "open back" in state["worn_items"]
    assert state["nudity_mode"] == "clothed"
