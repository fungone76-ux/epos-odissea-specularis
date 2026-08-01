from pathlib import Path

from epos.contract import VisualMoment
from epos.visual import build_visual_contract, compile_prompt_package
from epos.worldpack import load_pack


PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"

LUNA = "score_9, score_8_up, masterpiece, photorealistic, detailed, atmospheric, stsdebbie, dynamic pose, 1girl, mature woman, brown hair, athletic body, shiny skin, head tilt, massive breasts, cleavage"
MARIA = "score_9, score_8_up, stsSmith, ultra-detailed, realistic lighting, 1girl, mature female, veiny breasts, black hair, short hair, [lora:stsSmith-10e:0.65](lora:stsSmith-10e:0.65) [lora:FantasyWorldPonyV2:0.40](lora:FantasyWorldPonyV2:0.40)"
STELLA = "score_9, score_8_up, masterpiece, photorealistic, 1girl, alice_milf_catchers, massive breasts, cleavage, blonde hair, beautiful blue eyes, shapely legs, hourglass figure, skinny body, narrow waist, wide hips, [lora:alice_milf_catchers_lora.safetensors:0.7](lora:alice_milf_catchers_lora.safetensors:0.7)"
LUNA_LORA = "<lora:stsDebbie-10e:0.7>"
MARIA_LORA = "<lora:stsSmith-10e:0.65>"
STELLA_LORA = "<lora:alice_milf_catchers_lora.safetensors:0.7>"


def _pack_state():
    pack = load_pack(PACK)
    state = pack.new_world("odyssey-visual")
    for npc_id in ("polifemo", "atena", "antinoo", "penelope"):
        state.npcs[npc_id].present = True
        state.npcs[npc_id].location_id = state.location_id
    return pack, state


def _moment(**overrides):
    data = {
        "summary": "visual test",
        "focus_character": "player",
        "visible_characters": ["player"],
        "shared_action": False,
        "moment_type": "action",
        "actor_character": "player",
        "visual_en": "Odysseus raises her bronze-tipped bow in the cyclops cave",
        "tags_en": ["low angle", "tense posture"],
    }
    data.update(overrides)
    return VisualMoment.from_dict(data)


def test_base_luna_inviolabile_in_compact(monkeypatch):
    pack, state = _pack_state()
    monkeypatch.setenv("EPOS_PROMPT_MODE", "compact")
    contract = build_visual_contract(state, pack, _moment(), 0)
    pkg = contract.prompt_package
    assert pkg["base_prompt_by_character"]["player"] == LUNA
    assert pkg["positive"].startswith(LUNA)
    assert "ancient Greek warrior queen" not in pkg["base_prompt_by_character"]["player"]
    assert "very short crimson wool chiton with deep low-cut neckline" in pkg["positive"]
    assert "low camera" in pkg["positive"]
    assert "Odysseus raises" in pkg["positive"]


def test_visual_en_integrale_nel_positive():
    pack, state = _pack_state()
    visual_en = (
        "Ulisse in a low crouch on all fours, both hands and knees on volcanic rock"
    )
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en=visual_en, tags_en=["volcanic shore"]),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert "low crouch" in positive
    assert "on all fours" in positive
    assert "both hands and knees on volcanic rock" in positive
    assert contract.prompt_package["positive_prompt"] == positive


def test_lora_luna_separato_non_markdown():
    pack, state = _pack_state()
    contract = build_visual_contract(state, pack, _moment(), 0)
    positive = contract.prompt_package["positive"]
    assert LUNA in positive
    assert LUNA_LORA in positive
    assert positive.index(LUNA) < positive.index(LUNA_LORA)
    assert "[lora:stsDebbie-10e:0.7]" not in positive
    assert contract.prompt_package["character_lora_by_character"]["player"] == LUNA_LORA


def test_base_maria_inviolabile_e_ruolo_successivo(monkeypatch):
    pack, state = _pack_state()
    monkeypatch.setenv("EPOS_PROMPT_MODE", "compact")
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            focus_character="polifemo",
            visible_characters=["polifemo"],
            actor_character="polifemo",
            visual_en="Polyphemus grips her obsidian club near the cave fire",
        ),
        0,
    )
    pkg = contract.prompt_package
    pos = pkg["positive"]
    assert pkg["base_prompt_by_character"]["polifemo"] == MARIA
    assert MARIA_LORA in pos
    assert "[lora:stsSmith-10e:0.65](lora:stsSmith-10e:0.65)" in pos
    assert "[lora:FantasyWorldPonyV2:0.40](lora:FantasyWorldPonyV2:0.40)" in pos
    assert pos.index(MARIA) < pos.index("brutal threatening presence")
    assert "single large bloodshot eye" not in pkg["role_prompt_by_character"]["polifemo"]
    assert pkg["role_prompt_by_character"]["polifemo"] == "brutal threatening presence"


def test_base_stella_inviolabile_per_atena_e_antinoo():
    pack, state = _pack_state()
    for char_id in ("atena", "antinoo"):
        contract = build_visual_contract(
            state,
            pack,
            _moment(
                focus_character=char_id,
                visible_characters=[char_id],
                actor_character=char_id,
                visual_en=f"{char_id} stands in hard Mediterranean light",
            ),
            0,
        )
        pkg = contract.prompt_package
        assert pkg["base_prompt_by_character"][char_id] == STELLA
        assert STELLA_LORA in pkg["positive"]
        assert "alice_milf_catchers_lora.safetensors:0.7" in pkg["positive"]
        assert pkg["positive"].index(STELLA) < pkg["positive"].index(
            pkg["role_prompt_by_character"][char_id]
        )


def test_speaker_focus_polifemo():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            focus_character="player",
            visible_characters=["player", "polifemo"],
            shared_action=True,
            moment_type="speech",
            speaker_character="polifemo",
        ),
        0,
    )
    assert contract.focus_character == "polifemo"
    assert contract.visible_characters == ["polifemo"]
    assert LUNA not in contract.prompt_package["positive"]
    assert MARIA in contract.prompt_package["positive"]


def test_player_response_does_not_add_polifemo():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visible_characters=["player", "polifemo"],
            shared_action=True,
            moment_type="speech",
            speaker_character="player",
        ),
        0,
    )
    assert contract.focus_character == "player"
    assert contract.visible_characters == ["player"]
    positive = contract.prompt_package["positive"]
    assert LUNA in positive
    assert LUNA_LORA in positive
    assert MARIA_LORA not in positive
    assert STELLA_LORA not in positive
    assert MARIA not in positive
    assert STELLA not in positive


def test_reazione_polifemo_solo_polifemo():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            focus_character="player",
            visible_characters=["player", "polifemo"],
            shared_action=True,
            moment_type="reaction",
            reactor_character="polifemo",
            visual_en="Polyphemus recoils with blood on her single eye",
        ),
        0,
    )
    assert contract.focus_character == "polifemo"
    assert contract.visible_characters == ["polifemo"]
    assert MARIA in contract.prompt_package["positive"]
    assert LUNA not in contract.prompt_package["positive"]


def test_azione_non_intima_lotta_e_confronto_restano_monopersonaggio():
    pack, state = _pack_state()
    for visual_en in (
        "Odysseus strikes toward Polyphemus with a charred olive stake",
        "Odysseus wrestles in the dust of the cave",
        "Antinoo threatens Odysseus across the palace hall",
    ):
        actor = "antinoo" if "Antinoo" in visual_en else "player"
        contract = build_visual_contract(
            state,
            pack,
            _moment(
                focus_character=actor,
                visible_characters=["player", "polifemo", "antinoo"],
                shared_action=True,
                moment_type="action",
                actor_character=actor,
                visual_en=visual_en,
            ),
            0,
        )
        assert contract.visible_characters == [actor]
        assert contract.shared_action is False
        assert contract.prompt_package["positive"].count("score_9") == 1


def test_intimita_reale_consente_solo_partecipanti_diretti():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            focus_character="player",
            visible_characters=["player", "penelope", "atena"],
            shared_action=True,
            moment_type="intimate",
            intimate_shared_moment=True,
            multi_character_reason="recognized_in_shared_bed",
            multi_character_participants=["player", "penelope"],
        ),
        0,
    )
    assert contract.visible_characters == ["player", "penelope"]
    assert contract.shared_action is True
    assert "merged bodies" in contract.prompt_package["negative"]
    assert "background people" in contract.prompt_package["negative"]
    assert "atena" not in contract.prompt_package["base_prompt_by_character"]


def test_llm_non_puo_forzare_multi_non_intimo():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visible_characters=["player", "polifemo"],
            shared_action=True,
            moment_type="action",
            actor_character="player",
        ),
        0,
    )
    assert contract.focus_character == "player"
    assert contract.visible_characters == ["player"]
    assert contract.shared_action is False


def test_negativo_specifico_solo_visibile():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            focus_character="polifemo",
            visible_characters=["polifemo"],
            actor_character="polifemo",
        ),
        0,
    )
    negative = contract.prompt_package["negative"]
    assert "multiple eyes" in negative
    assert pack.visual_negative_extra_en.split(",")[0].strip() in negative
    assert "mundane" not in negative
    assert "old" not in negative


def test_compact_preserva_tutti_i_base_canonici(monkeypatch):
    pack, state = _pack_state()
    monkeypatch.setenv("EPOS_PROMPT_MODE", "compact")
    for char_id, canonical in {
        "player": LUNA,
        "polifemo": MARIA,
        "atena": STELLA,
        "antinoo": STELLA,
    }.items():
        expected_lora = {
            "player": LUNA_LORA,
            "polifemo": MARIA_LORA,
            "atena": STELLA_LORA,
            "antinoo": STELLA_LORA,
        }[char_id]
        contract = build_visual_contract(
            state,
            pack,
            _moment(
                focus_character=char_id,
                visible_characters=[char_id],
                actor_character=char_id,
                visual_en=f"{char_id} performs a precise visible gesture",
                tags_en=["precise gesture", "canon location"],
            ),
            0,
        )
        pkg = contract.prompt_package
        assert pkg["base_prompt_by_character"][char_id] == canonical
        assert pkg["positive"].startswith(canonical)
        assert expected_lora in pkg["positive"]
        assert "precise visible gesture" in pkg["positive"]
        assert "performs a precise visible gesture" in pkg["positive"]


def test_compact_preserva_visual_en_prioritario(monkeypatch):
    pack, state = _pack_state()
    monkeypatch.setenv("EPOS_PROMPT_MODE", "compact")
    monkeypatch.setenv("EPOS_PROMPT_PROSE", "0")
    visual_en = (
        "Ulisse in a low crouch on all fours, both hands on the ground, "
        "knees on the ground, body low beside the volcanic shore"
    )
    contract = build_visual_contract(state, pack, _moment(visual_en=visual_en), 0)
    positive = contract.prompt_package["positive"]
    assert positive.startswith(LUNA)
    assert LUNA_LORA in positive
    assert "on all fours" in positive
    assert "body low beside the volcanic shore" in positive
    assert "<lora:Expressive_H-000001:0.35>" in positive
    assert "<lora:FantasyWorldPonyV2:0.40>" in positive


def test_ordine_layer_player():
    pack, state = _pack_state()
    visual_en = "Ulisse in a low crouch on all fours on the volcanic shore"
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en=visual_en, tags_en=["wild coast marker", "Aegean glare"]),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert positive.index(LUNA) < positive.index(LUNA_LORA)
    assert positive.index(LUNA_LORA) < positive.index("very short crimson wool chiton")
    assert positive.index("very short crimson wool chiton") < positive.index("wild coast marker")
    assert positive.index("wild coast marker") < positive.index(visual_en)
    assert positive.index(visual_en) < positive.index("<lora:Expressive_H-000001:0.35>")


def test_regressione_reale_low_crouch_on_all_fours():
    pack, state = _pack_state()
    visual_en = (
        "Ulisse in a low crouch on all fours, intently scanning the rugged "
        "volcanic shore of the Cyclops island, both hands braced on dark "
        "volcanic rock, knees on the ground, body low and tense, full body "
        "visible, side three-quarter view, recurved bow resting beside her"
    )
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            summary="loc_ciclopi regression",
            focus_character="player",
            visible_characters=["player"],
            moment_type="action",
            actor_character="player",
            visual_en=visual_en,
            tags_en=["wild coast", "Aegean sea atmosphere", "low angle"],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert LUNA_LORA in positive
    assert "on all fours" in positive
    assert "very short crimson wool chiton with deep low-cut neckline" in positive
    assert "volcanic shore" in positive
    assert "<lora:Expressive_H-000001:0.35>" in positive
    assert "<lora:FantasyWorldPonyV2:0.40>" in positive


def test_a1111_payload_usa_positive_con_lora_e_visual(monkeypatch, tmp_path):
    import base64
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from epos.renderers import A1111Renderer

    pack, state = _pack_state()
    visual_en = (
        "Ulisse in a low crouch on all fours, her bronze-ringed braided hair "
        "wind-swept, both hands on volcanic rock"
    )
    contract = build_visual_contract(state, pack, _moment(visual_en=visual_en), 0)
    seen = {}
    fake_png = base64.b64encode(b"\x89PNGfake").decode()

    class Stub(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/sdapi/v1/options":
                body = json.dumps({}).encode()
            elif self.path == "/sdapi/v1/sd-models":
                body = json.dumps([{"title": "luna_main_model.safetensors"}]).encode()
            elif self.path == "/sdapi/v1/loras":
                body = json.dumps(
                    [
                        {"name": "stsDebbie-10e", "alias": "stsDebbie-10e"},
                        {"name": "Expressive_H-000001", "alias": "Expressive_H-000001"},
                        {"name": "FantasyWorldPonyV2", "alias": "FantasyWorldPonyV2"},
                    ]
                ).encode()
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

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        renderer = A1111Renderer(base_url=f"http://127.0.0.1:{server.server_address[1]}")
        record = renderer.render(contract.prompt_package, tmp_path)
    finally:
        server.shutdown()

    assert record.status == "complete"
    assert seen["prompt"] == contract.prompt_package["positive"]
    assert LUNA_LORA in seen["prompt"]
    assert "on all fours" in seen["prompt"]
    assert "both hands on volcanic rock" in seen["prompt"]
    assert "braided" not in seen["prompt"][seen["prompt"].index(LUNA) + len(LUNA):].lower()


def test_player_outfit_senza_tratti_fisici():
    pack, state = _pack_state()
    outfit = ", ".join(state.player.outfit.worn).lower()
    for forbidden in ("hair", "braid", "eye", "skin", "scar"):
        assert forbidden not in outfit
    assert "very short crimson wool chiton with deep low-cut neckline" in outfit
    assert "worn revealing leather armor with bronze studs" in outfit
    assert "barefoot" in outfit


def test_player_role_prompt_senza_tratti_fisici():
    pack, _state = _pack_state()
    role = pack.visual_sheets["player"].role_prompt_en.lower()
    for forbidden in ("braided", "sea-salt", "scar", "olive skin", "eye color"):
        assert forbidden not in role
    assert role == ""


def test_role_prompt_player_conciso_e_visivo():
    pack, _state = _pack_state()
    role = pack.visual_sheets["player"].role_prompt_en
    max_words = pack.visual_policy.max_role_prompt_words
    assert role == ""
    assert len(role.split()) <= max_words
    assert "expression" not in role.lower()
    for forbidden in (
        "war survivor",
        "experienced navigator",
        "sharp strategic presence",
        "Bronze Age adventurer",
    ):
        assert forbidden.lower() not in role.lower()


def test_role_prompt_polifemo_conciso_senza_genealogie():
    pack, _state = _pack_state()
    role = pack.visual_sheets["polifemo"].role_prompt_en
    assert role == "brutal threatening presence"
    assert len(role.split()) <= pack.visual_policy.max_role_prompt_words
    for forbidden in ("daughter of Poseidon", "Cyclops island", "cave-dwelling", "mythic host"):
        assert forbidden.lower() not in role.lower()


def test_tutti_role_prompt_odissea_concisi_senza_biografia_identita_o_outfit():
    pack, _state = _pack_state()
    forbidden = (
        "survivor",
        "navigator",
        "adventurer",
        "strategist",
        "legendary",
        "ancient hero",
        "daughter of",
        "son of",
        "ruler of",
        "experienced",
        "hair",
        "eyes",
        "skin",
        "scar",
        "breast",
        "hips",
        "chiton",
        "armor",
        "corselet",
        "cloak",
        "spear",
        "club",
        "belt",
        "sandals",
        "himation",
        "peplos",
        "expression",
        "smile",
        "smirk",
        "frown",
    )
    for char_id, sheet in pack.visual_sheets.items():
        role = sheet.role_prompt_en
        if not role:
            continue
        assert len(role.split()) <= pack.visual_policy.max_role_prompt_words, char_id
        lowered = role.lower()
        for term in forbidden:
            assert term not in lowered, (char_id, term, role)


def test_prompt_finale_player_role_breve_senza_vecchie_frasi():
    pack, state = _pack_state()
    visual_en = (
        "seated on a dark volcanic rock, legs visible, one hand resting on her knee, "
        "looking toward distant cliffs and cave openings"
    )
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en=visual_en, tags_en=["wild Aegean shoreline", "dramatic Mediterranean light"]),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert positive.startswith(LUNA)
    assert LUNA_LORA in positive
    assert "very short crimson wool chiton with deep low-cut neckline" in positive
    assert visual_en in positive
    for forbidden in (
        "ancient Greek war survivor",
        "experienced navigator",
        "sharp strategic presence",
        "Bronze Age adventurer",
    ):
        assert forbidden not in positive


def test_role_prompt_non_sostituisce_priorita_scene():
    pack, state = _pack_state()
    visual_en = (
        "kneeling beside the surf, both hands gripping black volcanic stone, "
        "full body, side three-quarter camera, distant cave openings under hard light"
    )
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en=visual_en, tags_en=["low camera angle", "windy shoreline"]),
        0,
    )
    positive = contract.prompt_package["positive"]
    for required in (
        "kneeling beside the surf",
        "both hands gripping black volcanic stone",
        "side three-quarter camera",
        "distant cave openings",
        "low camera",
        "windy shoreline",
    ):
        assert required in positive
    assert positive.index("low camera") < positive.index("kneeling beside the surf")


def test_compact_conserva_role_breve_e_visual_senza_versione_lunga(monkeypatch):
    pack, state = _pack_state()
    monkeypatch.setenv("EPOS_PROMPT_MODE", "compact")
    visual_en = "on all fours, both hands on volcanic rock, full body side view"
    contract = build_visual_contract(state, pack, _moment(visual_en=visual_en), 0)
    positive = contract.prompt_package["positive"]
    assert "on all fours" in positive
    assert "both hands on volcanic rock" in positive
    assert "full body" in positive
    assert "ancient Greek war survivor" not in positive
    assert "Bronze Age adventurer" not in positive


def test_prompt_player_senza_espressioni_facciali_fuori_base():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=(
                "seated on a dark volcanic rock, stern expression, "
                "looking toward distant cliffs, clenched jaw"
            ),
            tags_en=["seated pose", "weary but determined expression", "smile", "three-quarter view"],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    after_base = positive[len(LUNA):].lower()
    for forbidden in (
        "expression",
        "smile",
        "smiling",
        "frown",
        "smirk",
        "angry expression",
        "weary but determined expression",
        "clenched jaw",
    ):
        assert forbidden not in after_base
    assert "looking toward distant cliffs" in positive
    assert "front three quarter view" in positive or "three-quarter view" in positive


def test_tags_non_duplicano_outfit_player():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en="standing on black volcanic stone, full body, side view",
            tags_en=[
                "crimson wool chiton",
                "leather armor",
                "holding recurved bow",
                "side view",
                "dramatic Mediterranean light",
            ],
        ),
        0,
    )
    tags = contract.prompt_package["scene_tags"]
    assert "crimson wool chiton" not in tags
    assert "leather armor" not in tags
    assert "holding recurved bow" not in tags
    assert "dramatic Mediterranean light" in tags
    positive = contract.prompt_package["positive"]
    assert positive.count("very short crimson wool chiton with deep low-cut neckline") == 1
    assert positive.count("worn revealing leather armor with bronze studs") == 1
    assert positive.count("recurved bow with bronze tips") == 1


def test_visual_en_principale_tags_non_seconda_prosa():
    pack, state = _pack_state()
    visual_en = (
        "seated on a dark volcanic basalt rock with crossed legs, "
        "one hand resting near the bow, looking toward distant cliffs and cave openings, "
        "smoke rising in the far background"
    )
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=visual_en,
            tags_en=[
                "seated on dark volcanic basalt rock with crossed legs",
                "looking toward distant cliffs and cave openings",
                "three-quarter view",
                "wild Aegean shoreline",
            ],
        ),
        0,
    )
    assert visual_en in contract.prompt_package["positive"]
    assert "seated on dark volcanic basalt rock with crossed legs" not in contract.prompt_package["scene_tags"]
    assert "looking toward distant cliffs and cave openings" not in contract.prompt_package["scene_tags"]
    assert "three-quarter view" in contract.prompt_package["scene_tags"]


def test_dedupe_cross_layer_rimuove_tag_arma_ma_conserva_posizione_in_visual():
    pack, state = _pack_state()
    visual_en = "standing near the surf, holding a recurved bow against her leg, full body"
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=visual_en,
            tags_en=["holding recurved bow", "full body", "wild Aegean shoreline"],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert "holding recurved bow" not in contract.prompt_package["scene_tags"]
    assert "holding a recurved bow against her leg" in positive
    assert positive.count("holding a recurved bow against her leg") == 1


def test_roccia_vulcanica_prompt_pulito():
    pack, state = _pack_state()
    visual_en = (
        "seated on a dark volcanic basalt rock with crossed legs, "
        "one hand resting near the bow, looking toward distant cliffs and cave openings, "
        "smoke rising in the far background, cinematic composition"
    )
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=visual_en,
            tags_en=[
                "seated pose",
                "legs crossed",
                "crimson wool chiton",
                "leather armor",
                "holding recurved bow",
                "wild Aegean shoreline",
                "dramatic Mediterranean light",
                "smiling",
            ],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert "seated on a dark volcanic basalt rock with crossed legs" in positive
    assert "wild Aegean shoreline" in positive
    assert positive.count("very short crimson wool chiton with deep low-cut neckline") == 1
    assert positive.count("worn revealing leather armor with bronze studs") == 1
    assert "crimson wool chiton" not in contract.prompt_package["scene_tags"]
    assert "leather armor" not in contract.prompt_package["scene_tags"]
    assert "holding recurved bow" not in contract.prompt_package["scene_tags"]
    assert "smiling" not in positive[len(LUNA):].lower()


def test_compact_visual_primario_tags_pochi_outfit_non_ripetuto(monkeypatch):
    pack, state = _pack_state()
    monkeypatch.setenv("EPOS_PROMPT_MODE", "compact")
    visual_en = "seated on volcanic rock, crossed legs, full body, three-quarter view"
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=visual_en,
            tags_en=[
                "seated on volcanic rock",
                "crossed legs",
                "crimson wool chiton",
                "leather armor",
                "holding recurved bow",
                "dramatic Mediterranean light",
                "smirk",
            ],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert "seated on volcanic rock" in positive
    assert "crossed legs" in positive
    assert "full body" in positive
    assert "three-quarter view" in positive
    assert len(contract.prompt_package["scene_tags"]) <= pack.visual_policy.max_scene_tags
    assert "crimson wool chiton" not in contract.prompt_package["scene_tags"]
    assert "leather armor" not in contract.prompt_package["scene_tags"]
    assert "smirk" not in positive[len(LUNA):].lower()


def test_outfit_player_rivelatore_preservato_nel_prompt():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=(
                "seated on a dark volcanic basalt rock with crossed legs, "
                "one hand resting near the bow, looking toward distant cliffs"
            ),
            tags_en=["seated pose", "three-quarter view", "wild Aegean shoreline"],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert pack.visual_policy.preserve_revealing_outfit_traits is True
    assert pack.visual_policy.revealing_outfit_priority is True
    for required in (
        "very short crimson wool chiton with deep low-cut neckline",
        "bare thighs clearly visible",
        "worn revealing leather armor with bronze studs",
        "exposed shoulders",
    ):
        assert required in positive


def test_outfit_player_non_annacquato_da_tags_o_visual_generici():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=(
                "wearing a chiton and armor, seated on volcanic rock, "
                "looking toward distant cliffs"
            ),
            tags_en=["chiton", "armor", "bow", "seated pose", "dramatic Mediterranean light"],
        ),
        0,
    )
    pkg = contract.prompt_package
    positive_chunks = [chunk.strip().lower() for chunk in pkg["positive"].split(",")]
    assert "chiton" not in pkg["scene_tags"]
    assert "armor" not in pkg["scene_tags"]
    assert "bow" not in pkg["scene_tags"]
    assert "wearing a chiton and armor" not in pkg["positive"].lower()
    assert "very short crimson wool chiton with deep low-cut neckline" in pkg["positive"]
    assert "worn revealing leather armor with bronze studs" in pkg["positive"]
    assert "chiton" not in positive_chunks
    assert "armor" not in positive_chunks


def test_prompt_finale_rimuove_subtle_smile_e_chunk_monchi():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=(
                "seated on volcanic rock, subtle smile, hand on, looking at, "
                "one hand resting near the bow, looking toward distant cliffs"
            ),
            tags_en=["smirk", "holding", "standing with", "three-quarter view"],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    after_base = positive[len(LUNA):].lower()
    for forbidden in ("subtle smile", "smile", "smirk", "hand on", "looking at", "holding", "standing with"):
        assert forbidden not in after_base
    assert "one hand resting near the bow" in positive
    assert "looking toward distant cliffs" in positive
    assert "three-quarter view" in positive
    assert "hand on" in contract.prompt_package["broken_chunk_sanitization"]["removed_chunks"]


def test_altri_personaggi_femminili_conservano_outfit_rivelatore():
    pack, state = _pack_state()
    expected = {
        "polifemo": "skimpy crude stitched animal pelts with rough revealing cut",
        "atena": "revealing bronze corselet with low-cut neckline",
        "antinoo": "very short red wool combat chiton with deep low-cut neckline",
        "eurimaco": "expensive blue peplos with deep low-cut neckline",
    }
    state.npcs["eurimaco"].present = True
    state.npcs["eurimaco"].location_id = state.location_id
    for char_id, outfit_fragment in expected.items():
        contract = build_visual_contract(
            state,
            pack,
            _moment(
                focus_character=char_id,
                visible_characters=[char_id],
                actor_character=char_id,
                visual_en=f"{char_id} stands in dramatic Mediterranean light",
                tags_en=["three-quarter view", "dramatic Mediterranean light"],
            ),
            0,
        )
        assert outfit_fragment in contract.prompt_package["positive"]


def test_compact_preserva_outfit_rivelatore_player(monkeypatch):
    pack, state = _pack_state()
    monkeypatch.setenv("EPOS_PROMPT_MODE", "compact")
    monkeypatch.setenv("EPOS_PROMPT_OUTFIT_CHUNKS", "2")
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en="seated on volcanic rock, crossed legs, full body, three-quarter view",
            tags_en=["chiton", "armor", "dramatic Mediterranean light"],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert "very short crimson wool chiton with deep low-cut neckline" in positive
    assert "bare thighs clearly visible" in positive
    assert "worn revealing leather armor with bronze studs" in positive
    assert "exposed shoulders" in positive
    assert "chiton" not in contract.prompt_package["scene_tags"]
    assert "armor" not in contract.prompt_package["scene_tags"]


def test_visual_llm_sanitizzato_preserva_posa():
    pack, state = _pack_state()
    visual_en = (
        "Ulisse on all fours, her bronze-ringed braided hair wind-swept, "
        "both hands on volcanic rock"
    )
    contract = build_visual_contract(state, pack, _moment(visual_en=visual_en), 0)
    positive = contract.prompt_package["positive"]
    assert "on all fours" in positive
    assert "both hands on volcanic rock" in positive
    assert "braided" not in positive[positive.index(LUNA) + len(LUNA):].lower()
    assert "hair" not in positive[positive.index(LUNA) + len(LUNA):].lower()
    assert "bronze-ringed" not in positive.lower()
    assert any(
        "bronze-ringed braided hair wind-swept" in term
        for term in contract.prompt_package["identity_sanitization"]["removed_terms"]
    )


def test_tags_llm_sanitizzati():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            tags_en=["on all fours", "blonde hair", "green eyes", "volcanic coast"],
            visual_en="Ulisse braces against volcanic stone",
        ),
        0,
    )
    tags = contract.prompt_package["scene_tags"]
    assert "on all fours" in tags
    assert "volcanic coast" in tags
    assert "blonde hair" not in tags
    assert "green eyes" not in tags
    positive = contract.prompt_package["positive"]
    after_base = positive[positive.index(LUNA) + len(LUNA):].lower()
    assert "blonde hair" not in after_base
    assert "green eyes" not in after_base


def test_base_resta_unica_sorgente_capelli_player():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en="Ulisse on all fours, her loose wind-swept hair near the rocks",
            tags_en=["brown hair", "low angle"],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert "brown hair" in positive
    after_base = positive[positive.index(LUNA) + len(LUNA):].lower()
    for forbidden in ("hair", "braid", "scar", "olive skin"):
        assert forbidden not in after_base
    assert "low camera" in positive
    assert "on all fours" in positive


def test_outfit_persistito_viene_normalizzato_per_odissea():
    pack, state = _pack_state()
    state.player.outfit.worn.append("bronze-ringed braided hair")
    contract = build_visual_contract(state, pack, _moment(), 0)
    assert "bronze-ringed braided hair" not in state.player.outfit.worn
    assert "bronze-ringed" not in contract.prompt_package["positive"].lower()


def test_caso_reale_a_carponi_senza_identita_aggiunta():
    pack, state = _pack_state()
    visual_en = (
        "Ulisse in a low crouch on all fours, both hands on the volcanic ground, "
        "knees on the ground, her bronze-ringed braided hair slightly wind-swept, "
        "eyes scanning the rugged Aegean coastline, dark volcanic rocks and sea in the background"
    )
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=visual_en,
            tags_en=["on all fours", "volcanic rock", "Aegean sea"],
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert LUNA_LORA in positive
    assert "on all fours" in positive
    assert "both hands on the volcanic ground" in positive
    assert "knees on the ground" in positive
    assert "very short crimson wool chiton with deep low-cut neckline" in positive
    assert "volcanic rock" in positive
    after_base = positive[positive.index(LUNA) + len(LUNA):].lower()
    for forbidden in ("braid", "braided", "bronze-ringed hair", "scar", "olive skin"):
        assert forbidden not in after_base


def test_altri_personaggi_sanitizzano_identita_fuori_base():
    pack, state = _pack_state()
    for char_id, base in {"polifemo": MARIA, "atena": STELLA, "antinoo": STELLA}.items():
        contract = build_visual_contract(
            state,
            pack,
            _moment(
                focus_character=char_id,
                visible_characters=[char_id],
                actor_character=char_id,
                visual_en=(
                    f"{char_id} advances, green eyes fixed forward, "
                    "scar across the cheek, massive muscular body in motion"
                ),
                tags_en=["volcanic coast", "black hair", "green eyes"],
            ),
            0,
        )
        positive = contract.prompt_package["positive"]
        after_base = positive[positive.index(base) + len(base):].lower()
        assert "volcanic coast" in positive
        for forbidden in ("green eyes", "scar", "muscular body", "black hair"):
            assert forbidden not in after_base


def test_identity_summary_non_sostituisce_il_base():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            focus_character="atena",
            visible_characters=["atena"],
            actor_character="atena",
            visual_en="Athena points her spear from a mountain ridge",
        ),
        0,
    )
    positive = contract.prompt_package["positive"]
    assert positive.startswith(STELLA)
    assert not positive.startswith("stern divine authority")
    assert "stern divine authority" in positive


def test_default_policy_retrocompatibile_su_pack_temporaneo(tmp_path):
    (tmp_path / "world.yaml").write_text(
        "id: temp_pack\ntitle: Temp\nstart_location_id: room\n"
        "locations:\n  - id: room\n    name: Room\n",
        encoding="utf-8",
    )
    (tmp_path / "visual.yaml").write_text(
        "characters:\n"
        "  - id: player\n"
        "    base_prompt: base, base, cloak\n",
        encoding="utf-8",
    )
    pack = load_pack(tmp_path)
    assert pack.visual_policy.protected_base_prompts is False
    pkg = compile_prompt_package(
        pack,
        ["player"],
        [{"id": "player", "outfit_worn": [], "outfit_removed": [], "wounds": []}],
        "visual",
        ["tag"],
    )
    assert pkg["positive"] == "base, cloak, tag, visual"


def test_visual_director_on_all_fours_verso_caverna_sceglie_rear_three_quarter():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=(
                "Low angle side shot of Ulisse on all fours, advancing toward "
                "the cavern entrance, both hands and knees on dark volcanic rock"
            ),
            tags_en=["wide shot", "side view", "low angle"],
        ),
        0,
    )
    director = contract.camera_director
    positive = contract.prompt_package["positive"]
    assert contract.focus_character == "player"
    assert contract.visible_characters == ["player"]
    assert director["proposed_camera"] == "side"
    assert director["selected_camera"] == "rear_three_quarter"
    assert director["camera_override_applied"] is True
    assert "full body" in positive
    assert "low camera" in positive
    assert "rear three quarter view" in positive
    assert "facing away" in positive
    assert "cavern entrance ahead" in positive
    assert "side shot" not in positive.lower()
    assert "side view" not in contract.prompt_package["scene_tags"]


def test_visual_director_varia_se_precedente_rear():
    pack, state = _pack_state()
    state.flags["visual_camera_history"] = [
        {"camera_side": "rear_three_quarter", "shot_type": "full_body", "camera_angle": "low"}
    ]
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=(
                "Ulisse on all fours, advancing toward the cavern entrance, "
                "both hands and knees on dark volcanic rock"
            ),
            tags_en=["low angle"],
        ),
        0,
    )
    assert contract.camera_director["selected_camera"] == "rear"
    assert "rear view" in contract.prompt_package["positive"]
    assert "rear three quarter view" not in contract.prompt_package["positive"]


def test_visual_director_dialogo_non_introduce_personaggi():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            focus_character="polifemo",
            visible_characters=["player", "polifemo"],
            shared_action=True,
            moment_type="speech",
            speaker_character="polifemo",
            visual_en="Polyphemus speaks from the cave threshold",
            tags_en=["front view"],
        ),
        0,
    )
    assert contract.focus_character == "polifemo"
    assert contract.visible_characters == ["polifemo"]
    assert contract.prompt_package["visible_characters"] == ["polifemo"]


def test_visual_director_azione_frontale_puo_scegliere_front_three_quarter():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en="Ulisse reaching for the bow on volcanic stone, hands visible",
            tags_en=["side view"],
        ),
        0,
    )
    assert contract.camera_director["selected_camera"] == "front_three_quarter"
    assert "front three quarter view" in contract.prompt_package["positive"]
    assert "facing camera three quarter" in contract.prompt_package["positive"]


def test_visual_director_diagnostica_camera_strutturata():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en="Ulisse on all fours advancing toward the cavern entrance"),
        0,
    )
    pkg = contract.prompt_package
    for key in (
        "proposed_camera",
        "selected_camera",
        "camera_override_applied",
        "camera_override_reason",
        "shot_type",
        "camera_angle",
        "camera_side",
        "subject_orientation",
        "camera_history",
        "director_reason",
    ):
        assert key in pkg
    assert contract.camera_director["shot_type"] == "full_body"
    assert contract.camera_director["camera_angle"] == "low"


def test_a1111_payload_contiene_camera_del_regista(monkeypatch, tmp_path):
    import base64
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from epos.renderers import A1111Renderer

    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=(
                "Low angle side shot of Ulisse on all fours, advancing toward "
                "the cavern entrance, both hands and knees on dark volcanic rock"
            ),
            tags_en=["side view"],
        ),
        0,
    )
    seen = {}
    fake_png = base64.b64encode(b"\x89PNGfake").decode()

    class Stub(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/sdapi/v1/options":
                body = json.dumps({}).encode()
            elif self.path == "/sdapi/v1/sd-models":
                body = json.dumps([{"title": "luna_main_model.safetensors"}]).encode()
            elif self.path == "/sdapi/v1/loras":
                body = json.dumps(
                    [
                        {"name": "stsDebbie-10e", "alias": "stsDebbie-10e"},
                        {"name": "Expressive_H-000001", "alias": "Expressive_H-000001"},
                        {"name": "FantasyWorldPonyV2", "alias": "FantasyWorldPonyV2"},
                    ]
                ).encode()
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

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        record = A1111Renderer(base_url=f"http://127.0.0.1:{server.server_address[1]}").render(
            contract.prompt_package, tmp_path
        )
    finally:
        server.shutdown()

    assert record.status == "complete"
    assert "rear three quarter view" in seen["prompt"]
    assert "side shot" not in seen["prompt"].lower()


def test_nudity_policy_outfit_normale_non_aggiunge_nude_tags():
    pack, state = _pack_state()
    state.player.outfit.worn = [
        "long wool travel chiton",
        "heavy travel cloak",
        "leather sandals",
    ]
    state.player.outfit.removed = []
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en="Ulisse stands on a windy volcanic ledge"),
        0,
    )
    pkg = contract.prompt_package
    assert pkg["nudity_mode"] == "none"
    assert "completely nude" not in pkg["positive"]
    assert "fully naked" not in pkg["positive"]
    assert "no clothing" not in pkg["positive"]


def test_nudity_policy_revealing_non_collassa_in_fully_nude():
    pack, state = _pack_state()
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en="Ulisse stands in harsh sunlight on black volcanic rock"),
        0,
    )
    pkg = contract.prompt_package
    assert pkg["nudity_mode"] == "revealing"
    assert "very short crimson wool chiton with deep low-cut neckline" in pkg["positive"]
    assert "bare thighs clearly visible" in pkg["positive"]
    assert "completely nude" not in pkg["positive"]
    assert "fully naked" not in pkg["positive"]


def test_nudity_policy_topless_resta_separata_da_fully_nude():
    pack, state = _pack_state()
    state.player.outfit.worn = ["short linen skirt", "barefoot"]
    state.player.outfit.removed = [
        "very short crimson wool chiton with deep low-cut neckline",
        "worn revealing leather armor with bronze studs",
    ]
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en="Ulisse stands topless on a windy volcanic ledge"),
        0,
    )
    pkg = contract.prompt_package
    assert pkg["detected_clothing_state"] == "torso_unclothed_lower_clothed"
    assert pkg["nudity_mode"] == "topless"
    assert "topless" in pkg["positive"]
    assert "no top" in pkg["positive"]
    assert "completely nude" not in pkg["positive"]
    assert "fully naked" not in pkg["positive"]


def test_nudity_policy_bottomless_resta_separata_da_fully_nude():
    pack, state = _pack_state()
    state.player.outfit.worn = ["linen chest wrap", "barefoot"]
    state.player.outfit.removed = ["very short crimson wool chiton with deep low-cut neckline"]
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en="Ulisse stands bottomless beside the volcanic surf"),
        0,
    )
    pkg = contract.prompt_package
    assert pkg["detected_clothing_state"] == "torso_clothed_lower_unclothed"
    assert pkg["nudity_mode"] == "bottomless"
    assert "bottomless" in pkg["positive"]
    assert "no lower clothing" in pkg["positive"]
    assert "completely nude" not in pkg["positive"]


def test_nudity_policy_fully_nude_esplicita_e_blocca_vestiti():
    pack, state = _pack_state()
    state.player.outfit.worn = [
        "bare thighs clearly visible",
        "exposed shoulders",
        "recurved bow with bronze tips",
        "barefoot",
    ]
    state.player.outfit.removed = [
        "very short crimson wool chiton with deep low-cut neckline",
        "worn revealing leather armor with bronze studs",
        "thigh straps for quiver",
    ]
    contract = build_visual_contract(
        state,
        pack,
        _moment(
            visual_en=(
                "Ulisse stands bare-skinned on a high black volcanic rock ledge, "
                "exposed to harsh sunlight and sea wind"
            ),
            tags_en=["high black volcanic rock ledge", "sea wind"],
        ),
        0,
    )
    pkg = contract.prompt_package
    positive = pkg["positive"]
    negative = pkg["negative"]
    assert positive.startswith(LUNA)
    assert LUNA_LORA in positive
    assert pkg["detected_clothing_state"] == "no_torso_or_lower_clothing"
    assert pkg["nudity_mode"] == "fully_nude"
    for tag in ("completely nude", "fully naked", "no clothing", "no armor", "no dress", "no chiton", "barefoot"):
        assert tag in positive
        assert tag in pkg["nudity_tags_added"]
    for weak in ("bare thighs clearly visible", "exposed shoulders", "bare-skinned"):
        assert weak not in positive
    for blocked in ("bikini", "swimsuit", "underwear", "lingerie", "bra", "panties", "dress", "skirt", "armor", "chiton", "clothing"):
        assert blocked in negative
        assert blocked in pkg["clothing_block_tags_added"]
    assert "Ulisse stands completely nude" in contract.visual_en


def test_nudity_policy_base_prompt_protetto_non_modificato():
    pack, state = _pack_state()
    state.player.outfit.worn = ["barefoot"]
    state.player.outfit.removed = [
        "very short crimson wool chiton with deep low-cut neckline",
        "worn revealing leather armor with bronze studs",
    ]
    contract = build_visual_contract(
        state,
        pack,
        _moment(visual_en="Ulisse stands completely nude in the sea wind"),
        0,
    )
    pkg = contract.prompt_package
    assert pkg["base_prompt_by_character"]["player"] == LUNA
    assert pkg["positive"].startswith(LUNA)
    assert "<lora:stsDebbie-10e:0.7>" in pkg["positive"]
    assert "<lora:Expressive_H-000001:0.35>" in pkg["positive"]
    assert "<lora:FantasyWorldPonyV2:0.40>" in pkg["positive"]
