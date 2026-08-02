from pathlib import Path

from epos.contract import CheckProposal, ConfrontProposal, FinalScene
from epos.validators import (
    ValidationReport,
    validate_check_proposal,
    validate_confront_proposal,
    validate_scene,
)
from epos.worldpack import load_pack


PACK_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "demo_pack"


def _state_and_pack():
    pack = load_pack(PACK_DIR)
    return pack.new_world("validators-refactor"), pack


def _scene(**overrides):
    data = {
        "narration": "Scena.",
        "visual": {
            "summary": "momento",
            "focus_character": "maera",
            "visible_characters": ["maera"],
            "shared_action": False,
            "visual_en": "a quiet moment",
            "tags_en": [],
        },
    }
    data.update(overrides)
    return FinalScene.from_dict(data)


def test_validators_public_api_is_stable():
    import epos.validators as validators

    assert [name for name in dir(validators) if not name.startswith("_")] == [
        "Any",
        "CheckProposal",
        "ConfrontProposal",
        "FinalScene",
        "KNOWLEDGE_SOURCES",
        "MAX_DIFFICULTY",
        "MAX_EMOTIONAL_IMPACT",
        "MAX_RELATIONSHIP_DELTA",
        "MAX_RESOURCE_DELTA",
        "MIN_DIFFICULTY",
        "Mutation",
        "Outfit",
        "RELATIONSHIP_DOMAINS",
        "ValidationErrorDetail",
        "ValidationReport",
        "ValidationWarning",
        "WorldPack",
        "WorldState",
        "annotations",
        "dataclass",
        "field",
        "outfit_state",
        "player_aliases_for_state",
        "re",
        "validate_check_proposal",
        "validate_confront_proposal",
        "validate_scene",
    ]


def test_validation_report_problem_mapping_golden():
    report = ValidationReport(
        problems=[
            "memory_event richiede witnesses non vuoto",
            "visual: personaggio visibile ma assente 'luna'",
            "relationship_delta: target inesistente 'ghost'",
        ]
    )

    assert report.to_dict(stage="semantic", phase="phase2") == {
        "valid": False,
        "validation_stage": "semantic",
        "phase": "phase2",
        "errors": [
            {
                "code": "memory_without_witnesses",
                "path": "memory_events",
                "message": "memory_event richiede witnesses non vuoto",
                "details": {},
            },
            {
                "code": "visible_character_not_present",
                "path": "visual.visible_characters",
                "message": "visual: personaggio visibile ma assente 'luna'",
                "details": {},
            },
            {
                "code": "invalid_mutation_target",
                "path": "mutations.relationship_delta",
                "message": "relationship_delta: target inesistente 'ghost'",
                "details": {},
            },
        ],
        "warnings": [],
        "problems": [
            "memory_event richiede witnesses non vuoto",
            "visual: personaggio visibile ma assente 'luna'",
            "relationship_delta: target inesistente 'ghost'",
        ],
    }


def test_check_proposal_issue_order_and_messages_golden():
    state, pack = _state_and_pack()
    proposal = CheckProposal(
        action_kind="social",
        skill="",
        difficulty=99,
        target_ids=["ghost"],
        opposition="npc_resistance",
        stakes={},
    )

    report = validate_check_proposal(state, pack, proposal)

    assert report.problems == [
        "difficolt\u00c3\u00a0 99 fuori range 1-6",
        "skill della prova non dichiarata",
        "target inesistente: 'ghost'",
        "opposizione npc_resistance senza un NPC bersaglio",
    ]
    assert [error.code for error in report.errors] == [
        "semantic_contract_rejected",
        "missing_required_field",
        "unknown_npc_id",
        "semantic_contract_rejected",
    ]
    assert [error.path for error in report.errors] == [
        "check.difficulty",
        "check.skill",
        "check.target_ids[0]",
        "check.opposition",
    ]

def test_confront_proposal_issue_order_and_messages_golden():
    state, pack = _state_and_pack()
    proposal = ConfrontProposal(skill="", target_id="corren", stakes={})

    report = validate_confront_proposal(state, pack, proposal)

    assert report.problems == [
        "confronto con NPC assente: 'corren'",
        "skill del confronto non dichiarata",
    ]
    assert [error.code for error in report.errors] == [
        "actor_character_not_present",
        "missing_required_field",
    ]
    assert [error.path for error in report.errors] == [
        "confront.target_id",
        "confront.skill",
    ]

def test_scene_issue_order_and_messages_golden():
    state, pack = _state_and_pack()
    scene = _scene(
        dialogue=[{"speaker": "ghost", "text": "Sono qui."}],
        mutations=[
            {
                "type": "relationship_delta",
                "target": "ghost",
                "payload": {"unknown": 99},
            }
        ],
        memory_events=[
            {
                "summary": "Luna vede qualcosa",
                "witnesses": ["corren"],
                "emotional_impact": 4,
            }
        ],
        visual={
            "summary": "momento",
            "focus_character": "maera",
            "visible_characters": ["maera", "corren"],
            "shared_action": False,
            "visual_en": "Maera stands alone in the hall",
            "tags_en": [],
        },
    )

    report = validate_scene(state, pack, scene)

    assert report.problems == [
        "relationship_delta: target inesistente 'ghost'",
        "relationship_delta: dominio sconosciuto 'unknown'",
        "dialogo di speaker non presente: 'ghost'",
        "memory_event: testimone assente 'corren' \u00e2\u20ac\u201d un NPC non pu\u00c3\u00b2 ricordare ci\u00c3\u00b2 che non ha osservato",
        "memory_event: impatto emotivo 4 oltre il limite \u00c2\u00b13",
        "visual: personaggio visibile ma assente 'corren'",
    ]
    assert [error.code for error in report.errors] == [
        "unknown_npc_id",
        "invalid_memory_witness",
        "semantic_contract_rejected",
        "visible_character_not_present",
    ]
