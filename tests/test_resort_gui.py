from pathlib import Path

from epos.resort_gui import build_resort_gui_status
from epos.resort_relationships import apply_player_relationship_delta
from epos.resort_runtime import load_resort_pack, new_resort_world


PACK_DIR = Path(__file__).resolve().parents[1] / "worlds" / "resort_world"


def test_resort_gui_status_contains_campaign_information():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "gui-status")

    status = build_resort_gui_status(state, pack)

    assert status["day"] == 1
    assert status["phase"] == "mattina"
    assert status["location_name"] == "Lobby"
    assert status["score"] == 0
    assert status["score_tier"] == "soggiorno_fallimentare"
    assert status["days_left"] == 6
    assert status["debt_due"] is False
    assert {mission["id"] for mission in status["missions"]} == {
        "mission_resort_future"
    }
    assert set(status["present_npcs"]) == {
        "Victoria Hale",
        "Stella",
        "Maria",
        "Luna",
    }


def test_resort_gui_status_reads_relationships_and_eligible_events():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "gui-relations")
    apply_player_relationship_delta(state, "maria", trust=2, attraction=1)
    state.location_id = "loc_suite"
    state.player.location_id = "loc_suite"
    state.time_phase = "sera"

    status = build_resort_gui_status(state, pack)

    assert "Il bagno per due" in status["eligible_events"]
    assert status["relationships"]["maria"]["trust"] == 2
    assert status["relationships"]["maria"]["attraction"] == 1


def test_resort_gui_status_does_not_reveal_locked_personal_missions():
    pack = load_resort_pack(PACK_DIR)
    state = new_resort_world(pack, "gui-hidden-missions")

    status = build_resort_gui_status(state, pack)
    visible_ids = {mission["id"] for mission in status["missions"]}

    assert "mission_luna_letter" not in visible_ids
    assert "mission_maria_stability" not in visible_ids
    assert "mission_stella_promotion" not in visible_ids
