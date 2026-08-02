"""Pure serialization helpers for turn diagnostics and artifacts."""

from __future__ import annotations

from typing import Any

from .contract import FinalScene, GmPhaseResponse


def _phase_response_to_dict(phase1: GmPhaseResponse) -> dict[str, Any]:
    if phase1.mode == "no_check":
        return {"mode": "no_check", "scene": _scene_to_dict(phase1.scene)}
    if phase1.mode == "confront_proposal":
        return {"mode": "confront_proposal", "confront": phase1.confront.to_dict()}
    if phase1.mode == "clarification":
        return {"mode": "clarification", "clarification": phase1.clarification}
    return {"mode": "check_proposal", "check": phase1.check.to_dict()}


def _scene_to_dict(scene: FinalScene) -> dict[str, Any]:
    return {
        "narration": scene.narration,
        "dialogue": [{"speaker": d.speaker, "text": d.text, "to": d.to} for d in scene.dialogue],
        "npc_actions": scene.npc_actions,
        "intentions": scene.intentions,
        "initiatives": [
            {
                "source": i.source,
                "type": i.type,
                "summary": i.summary,
                "reason": i.reason,
                "target": i.target,
            }
            for i in scene.initiatives
        ],
        "disclosure_events": [
            {"npc_id": d.npc_id, "fact": d.fact, "action": d.action, "tactic": d.tactic}
            for d in scene.disclosure_events
        ],
        "mutations": [
            {"type": m.type, "target": m.target, "payload": m.payload, "reason": m.reason}
            for m in scene.mutations
        ],
        "memory_events": [
            {
                "summary": m.summary,
                "witnesses": m.witnesses,
                "source": m.source,
                "credibility": m.credibility,
                "level": m.level,
                "emotional_impact": m.emotional_impact,
                "public": m.public,
            }
            for m in scene.memory_events
        ],
        "visual": (
            {
                "summary": scene.visual.summary,
                "focus_character": scene.visual.focus_character,
                "visible_characters": scene.visual.visible_characters,
                "shared_action": scene.visual.shared_action,
                "visual_en": scene.visual.visual_en,
                "tags_en": scene.visual.tags_en,
                "moment_type": scene.visual.moment_type,
                "speaker_character": scene.visual.speaker_character,
                "actor_character": scene.visual.actor_character,
                "reactor_character": scene.visual.reactor_character,
                "intimate_shared_moment": scene.visual.intimate_shared_moment,
                "multi_character_reason": scene.visual.multi_character_reason,
                "multi_character_participants": scene.visual.multi_character_participants,
            }
            if scene.visual
            else None
        ),
    }
