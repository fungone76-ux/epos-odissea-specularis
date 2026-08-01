"""Test dell'engine Odissea Specularis."""

import sys
from pathlib import Path

import pytest

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from epos.odyssey_engine import OdysseyEngine, MISSIONS, LOCATION_ORDER


@pytest.fixture
def engine():
    pack_dir = Path(__file__).parent.parent / "worlds" / "odyssey_specularis"
    return OdysseyEngine(pack_dir)


def test_load_pack():
    pack_dir = Path(__file__).parent.parent / "worlds" / "odyssey_specularis"
    engine = OdysseyEngine(pack_dir)
    status = engine.game_status()
    assert status["location"]["id"] == "loc_ciclopi"
    assert status["player"]["name"] == "Ulisse"
    assert status["player"]["skills"]["dolos"] == 4
    assert status["player"]["skills"]["sarissa"] == 3
    print("✓ Pack caricato correttamente")
    return engine


def test_ciclopi_dolos(engine):
    """Test missione Ciclopi con Dolos."""
    result = engine.attempt_mission(skill_choice="dolos")
    print(f"  Ciclopi (Dolos): pool={result.pool_size}, diff={result.difficulty}, dice={result.dice}, outcome={result.outcome.value}")
    print(f"  Success: {result.success}, Message: {result.message}")
    if result.success:
        print(f"  Kleos: {result.kleos_gained}, Next location: {engine.current_location_id()}")
    return result.success


def test_full_run_simulation():
    """Simula una partita completa con tiri casuali."""
    pack_dir = Path(__file__).parent.parent / "worlds" / "odyssey_specularis"
    engine = OdysseyEngine(pack_dir)

    print("\n=== SIMULAZIONE PARTITA ===")
    print(f"Player: {engine.state.player.name}")
    print(f"Skills: {dict(engine.state.player.skills)}")
    print()

    max_turns = 50
    for turn in range(max_turns):
        if engine.state.flags.get("game_over", False):
            break

        loc_id = engine.current_location_id()
        mission = MISSIONS[loc_id]
        status = engine.game_status()

        print(f"--- Turno {turn+1} | Location: {mission.name} ({loc_id}) ---")
        print(f"  Skills attuali: {status['player']['skills']}")
        print(f"  Kleos: {status['player']['kleos']}")
        print(f"  Effetti attivi: {status['active_effects']}")

        # Scegli skill
        skill = mission.primary_skill
        if mission.alternative_skill:
            # Scegli quella con rating più alto
            p_rating = engine.state.player.skill_rating(mission.primary_skill)
            a_rating = engine.state.player.skill_rating(mission.alternative_skill)
            if a_rating > p_rating:
                skill = mission.alternative_skill

        # Special: Calipso auto-pass se possibile
        use_auto = False
        if loc_id == "loc_calipso" and engine.check_calipso_auto_pass():
            use_auto = True
            print("  >>> Auto-pass Calipso attivato (Kleos >= 4)")

        # Special: Moly a Circe
        use_moly = False
        if loc_id == "loc_circe" and engine.state.flags.get("moly_possessed", False):
            use_moly = True
            print("  >>> Moly usato contro Circe")

        # Tenta missione
        result = engine.attempt_mission(
            skill_choice=skill,
            use_moly=use_moly,
            use_auto_pass=use_auto,
        )

        print(f"  Tiro: {result.skill_used} | Pool: {result.pool_size} | Diff: {result.difficulty}")
        print(f"  Dadi: {result.dice} | Outcome: {result.outcome.value}")
        print(f"  Success: {result.success}")
        if result.special_triggered:
            print(f"  Special: {result.special_triggered}")
        if result.permanent_penalty:
            print(f"  Penalità: {result.permanent_penalty}")
        print(f"  {result.message}")
        print()

        engine.next_turn()

    final = engine.game_status()
    print("\n=== FINE PARTITA ===")
    print(f"Vittoria: {final['victory']}")
    print(f"Game Over: {final['game_over']}")
    print(f"Kleos finale: {final['player']['kleos']}")
    print(f"Skills finali: {final['player']['skills']}")
    print(f"Location finale: {engine.current_location_id()}")


def test_save_load():
    """Test salvataggio e caricamento."""
    pack_dir = Path(__file__).parent.parent / "worlds" / "odyssey_specularis"
    engine = OdysseyEngine(pack_dir)

    # Fai un tiro
    engine.attempt_mission(skill_choice="dolos")
    engine.next_turn()

    # Salva
    save_path = Path("/tmp/odyssey_test_save.json")
    engine.save(save_path)
    print(f"✓ Salvato in {save_path}")

    # Carica
    engine2 = OdysseyEngine.load(save_path, pack_dir)
    assert engine2.state.turn == engine.state.turn
    assert engine2.current_location_id() == engine.current_location_id()
    print(f"✓ Caricato correttamente, turno {engine2.state.turn}")


if __name__ == "__main__":
    print("=== TEST ODYSSEY ENGINE ===\n")

    engine = test_load_pack()

    print("\n--- Test missione Ciclopi ---")
    test_ciclopi_dolos(engine)

    print("\n--- Test salvataggio ---")
    test_save_load()

    print("\n--- Test simulazione completa ---")
    test_full_run_simulation()

    print("\n=== TUTTI I TEST COMPLETATI ===")
