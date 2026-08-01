"""Il pack definitivo Acque Chiuse: caricamento, coerenza, formato esteso."""

from pathlib import Path

import pytest

from epos.gm import DemoGameMaster
from epos.prompt import build_snapshot
from epos.state_store import StateStore
from epos.turn_service import TurnService
from epos.validators import validate_scene
from epos.contract import FinalScene
from epos.worldpack import load_pack

PACK_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "acque_chiuse"


@pytest.fixture
def pack():
    return load_pack(PACK_DIR)


@pytest.fixture
def state(pack):
    return pack.new_world("acque-test")


class TestPackStructure:
    def test_pack_loads(self, pack):
        assert pack.id == "acque_chiuse"
        assert pack.open_end is True
        assert pack.riserva_dice == 2

    def test_six_locations(self, pack):
        assert set(pack.locations) == {
            "vasche_grandi", "sala_comune", "serra_umida",
            "cantine_acqua", "alloggi", "sentiero",
        }

    def test_five_npcs_all_adults(self, pack):
        assert set(pack.npc_canon) == {"marea", "ilsa", "vel", "rook", "lienne"}
        for npc in pack.npc_canon.values():
            assert npc.age >= 18

    def test_every_npc_has_confront_skills(self, pack):
        for npc in pack.npc_canon.values():
            assert npc.skills, f"{npc.id} senza skill per i confronti"

    def test_every_npc_has_secrets_and_policy(self, pack):
        for npc in pack.npc_canon.values():
            assert npc.secrets, f"{npc.id} senza segreti"
            assert npc.disclosure_policy, f"{npc.id} senza disclosure_policy"

    def test_story_spine_has_conclusion(self, pack):
        concluding = [m for m in pack.story_markers.values() if m.concludes_slice]
        assert len(concluding) == 1
        assert concluding[0].id == "truth_of_nila"

    def test_three_pressures(self, pack):
        assert set(pack.pressures) == {"disgelo", "agenti", "infusioni"}

    def test_world_facts_have_does_not_imply(self, pack):
        assert len(pack.world_facts) >= 6
        for fact in pack.world_facts.values():
            assert fact.does_not_imply, f"{fact.id} senza inferenze vietate"

    def test_relationships_have_known_by(self, pack):
        assert len(pack.relationships) >= 4
        for rel in pack.relationships:
            assert rel.known_by, f"{rel.from_id}->{rel.to_id} senza known_by"
            for known in rel.known_by:
                assert known in pack.npc_canon, f"{known} non è un NPC del pack"

    def test_npc_locations_exist(self, pack):
        for npc in pack.npc_canon.values():
            assert npc.location_id in pack.locations

    def test_only_marea_present_at_start(self, pack, state):
        present = state.present_npc_ids()
        assert present == ["marea"]


class TestSnapshot:
    def test_facts_in_snapshot(self, pack, state):
        snapshot = build_snapshot(state, pack, "mi guardo intorno")
        assert len(snapshot["world_facts"]) == len(pack.world_facts)
        nila = [f for f in snapshot["world_facts"] if "Nila" in f["statement"]]
        assert nila and nila[0]["does_not_imply"]

    def test_relationships_in_snapshot(self, pack, state):
        snapshot = build_snapshot(state, pack, "mi guardo intorno")
        affair = [
            r for r in snapshot["npc_relationships"]
            if r["from"] == "rook" and r["to"] == "lienne"
        ]
        assert affair
        assert set(affair[0]["known_by"]) == {"rook", "lienne", "vel"}

    def test_npc_secrets_in_snapshot_via_disclosure(self, pack, state):
        snapshot = build_snapshot(state, pack, "mi presento")
        marea = snapshot["present_npcs"][0]
        assert marea["disclosure"]["secrets"]
        assert marea["disclosure"]["disclosure_policy"]


class TestDefinitiveGameplay:
    def test_opening_turn_commits(self, pack, tmp_path):
        service = TurnService(
            gm=DemoGameMaster(), pack=pack, store=StateStore(tmp_path / "saves")
        )
        state = service.new_session()
        assert "Terme del Passo" in state.last_scene or "terme" in state.last_scene.casefold()
        result = service.play(state, "Accetto il lavoro e chiedo della stanza senz'acqua.")
        assert state.turn == 1
        assert result.narration

    def test_visual_package_uses_canonical_prompts(self, pack, state):
        from epos.contract import VisualMoment
        from epos.visual import build_visual_contract

        moment = VisualMoment.from_dict(
            {
                "summary": "Marea studia la nuova inserviente",
                "focus_character": "marea",
                "visible_characters": ["marea"],
                "shared_action": False,
                "visual_en": "the bathhouse mistress studying the new attendant across steaming pools",
                "tags_en": ["steam", "warm light"],
            }
        )
        contract = build_visual_contract(state, pack, moment, turn=0)
        assert "<lora:stsSmith-10e:0.65>" in contract.prompt_package["positive"]
        assert "steam" in contract.prompt_package["positive"]

    def test_canonical_player_sheet_survives_creation(self, pack, tmp_path):
        """La protagonista ha volto canonico: la creazione non lo sovrascrive."""
        from epos.creation import CreationAnswers

        service = TurnService(
            gm=DemoGameMaster(), pack=pack, store=StateStore(tmp_path / "saves")
        )
        answers = CreationAnswers(
            identity="Una viaggiatrice che sente troppo",
            appearance="qualunque cosa scriva il giocatore",
            skills={"potere_acqua": 2, "social": 1},
        )
        state = service.new_session(creation_answers=answers)
        assert "visual_overrides" not in state.flags  # il pack vince
        assert "potere_acqua" in state.player.skills


class TestCanonicalVisuals:
    """I LoRA e i base prompt devono essere quelli canonici del vecchio repo."""

    def test_identity_loras_canonical(self, pack):
        player = pack.visual_sheets["player"].base_prompt
        assert "stsdebbie" in player
        assert "<lora:stsDebbie-10e:0.7>" in player
        assert "<lora:stsSmith-10e:0.65>" in pack.visual_sheets["marea"].base_prompt
        assert (
            "<lora:alice_milf_catchers_lora.safetensors:0.7>"
            in pack.visual_sheets["ilsa"].base_prompt
        )
        assert (
            "<lora:vaela_orm_identity.safetensors:0.7>"
            in pack.visual_sheets["vel"].base_prompt
        )
        # i personaggi nuovi non hanno LoRA di identità inventati
        assert "<lora:" not in pack.visual_sheets["rook"].base_prompt
        assert "<lora:" not in pack.visual_sheets["lienne"].base_prompt

    def test_global_loras_suffix_canonical(self, pack):
        assert pack.visual_prompt_suffix_en == (
            "<lora:Expressive_H-000001:0.35>, <lora:FantasyWorldPonyV2:0.40>"
        )

    def test_global_suffix_applied_once_with_full_cast(self, pack, state):
        from epos.contract import VisualMoment
        from epos.visual import build_visual_contract

        for npc in state.npcs.values():
            npc.present = True
            npc.location_id = state.location_id
        moment = VisualMoment.from_dict(
            {
                "summary": "Tutti nella sala grande",
                "focus_character": "player",
                "visible_characters": ["player", "marea", "ilsa", "vel", "rook", "lienne"],
                "shared_action": True,
                "visual_en": "the whole cast around the steaming main pool",
                "tags_en": ["steam"],
            }
        )
        contract = build_visual_contract(state, pack, moment, turn=0)
        positive = contract.prompt_package["positive"]
        assert positive.count("<lora:Expressive_H-000001:0.35>") == 1
        assert positive.count("<lora:FantasyWorldPonyV2:0.40>") == 1
        assert positive.endswith(pack.visual_prompt_suffix_en)

    def test_player_starts_with_canonical_outfit(self, pack, state):
        worn = state.player.outfit.worn
        assert "cropped fitted dark leather top with deep neckline" in worn
        assert "barefoot" in worn

    def test_canonical_negative(self, pack, state):
        from epos.contract import VisualMoment
        from epos.visual import build_visual_contract

        moment = VisualMoment.from_dict(
            {
                "summary": "Marea studia la nuova inserviente",
                "focus_character": "marea",
                "visible_characters": ["marea"],
                "shared_action": False,
                "visual_en": "the bathhouse mistress studying the new attendant",
                "tags_en": ["steam"],
            }
        )
        contract = build_visual_contract(state, pack, moment, turn=0)
        negative = contract.prompt_package["negative"]
        assert "score_4, score_3, score_2, score_1" in negative
        assert "child, young-looking" in negative
        assert "modest clothing" in negative  # extra di pack
