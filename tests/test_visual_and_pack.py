"""Visual contract, prompt package, world-pack, persistenza."""

from pathlib import Path

import pytest

from epos.contract import VisualMoment
from epos.renderers import PendingRenderer
from epos.state_store import StateStore
from epos.visual import build_visual_contract, compile_prompt_package
from epos.worldpack import WorldPackError, load_pack

PACK_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


@pytest.fixture
def pack():
    return load_pack(PACK_DIR)


@pytest.fixture
def state(pack):
    return pack.new_world("viz-session")


class TestWorldPack:
    def test_demo_pack_loads(self, pack):
        assert pack.start_location_id == "common_hall"
        assert "maera" in pack.npc_canon
        assert "player" in pack.visual_sheets

    def test_new_world_initializes_presence(self, pack, state):
        assert state.npcs["maera"].present is True
        assert state.npcs["corren"].present is False
        assert state.player.resources == {"strain": 0}

    def test_new_world_opening_narration(self, pack, state):
        assert "stazione di posta" in state.last_scene

    def test_underage_npc_rejected(self, tmp_path):
        (tmp_path / "world.yaml").write_text(
            "id: x\ntitle: x\nstart_location_id: a\n"
            "locations:\n  - id: a\n    name: A\n",
            encoding="utf-8",
        )
        (tmp_path / "npcs.yaml").write_text(
            "npcs:\n  - id: kid\n    name: Kid\n    age: 15\n    location_id: a\n",
            encoding="utf-8",
        )
        with pytest.raises(WorldPackError, match="adulta"):
            load_pack(tmp_path)

    def test_unknown_start_location_rejected(self, tmp_path):
        (tmp_path / "world.yaml").write_text(
            "id: x\ntitle: x\nstart_location_id: nope\n"
            "locations:\n  - id: a\n    name: A\n",
            encoding="utf-8",
        )
        with pytest.raises(WorldPackError, match="start_location"):
            load_pack(tmp_path)


class TestPromptPackage:
    def test_base_prompt_copied_exactly(self, pack, state):
        characters = [
            {
                "id": "maera",
                "outfit_worn": ["grembiule di lana grigia"],
                "outfit_removed": [],
                "wounds": [],
            }
        ]
        package = compile_prompt_package(
            pack, ["maera"], characters, "a quiet moment at the inn", ["candlelight"]
        )
        canonical = pack.visual_sheets["maera"].base_prompt
        assert package["positive"].startswith(canonical)
        assert "a quiet moment at the inn" in package["positive"]
        assert "candlelight" in package["positive"]
        assert package["negative"]

    def test_order_base_outfit_visual_tags(self, pack, state):
        characters = [
            {
                "id": "maera",
                "outfit_worn": ["OUTFIT_TAG"],
                "outfit_removed": [],
                "wounds": [],
            }
        ]
        package = compile_prompt_package(
            pack, ["maera"], characters, "VISUAL_TAG", ["FREE_TAG"]
        )
        pos = package["positive"]
        # Convenzione Pony/SDXL: tag corti ad alto segnale prima della prosa
        assert pos.index("OUTFIT_TAG") < pos.index("FREE_TAG") < pos.index("VISUAL_TAG")

    def test_prompt_suffix_appended_once_at_end(self, pack, state):
        from dataclasses import replace

        pack2 = replace(pack, visual_prompt_suffix_en="GLOBAL_SUFFIX_TAG")
        characters = [
            {"id": "maera", "outfit_worn": [], "outfit_removed": [], "wounds": []},
            {"id": "player", "outfit_worn": [], "outfit_removed": [], "wounds": []},
        ]
        package = compile_prompt_package(
            pack2, ["maera", "player"], characters, "VISUAL", ["TAG"]
        )
        assert package["positive"].count("GLOBAL_SUFFIX_TAG") == 1
        assert package["positive"].endswith("GLOBAL_SUFFIX_TAG")

    def test_starting_outfit_en_wins_over_world_outfit(self, pack):
        from dataclasses import replace

        sheet = pack.visual_sheets["player"]
        sheet2 = replace(sheet, starting_outfit_en=("ENGLISH CANONICAL ITEM",))
        sheets = dict(pack.visual_sheets, player=sheet2)
        pack2 = replace(pack, visual_sheets=sheets)
        state2 = pack2.new_world("outfit-session")
        assert state2.player.outfit.worn == ["ENGLISH CANONICAL ITEM"]
        # gli NPC senza starting_outfit_en restano sullo starting_outfit
        # narrativo del pack
        assert state2.npcs["maera"].outfit.worn == list(
            pack.npc_canon["maera"].starting_outfit
        )


class TestVisualContract:
    def _moment(self, **overrides):
        data = {
            "summary": "Maera studia il giocatore",
            "focus_character": "maera",
            "visible_characters": ["maera"],
            "shared_action": False,
            "visual_en": "an innkeeper studying a stranger",
            "tags_en": ["firelight"],
        }
        data.update(overrides)
        return VisualMoment.from_dict(data)

    def test_build_and_roundtrip(self, pack, state):
        contract = build_visual_contract(state, pack, self._moment(), turn=0)
        assert contract.characters[0]["id"] == "maera"
        assert contract.prompt_package["positive"]
        from epos.visual import VisualContract

        restored = VisualContract.from_dict(contract.to_dict())
        assert restored == contract

    def test_outfit_authoritative_from_state(self, pack, state):
        state.npcs["maera"].outfit.remove_item("grembiule di lana grigia")
        contract = build_visual_contract(state, pack, self._moment(), turn=0)
        assert "grembiule di lana grigia" in contract.characters[0]["outfit_removed"]

    def test_absent_character_rejected(self, pack, state):
        with pytest.raises(ValueError, match="assenti"):
            build_visual_contract(
                state,
                pack,
                self._moment(focus_character="corren", visible_characters=["corren"]),
                turn=0,
            )


class TestPersistence:
    def test_state_roundtrip(self, pack, tmp_path):
        store = StateStore(tmp_path / "saves")
        state = pack.new_world("persist-test")
        state.player.outfit.remove_item("stivali infangati")
        state.npcs["maera"].relationship_towards("player").apply_delta({"trust": 7})
        store.save_state(state)

        loaded = store.load_state(state.session_id)
        assert loaded.to_dict() == state.to_dict()
        assert store.list_sessions() == ["persist-test"]

    def test_turn_artifacts_and_checkpoint_are_written_without_tmp_leftovers(self, pack, tmp_path):
        store = StateStore(tmp_path / "saves")
        state = pack.new_world("atomic-persist-test")
        store.save_state(state)

        artifact_path = store.save_turn_artifact(
            state.session_id, 0, "scene", {"narration": "ok"}
        )
        store.save_turn_artifact(state.session_id, 0, "scene", {"narration": "updated"})
        store.save_checkpoint(
            state.session_id,
            0,
            "check_resolved",
            {"skill": "dolos", "difficulty": 3},
            None,
        )

        assert artifact_path.name == "scene.json"
        assert store.load_turn_artifact(state.session_id, 0, "scene") == {
            "narration": "updated"
        }
        checkpoint = store.load_checkpoint(state.session_id)
        assert checkpoint["phase"] == "check_resolved"
        assert checkpoint["proposal"]["skill"] == "dolos"
        assert list((tmp_path / "saves").rglob("*.tmp")) == []

    def test_missing_session_raises(self, tmp_path):
        from epos.state_store import StateStoreError

        store = StateStore(tmp_path / "saves")
        with pytest.raises(StateStoreError):
            store.load_state("non-esiste")

    def test_pending_renderer(self, tmp_path):
        record = PendingRenderer().render({"positive": "x"}, tmp_path)
        assert record.status == "pending"


class TestDotenv:
    def test_loads_and_preserves_existing(self, tmp_path, monkeypatch):
        from epos.dotenv import load_dotenv

        env_file = tmp_path / ".env"
        env_file.write_text(
            "# commento\n\nEPOS_LLM_MODEL=gpt-test\n"
            "EPOS_LLM_API_KEY='chiave con spazi'\n"
            'EPOS_RENDER_MODE="comfy"\nriga_senza_uguale\n',
            encoding="utf-8",
        )
        monkeypatch.delenv("EPOS_LLM_MODEL", raising=False)
        monkeypatch.delenv("EPOS_LLM_API_KEY", raising=False)
        monkeypatch.setenv("EPOS_RENDER_MODE", "pending")  # già presente: vince
        load_dotenv(env_file)
        import os

        assert os.environ["EPOS_LLM_MODEL"] == "gpt-test"
        assert os.environ["EPOS_LLM_API_KEY"] == "chiave con spazi"
        assert os.environ["EPOS_RENDER_MODE"] == "pending"

    def test_missing_file_is_noop(self, tmp_path):
        from epos.dotenv import load_dotenv

        load_dotenv(tmp_path / "non_esiste.env")  # nessuna eccezione
