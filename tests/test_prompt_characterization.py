import hashlib
import json
from pathlib import Path

from epos.contract import CheckProposal
from epos.prompt import (
    PHASE1_INSTRUCTIONS,
    PHASE2_INSTRUCTIONS,
    SCENE_FORMAT_RULES,
    SYSTEM_PROMPT,
    _compact_snapshot,
    build_snapshot,
    phase1_messages,
    phase2_messages,
)
from epos.rules import Outcome, Roll
from epos.worldpack import load_pack


PACK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"
PLAYER_TEXT = "Chiedo a Maera del sentiero nord."


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _case():
    pack = load_pack(PACK)
    state = pack.new_world("prompt-characterization")
    proposal = CheckProposal(
        action_kind="social",
        skill="dolos",
        difficulty=2,
        target_ids=["maera"],
        opposition="npc_resistance",
        reason="Maera decide se fidarsi.",
        stakes={
            "full_success": "Maera si fida.",
            "partial_success": "Maera offre un indizio.",
            "failure": "Maera resta sospettosa.",
            "critical_failure": "Maera chiama aiuto.",
        },
    )
    roll = Roll(
        pool_size=3,
        difficulty=2,
        dice=(6, 4, 1),
        outcome=Outcome.PARTIAL_SUCCESS,
    )
    return pack, state, proposal, roll


def test_prompt_public_facade_exports_existing_symbols():
    assert SYSTEM_PROMPT.startswith("Sei il Game Master")
    assert "check_proposal" in PHASE1_INSTRUCTIONS
    assert "SCENA" in PHASE2_INSTRUCTIONS
    assert "visual" in SCENE_FORMAT_RULES
    assert build_snapshot is not None
    assert phase1_messages is not None
    assert phase2_messages is not None
    assert _compact_snapshot is not None


def test_snapshot_and_prompt_outputs_are_byte_stable():
    pack, state, proposal, roll = _case()
    snapshot = build_snapshot(state, pack, PLAYER_TEXT)

    outputs = {
        "snapshot": json.dumps(snapshot, ensure_ascii=False, indent=1),
        "compact_snapshot": json.dumps(
            _compact_snapshot(snapshot), ensure_ascii=False, indent=1
        ),
        "phase1": phase1_messages(state, pack, PLAYER_TEXT)[-1]["content"],
        "phase1_compact": phase1_messages(state, pack, PLAYER_TEXT, compact=True)[-1][
            "content"
        ],
        "phase2": phase2_messages(
            state,
            pack,
            PLAYER_TEXT,
            proposal.to_dict(),
            roll.to_dict(),
            "Maera offre un indizio.",
            {"player_narration": "La ringrazio senza insistere."},
        )[-1]["content"],
        "phase2_compact": phase2_messages(
            state,
            pack,
            PLAYER_TEXT,
            proposal.to_dict(),
            roll.to_dict(),
            "Maera offre un indizio.",
            {"player_narration": "La ringrazio senza insistere."},
            compact=True,
        )[-1]["content"],
    }

    assert {key: _hash(value) for key, value in outputs.items()} == {
        "snapshot": "aedd1a5d08c4f470a21c41664b26a94fd9f2b8eb134b3dd7470fb0bf4f9cc125",
        "compact_snapshot": "e9051e02157dac591cee691746a8bb00c6176a26a6b96164d0f36f3b1dc63c36",
        "phase1": "51b53142c2579c392af13f94fe2f298eb3c990f7621ff637949d5c4767b12cd8",
        "phase1_compact": "1069c8622e9bab2a8d7e32f212a40cfd2e4c37decb423839dcbee5e97eb481e6",
        "phase2": "4f96596628050ef52144f1ab48e3cd88d5a64c704475933e051d17e7dae61f78",
        "phase2_compact": "ee164bf8907b988499b4fa14ac726ee798e6d2af27b5a8ad0e1651d4e883a2ed",
    }
