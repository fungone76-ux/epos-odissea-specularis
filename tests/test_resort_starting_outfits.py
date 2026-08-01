from pathlib import Path

from epos.resort_runtime import load_resort_pack, new_resort_world


PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"

EXPECTED_STARTING_OUTFITS = {
    "victoria": (
        "black bodycon blazer mini dress",
        "deep neckline",
        "sheer black stockings",
        "black stilettos",
        "elegant jewelry",
    ),
    "stella": (
        "fitted resort hostess micro dress",
        "plunging neckline",
        "very short hem",
        "sheer stockings",
        "gold name tag",
        "high heels",
    ),
    "maria": (
        "fitted luxury maid mini dress",
        "deep neckline",
        "white lace trim",
        "sheer stockings",
        "high heels",
    ),
    "luna": (
        "fitted ivory VIP attendant mini dress",
        "low neckline",
        "open back",
        "sheer stockings",
        "delicate high heels",
    ),
}


def test_narrative_and_visual_starting_outfits_are_aligned():
    pack = load_resort_pack(PACK_DIR)

    for npc_id, expected in EXPECTED_STARTING_OUTFITS.items():
        assert tuple(pack.world.npc_canon[npc_id].starting_outfit) == expected
        assert pack.world.visual_sheets[npc_id].starting_outfit_en == expected


def test_new_resort_session_uses_visual_canonical_starting_outfits():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "starting-outfits")

    for npc_id, expected in EXPECTED_STARTING_OUTFITS.items():
        assert tuple(state.npcs[npc_id].outfit.worn) == expected
