"""Test di regressione per gli 8 fix critici — Odissea Specularis.

1. GM propone solo skill rilevanti per la missione (con hint esplicito)
2. Tracker avvisa della skill sbagliata
3. GUI: diff nominale + effettiva (retry offset) — verifica lato status
4. GUI: log ultime 3 azioni — verifica lato status
5. Poseidon's Curse e Wind Bag applicati alla difficoltà Pontos
6. Itaca a 3 fasi (dolos -> sarissa -> eros)
7. Nave Feacia: auto-pass del primo tiro di Itaca
8. TurnService passa choice a narrate()
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from epos.worldpack import load_pack
from epos.contract import CheckProposal
from epos.rules import Roll, Outcome, resolve_check
from epos.turn_service import TurnResult
from epos.odyssey_mission_tracker import OdysseyMissionTracker, MISSIONS, LOCATION_ORDER
from epos.odyssey_gm import OdysseyDemoGameMaster

PACK = Path(__file__).parent.parent / "worlds" / "odyssey_specularis"


@pytest.fixture
def env():
    pack = load_pack(PACK)
    state = pack.new_world()
    return pack, state, OdysseyMissionTracker(state), OdysseyDemoGameMaster()


def make_result(skill, outcome, difficulty=3, target_ids=None, stake="", scene_mutations=None):
    return TurnResult(
        turn=1, mode="check", narration="test",
        proposal=CheckProposal(
            action_kind=skill,
            skill=skill,
            difficulty=difficulty,
            target_ids=list(target_ids or []),
        ),
        roll=Roll(pool_size=5, difficulty=difficulty, dice=(6, 6), outcome=outcome),
        stake=stake,
        scene_mutations=list(scene_mutations or []),
    )


def goto(state, loc_id):
    state.flags["odyssey_location_index"] = LOCATION_ORDER.index(loc_id)


# -- FIX 1 ------------------------------------------------------------------

def test_gm_propone_solo_skill_rilevanti(env):
    pack, state, tracker, gm = env
    resp = gm.propose(state, pack, "Resisto alla curiosità e stringo i pugni")
    assert resp.check.skill in ("dolos", "sarissa")


def test_gm_hint_su_skill_sbagliata(env):
    pack, state, tracker, gm = env
    resp = gm.propose(state, pack, "Resisto alla curiosità e stringo i pugni")
    assert "THUMOS" in resp.check.reason
    assert "richiede" in resp.check.reason


# -- FIX 2 ------------------------------------------------------------------

def test_tracker_avvisa_skill_sbagliata(env):
    pack, state, tracker, gm = env
    changes = tracker.process_turn(make_result("thumos", Outcome.FULL_SUCCESS))
    assert changes.get("wrong_skill") is True
    assert "THUMOS" in changes["message"]
    assert "Nessun progresso" in changes["message"]


# -- FIX 5 ------------------------------------------------------------------

def test_poseidon_curse_aumenta_difficolta_pontos(env):
    pack, state, tracker, gm = env
    goto(state, "loc_scilla_cariddi")
    base = MISSIONS["loc_scilla_cariddi"].difficulty
    state.flags["poseidon_curse_active"] = True
    resp = gm.propose(state, pack, "navigo attraverso lo stretto")
    assert resp.check.difficulty == base + 1


def test_wind_bag_riduce_difficolta_pontos(env):
    pack, state, tracker, gm = env
    goto(state, "loc_scilla_cariddi")
    base = MISSIONS["loc_scilla_cariddi"].difficulty
    state.flags["wind_bag_active"] = True
    resp = gm.propose(state, pack, "navigo attraverso lo stretto")
    assert resp.check.difficulty == base - 1


# -- FIX 6 ------------------------------------------------------------------

def test_itaca_tre_fasi(env):
    pack, state, tracker, gm = env
    goto(state, "loc_itaca")

    c1 = tracker.process_turn(make_result("dolos", Outcome.FULL_SUCCESS, 6))
    assert c1.get("itaca_phase_advanced") is True
    assert not c1.get("mission_completed")
    assert state.flags["itaca_phase"] == 1

    c2 = tracker.process_turn(make_result("sarissa", Outcome.FULL_SUCCESS, 6))
    assert c2.get("itaca_phase_advanced") is True
    assert state.flags["itaca_phase"] == 2

    c3 = tracker.process_turn(
        make_result("eros", Outcome.FULL_SUCCESS, 6, stake=MISSIONS["loc_itaca"].victory_reward)
    )
    assert c3.get("mission_completed") is True
    assert c3.get("victory") is True


def test_full_success_senza_transizione_missione_resta_attiva(env):
    pack, state, tracker, gm = env
    changes = tracker.process_turn(
        make_result(
            "dolos",
            Outcome.FULL_SUCCESS,
            target_ids=["polifemo"],
            stake=(
                "Raggiungi l'imboccatura della caverna rimanendo del tutto "
                "inosservata, ottenendo una visuale chiara sull'interno e su Polifemo."
            ),
        )
    )
    assert changes.get("preparation") is True
    assert not changes.get("mission_completed")
    assert tracker.current_location_id() == "loc_ciclopi"
    assert state.flags["odyssey_location_index"] == 0


def test_missione_completa_solo_con_posta_canonica_o_mutazione(env):
    pack, state, tracker, gm = env
    changes = tracker.process_turn(
        make_result(
            "dolos",
            Outcome.FULL_SUCCESS,
            target_ids=["polifemo"],
            stake=MISSIONS["loc_ciclopi"].victory_reward,
        )
    )
    assert changes.get("mission_completed") is True
    assert tracker.current_location_id() == "loc_eolo"


def test_missione_completa_con_mutazione_esplicita(env):
    pack, state, tracker, gm = env
    changes = tracker.process_turn(
        make_result(
            "dolos",
            Outcome.FULL_SUCCESS,
            target_ids=["polifemo"],
            stake="azione riuscita",
            scene_mutations=[
                {
                    "type": "mission_complete",
                    "target": "loc_ciclopi",
                    "payload": {"completed_objectives": ["escaped_polyphemus"]},
                    "reason": "obiettivo finale risolto",
                }
            ],
        )
    )
    assert changes.get("mission_completed") is True
    assert tracker.current_location_id() == "loc_eolo"


def test_regressione_reale_caverna_quattro_zampe_non_completa_missione(env):
    pack, state, tracker, gm = env
    result = make_result(
        "dolos",
        Outcome.FULL_SUCCESS,
        difficulty=2,
        target_ids=["polifemo"],
        stake=(
            "Raggiungi l'imboccatura della caverna rimanendo del tutto "
            "inosservata, ottenendo una visuale chiara sull'interno e su Polifemo."
        ),
        scene_mutations=[],
    )
    result.proposal = CheckProposal(
        action_kind="stealth",
        skill="dolos",
        difficulty=2,
        target_ids=["polifemo"],
        opposition="npc_resistance",
        reason="avvicinarsi alla caverna a quattro zampe senza farsi notare",
        stakes={
            "full_success": result.stake,
            "partial_success": "ti avvicini con un rischio",
            "failure": "Polifemo ti nota",
            "critical_failure": "Polifemo ti blocca",
        },
    )
    changes = tracker.process_turn(result)
    assert changes.get("preparation") is True
    assert not changes.get("mission_completed")
    assert state.flags["odyssey_location_index"] == 0


def test_ui_non_ha_segnale_missione_conclusa_per_successo_preparatorio(env):
    pack, state, tracker, gm = env
    changes = tracker.process_turn(
        make_result(
            "dolos",
            Outcome.FULL_SUCCESS,
            target_ids=["polifemo"],
            stake="Raggiungi l'imboccatura della caverna senza essere vista.",
        )
    )
    ui_messages = []
    if changes.get("mission_completed"):
        ui_messages.append(f"MISSIONE COMPLETATA: {changes['mission_name']}")
    assert ui_messages == []
    assert "Azione riuscita" in changes["message"]


def test_itaca_skill_richiesta_dipende_dalla_fase(env):
    pack, state, tracker, gm = env
    goto(state, "loc_itaca")
    tracker.process_turn(make_result("dolos", Outcome.FULL_SUCCESS, 6))
    # Fase 1: la skill rilevante ora è sarissa
    assert tracker.required_skills() == ("sarissa",)
    changes = tracker.process_turn(make_result("dolos", Outcome.FULL_SUCCESS, 6))
    assert changes.get("wrong_skill") is True
    assert "SARISSA" in changes["message"]


# -- FIX 7 ------------------------------------------------------------------

def test_nave_feacia_auto_pass(env):
    pack, state, tracker, gm = env
    goto(state, "loc_itaca")
    state.flags["phaeacian_ship"] = True
    resp = gm.propose(state, pack, "mi travesto da mendicante ed entro nel palazzo")
    assert resp.check.skill == "dolos"
    assert resp.check.difficulty == 0


def test_resolve_check_difficolta_zero_auto_successo(env):
    roll = resolve_check(2, 0, "safe")
    assert roll.outcome == Outcome.FULL_SUCCESS


# -- FIX 3 / 4 --------------------------------------------------------------

def test_status_espone_diff_e_retry_offset(env):
    pack, state, tracker, gm = env
    tracker.process_turn(make_result("dolos", Outcome.FAILURE))
    st = tracker.get_status()
    assert st["mission_difficulty"] == MISSIONS["loc_ciclopi"].difficulty
    assert st["retry_offset"] == 1
    assert st["effective_difficulty"] == st["mission_difficulty"] - 1


def test_status_action_history(env):
    pack, state, tracker, gm = env
    tracker.process_turn(make_result("dolos", Outcome.FAILURE))
    tracker.process_turn(make_result("thumos", Outcome.PARTIAL_SUCCESS))
    st = tracker.get_status()
    assert len(st["action_history"]) == 2
    last = st["action_history"][-1]
    assert last["skill"] == "thumos"
    assert last["relevant"] is False


def test_action_history_limitata_a_tre(env):
    pack, state, tracker, gm = env
    # Thumos non è rilevante ai Ciclopi: niente game over, il log cresce
    for _ in range(5):
        tracker.process_turn(make_result("thumos", Outcome.FAILURE))
    assert len(tracker.get_status()["action_history"]) == 3


# -- FIX 8 ------------------------------------------------------------------

def test_turn_service_passa_choice_a_narrate():
    import inspect
    from epos import turn_service
    src = inspect.getsource(turn_service)
    assert 'extras: dict[str, Any] = {"choice": choice}' in src


# -- Renderer A1111 -----------------------------------------------------------

def test_renderer_a1111_da_env(monkeypatch):
    monkeypatch.setenv("EPOS_RENDER_MODE", "a1111")
    from epos.renderers import renderer_from_env, A1111Renderer
    r = renderer_from_env()
    assert isinstance(r, A1111Renderer)
    assert r.base_url == "http://127.0.0.1:17860"


def test_renderer_a1111_payload(monkeypatch, tmp_path):
    """Verifica payload e salvataggio immagine con uno stub HTTP."""
    import base64, json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    fake_png = base64.b64encode(b"\x89PNGfakedata").decode()
    seen = {}

    class Stub(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/sdapi/v1/options":
                body = json.dumps({}).encode()
            elif self.path == "/sdapi/v1/sd-models":
                body = json.dumps([{"title": "luna_main_model.safetensors"}]).encode()
            elif self.path == "/sdapi/v1/loras":
                body = json.dumps([]).encode()
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers["Content-Length"])
            seen.update(json.loads(self.rfile.read(length)))
            body = json.dumps({"images": [fake_png]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    monkeypatch.setenv("EPOS_RENDER_MODE", "a1111")
    monkeypatch.setenv("A1111_BASE_URL", f"http://127.0.0.1:{port}")
    from epos.renderers import renderer_from_env
    rec = renderer_from_env().render(
        {"positive": "una regina guerriera", "negative": "brutta"}, tmp_path
    )
    server.shutdown()

    assert rec.status == "complete"
    assert rec.backend == "a1111"
    assert seen["prompt"] == "una regina guerriera"
    assert seen["negative_prompt"] == "brutta"
    assert (tmp_path / "image.png").read_bytes() == b"\x89PNGfakedata"


# -- Prompt visual: deduplica e ordine ----------------------------------------

def test_prompt_deduplica_chunk():
    from epos.visual import _dedupe_chunks
    text = "1girl, red chiton, leather armor, red chiton,  LEATHER armor , bow"
    assert _dedupe_chunks(text) == "1girl, red chiton, leather armor, bow"


def test_prompt_deduplica_preserva_lora():
    from epos.visual import _dedupe_chunks
    text = "score_9, <lora:Expressive_H-000001:0.35>, score_9"
    assert _dedupe_chunks(text) == "score_9, <lora:Expressive_H-000001:0.35>"


def test_prompt_odyssey_senza_duplicati():
    """Il prompt reale del pack Odyssey non deve avere chunk duplicati."""
    from epos.worldpack import load_pack
    from epos.visual import compile_prompt_package

    pack = load_pack(PACK)
    state = pack.new_world()
    characters = [{
        "id": "player",
        "outfit_worn": list(state.player.outfit.worn),
        "outfit_removed": [],
        "wounds": [],
    }]
    package = compile_prompt_package(
        pack, ["player"], characters,
        "Ulisse gazes at the cave, her chiton windswept.",
        ["volcanic landscape", "solitude"],
    )
    for field in ("positive", "negative"):
        chunks = [" ".join(c.lower().split()) for c in package[field].split(",")]
        assert len(chunks) == len(set(chunks)), f"duplicati in {field}: {package[field]}"
    # l'outfit compare una sola volta (non più ripetuto dallo style_en)
    assert package["positive"].count("worn revealing leather armor with bronze studs") == 1


# -- Prompt: prosa opzionale e negativo corto ---------------------------------

def test_prompt_prose_non_escludibile_in_odyssey(monkeypatch):
    from epos.visual import compile_prompt_package
    from epos.worldpack import load_pack
    pack = load_pack(PACK)
    state = pack.new_world()
    chars = [{"id": "player", "outfit_worn": list(state.player.outfit.worn),
              "outfit_removed": [], "wounds": []}]
    monkeypatch.setenv("EPOS_PROMPT_PROSE", "0")
    pkg = compile_prompt_package(pack, ["player"], chars,
                                 "She gazes at the dark cliffs.", ["volcanic coast"])
    assert "She gazes" in pkg["positive"]
    assert "volcanic coast" in pkg["positive"]


def test_negativo_corto_mantiene_sicurezza():
    from epos.visual import DEFAULT_NEGATIVE
    # Pony vuole negativi corti, ma i tag di sicurezza restano sempre
    assert "child" in DEFAULT_NEGATIVE
    assert "young-looking" in DEFAULT_NEGATIVE
    assert len(DEFAULT_NEGATIVE.split(",")) <= 25


def test_base_prompt_senza_narrativa_astratta():
    from epos.worldpack import load_pack
    pack = load_pack(PACK)
    sheet = pack.visual_sheets["player"]
    for astratto in ("survivor of Trojan War", "standing on rocky",
                     "daughter of Poseidon", "son of"):
        assert astratto not in sheet.base_prompt


# -- A1111: controllo LoRA ----------------------------------------------------

def test_a1111_lora_mancante_segnalato(monkeypatch, tmp_path):
    import base64, json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    fake_png = base64.b64encode(b"\x89PNGfakedata").decode()

    class Stub(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/sdapi/v1/options":
                body = json.dumps({}).encode()
            elif self.path == "/sdapi/v1/sd-models":
                body = json.dumps([{"title": "luna_main_model.safetensors"}]).encode()
            elif self.path == "/sdapi/v1/loras":
                body = json.dumps([{"name": "Expressive_H-000001", "alias": "x"}]).encode()
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            self.rfile.read(length)
            body = json.dumps({"images": [fake_png]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    monkeypatch.setenv("EPOS_RENDER_MODE", "a1111")
    monkeypatch.setenv("A1111_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}")
    from epos.renderers import renderer_from_env
    rec = renderer_from_env().render(
        {"positive": "1girl, <lora:Expressive_H-000001:0.35>, <lora:stsDebbie-10e:0.7>",
         "negative": ""},
        tmp_path,
    )
    server.shutdown()

    assert rec.status == "failed"
    assert "stsDebbie-10e" in (rec.error or "")
    assert "Expressive_H" not in (rec.error or "")
    assert rec.diagnostics["missing_loras"] == ["stsDebbie-10e"]


# -- Debug file per turno -----------------------------------------------------

def test_debug_file_scritto(tmp_path):
    from epos.worldpack import load_pack
    from epos.turn_service import TurnService
    from epos.state_store import StateStore
    from epos.odyssey_gm import OdysseyDemoGameMaster

    pack = load_pack(PACK)
    store = StateStore(tmp_path / "saves")
    service = TurnService(
        gm=OdysseyDemoGameMaster(), pack=pack, store=store,
        decision_provider=lambda *a, **k: type("D", (), {
            "choice": "safe", "use_riserva": False, "use_trigger": False,
            "dado_temerario_price": None})(),
    )
    state = service.new_session()
    result = service.play(state, "Inganno Polifemo dicendo di chiamarmi Nessuno")
    debug = store.turn_dir(state.session_id, result.turn) / "debug_turno.txt"
    assert debug.is_file()
    text = debug.read_text(encoding="utf-8")
    assert "[INPUT GIOCATORE]" in text
    assert "Inganno Polifemo" in text
    assert "[PROMPT POSITIVO]" in text
