from epos.contract import (
    CheckProposal,
    DialogueLine,
    DisclosureEvent,
    FinalScene,
    GmPhaseResponse,
    InitiativeEvent,
    MemoryProposal,
    Mutation,
    VisualMoment,
)
from epos.turn_service import _phase_response_to_dict, _scene_to_dict



def test_turn_diagnostics_reexport_facade_symbols():
    from epos import turn_diagnostics, turn_service

    assert turn_service._phase_response_to_dict is turn_diagnostics._phase_response_to_dict
    assert turn_service._scene_to_dict is turn_diagnostics._scene_to_dict

def _full_scene() -> FinalScene:
    return FinalScene(
        narration="La scena procede.",
        dialogue=[DialogueLine(speaker="luna", text="Vieni.", to="player")],
        npc_actions=[{"npc_id": "luna", "action": "osserva"}],
        intentions=[{"npc_id": "luna", "intent": "proteggere"}],
        initiatives=[
            InitiativeEvent(
                source="luna",
                type="assist",
                summary="Luna interviene.",
                reason="Il player e in difficolta.",
                target="player",
            )
        ],
        disclosure_events=[
            DisclosureEvent(
                npc_id="luna",
                fact="conosce il passaggio",
                action="partial_truth",
                tactic="allusione",
            )
        ],
        mutations=[
            Mutation(
                type="story_marker_add",
                target="world",
                payload={"marker_id": "marker_luna_aiuta"},
                reason="Aiuto ottenuto.",
            )
        ],
        memory_events=[
            MemoryProposal(
                summary="Luna ha aiutato il player.",
                witnesses=["luna"],
                source="observed",
                credibility=1.0,
                level="immediate",
                emotional_impact=1,
                public=True,
            )
        ],
        visual=VisualMoment(
            summary="Luna aiuta il player",
            focus_character="luna",
            visible_characters=["luna", "player"],
            shared_action=True,
            visual_en="Luna helps the player near the canal.",
            tags_en=["two characters", "canal"],
            moment_type="action",
            speaker_character="luna",
            actor_character="luna",
            reactor_character="player",
            intimate_shared_moment=False,
            multi_character_reason="actor and reactor",
            multi_character_participants=["luna", "player"],
        ),
    )


def test_scene_to_dict_preserves_diagnostic_shape_and_order():
    assert _scene_to_dict(_full_scene()) == {
        "narration": "La scena procede.",
        "dialogue": [{"speaker": "luna", "text": "Vieni.", "to": "player"}],
        "npc_actions": [{"npc_id": "luna", "action": "osserva"}],
        "intentions": [{"npc_id": "luna", "intent": "proteggere"}],
        "initiatives": [
            {
                "source": "luna",
                "type": "assist",
                "summary": "Luna interviene.",
                "reason": "Il player e in difficolta.",
                "target": "player",
            }
        ],
        "disclosure_events": [
            {
                "npc_id": "luna",
                "fact": "conosce il passaggio",
                "action": "partial_truth",
                "tactic": "allusione",
            }
        ],
        "mutations": [
            {
                "type": "story_marker_add",
                "target": "world",
                "payload": {"marker_id": "marker_luna_aiuta"},
                "reason": "Aiuto ottenuto.",
            }
        ],
        "memory_events": [
            {
                "summary": "Luna ha aiutato il player.",
                "witnesses": ["luna"],
                "source": "observed",
                "credibility": 1.0,
                "level": "immediate",
                "emotional_impact": 1,
                "public": True,
            }
        ],
        "visual": {
            "summary": "Luna aiuta il player",
            "focus_character": "luna",
            "visible_characters": ["luna", "player"],
            "shared_action": True,
            "visual_en": "Luna helps the player near the canal.",
            "tags_en": ["two characters", "canal"],
            "moment_type": "action",
            "speaker_character": "luna",
            "actor_character": "luna",
            "reactor_character": "player",
            "intimate_shared_moment": False,
            "multi_character_reason": "actor and reactor",
            "multi_character_participants": ["luna", "player"],
        },
    }


def test_phase_response_to_dict_preserves_modes():
    check = CheckProposal(
        action_kind="force",
        skill="physical",
        difficulty=2,
        target_ids=["door"],
        opposition="none",
        reason="aprire",
        stakes={"success": "apri", "mixed": "apri con rumore", "failure": "resta chiusa"},
    )

    assert _phase_response_to_dict(GmPhaseResponse(mode="no_check", scene=_full_scene()))[
        "mode"
    ] == "no_check"
    assert _phase_response_to_dict(
        GmPhaseResponse(mode="check_proposal", check=check)
    ) == {"mode": "check_proposal", "check": check.to_dict()}
    assert _phase_response_to_dict(
        GmPhaseResponse(mode="clarification", clarification="Specifica meglio.")
    ) == {"mode": "clarification", "clarification": "Specifica meglio."}
