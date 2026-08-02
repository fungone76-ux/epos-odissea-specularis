from pathlib import Path
from types import SimpleNamespace

from epos.contract import FinalScene
from epos.resort_runtime import load_resort_pack, new_resort_world
from epos.resort_schedule import (
    NPC_IDS,
    PHASES,
    apply_resort_schedule,
    load_resort_schedule_config,
    record_outfit_overrides_from_turn,
    schedule_key,
)

PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def test_schedule_and_wardrobe_cover_all_seven_days_and_phases():
    pack = load_resort_pack(PACK_DIR)
    config = load_resort_schedule_config(PACK_DIR, pack.world)

    for npc_id in NPC_IDS:
        assert set(config.schedules[npc_id]) == set(range(1, 8))
        assert set(config.wardrobes[npc_id]) == set(range(1, 8))
        for day in range(1, 8):
            assert set(config.schedules[npc_id][day]) == set(PHASES)
            assert set(config.wardrobes[npc_id][day]) == set(PHASES)


def test_no_npc_repeats_the_same_complete_day_pattern():
    pack = load_resort_pack(PACK_DIR)
    config = load_resort_schedule_config(PACK_DIR, pack.world)

    for npc_id in NPC_IDS:
        signatures = []
        for day in range(1, 8):
            signature = tuple(
                (
                    config.schedules[npc_id][day][phase],
                    config.wardrobes[npc_id][day][phase],
                )
                for phase in PHASES
            )
            signatures.append(signature)
        assert len(signatures) == len(set(signatures))


def test_all_scheduled_outfits_match_location_and_revealing_style_contract():
    pack = load_resort_pack(PACK_DIR)
    config = load_resort_schedule_config(PACK_DIR, pack.world)

    # Vocabolario semantico ammesso dal guardaroba canonico. Il contratto non
    # richiede una singola parola specifica: basta almeno un descrittore che
    # renda l'outfit aderente, rivelante o esplicitamente sensuale.
    revealing_terms = (
        "bodycon", "fitted", "mini", "micro", "deep neckline", "plunging",
        "low neckline", "low cut", "backless", "open back", "high slit",
        "thigh slit", "slit dress", "slit gown", "cutout", "lingerie",
        "bikini", "swimsuit", "one piece", "sheer", "mesh", "lace",
        "loosely tied", "corset", "sculpted bodice", "slip", "off shoulder",
        "halter", "bandeau", "high cut", "tiny bottoms", "string bikini",
        "no blouse", "very short hem", "open shirt", "crop cover up",
    )
    swim_locations = {"loc_pool", "loc_private_beach", "loc_wild_beach"}

    for npc_id in NPC_IDS:
        for day in range(1, 8):
            for phase in PHASES:
                location_id = config.schedules[npc_id][day][phase]
                outfit = " ".join(config.wardrobes[npc_id][day][phase]).lower()

                assert any(term in outfit for term in revealing_terms), (
                    npc_id, day, phase, location_id, outfit
                )
                if location_id in swim_locations:
                    assert any(
                        term in outfit
                        for term in ("bikini", "swimsuit", "one piece")
                    ), (npc_id, day, phase, location_id, outfit)
                if location_id == "loc_spa":
                    assert any(
                        term in outfit for term in ("spa robe", "spa tunic", "spa wrap")
                    ), (npc_id, day, phase, location_id, outfit)


def test_luna_day_two_afternoon_private_beach_outfit_is_revealing_beachwear():
    pack = load_resort_pack(PACK_DIR)
    config = load_resort_schedule_config(PACK_DIR, pack.world)

    assert config.schedules["luna"][2]["pomeriggio"] == "loc_private_beach"
    assert config.wardrobes["luna"][2]["pomeriggio"] == (
        "pale blue string bikini",
        "sheer white sarong",
        "shell necklace",
        "barefoot",
    )


def test_schedule_updates_location_outfit_and_presence_for_current_period():
    pack = load_resort_pack(PACK_DIR)
    config = load_resort_schedule_config(PACK_DIR, pack.world)
    state = new_resort_world(pack, "schedule-apply")
    state.flags["resort_day"] = 3
    state.time_phase = "pomeriggio"
    state.location_id = "loc_spa"
    state.player.location_id = "loc_spa"

    changes = apply_resort_schedule(state, config, previous_key="3:mattina")

    assert changes
    assert state.npcs["stella"].location_id == "loc_spa"
    assert state.npcs["stella"].present is True
    assert state.npcs["luna"].location_id == "loc_spa"
    assert state.npcs["luna"].present is True
    assert state.npcs["victoria"].present is False
    assert state.npcs["stella"].outfit.worn == list(
        config.wardrobes["stella"][3]["pomeriggio"]
    )


def test_outfit_override_is_kept_in_current_period_and_expires_next_period():
    pack = load_resort_pack(PACK_DIR)
    config = load_resort_schedule_config(PACK_DIR, pack.world)
    state = new_resort_world(pack, "schedule-outfit-lock")
    state.flags["resort_day"] = 2
    state.time_phase = "sera"
    state.npcs["luna"].outfit.worn = ["black lace lingerie", "sheer black stockings"]

    scene = FinalScene.from_dict(
        {
            "narration": "Luna indossa l'outfit concordato.",
            "dialogue": [],
            "npc_actions": [{"npc_id": "luna", "action": "changes outfit"}],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [
                {
                    "type": "outfit_wear",
                    "target": "luna",
                    "payload": {"item": "black lace lingerie"},
                    "reason": "Richiesta accettata.",
                }
            ],
            "memory_events": [],
            "visual": None,
        }
    )
    record_outfit_overrides_from_turn(state, SimpleNamespace(scene=scene))
    assert state.flags["resort_outfit_override_until"]["luna"] == schedule_key(state)

    apply_resort_schedule(state, config, previous_key="2:pomeriggio")
    assert state.npcs["luna"].outfit.worn == [
        "black lace lingerie",
        "sheer black stockings",
    ]

    state.time_phase = "notte"
    apply_resort_schedule(state, config, previous_key="2:sera")
    assert state.npcs["luna"].outfit.worn == list(
        config.wardrobes["luna"][2]["notte"]
    )
