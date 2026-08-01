"""Runtime compatibility for Resort NPC actions.

``FinalScene.from_dict`` keeps ``npc_actions`` as dictionaries.  Older Resort
helpers expected attribute-based objects and therefore ignored valid actions,
rejecting the final scene before rendering.  This patch makes the canonical
validator accept both representations without weakening presence checks.
"""

from __future__ import annotations

from .validators import ValidationReport

_INSTALLED = False


def _field(item, name: str, default=""):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def install_resort_npc_action_patch() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import resort_turn_service as module

    original_validate = module.validate_resort_scene_policy
    original_npc_from_scene = module._npc_from_scene

    def validate_resort_scene_policy(state, pack, scene):
        report = original_validate(state, pack, scene)
        present = set(state.present_npc_ids())
        has_present_action = any(
            str(_field(action, "npc_id", "")) in present
            for action in getattr(scene, "npc_actions", [])
        )
        if not has_present_action:
            return report

        errors = [
            error
            for error in report.errors
            if error.code != "resort_npc_response_required"
        ]
        if len(errors) == len(report.errors):
            return report
        return ValidationReport(
            problems=[error.message for error in errors],
            errors=errors,
            warnings=list(report.warnings),
        )

    def npc_from_scene(state, scene):
        intro_step = module.current_intro_step(state)
        if intro_step is not None and intro_step.npc_id in state.npcs:
            return intro_step.npc_id

        present = [
            npc_id for npc_id in state.present_npc_ids() if npc_id in state.npcs
        ]
        if not present:
            return None

        for line in scene.dialogue:
            npc_id = module._speaker_id(state, getattr(line, "speaker", ""))
            if npc_id in present:
                return npc_id

        for action in scene.npc_actions:
            npc_id = str(_field(action, "npc_id", ""))
            if npc_id in present:
                return npc_id

        for initiative in scene.initiatives:
            npc_id = str(_field(initiative, "source", ""))
            if npc_id in present:
                return npc_id

        visual = scene.visual
        if visual is not None:
            for candidate in (
                visual.speaker_character,
                visual.actor_character,
                visual.reactor_character,
                visual.focus_character,
                *visual.visible_characters,
            ):
                if candidate in present:
                    return candidate

        return present[0]

    module.validate_resort_scene_policy = validate_resort_scene_policy
    module._npc_from_scene = npc_from_scene
    _INSTALLED = True
