"""Phase 2 final-scene prompt builder."""

from __future__ import annotations

from typing import Any

from .models import WorldState
from .narrative_policy import derive_narrative_policy, narrative_policy_prompt
from .prompt_rules import (
    CONFRONT_BLOCK,
    ODYSSEY_VISUAL_RULES,
    PHASE2_INSTRUCTIONS,
    PLAYER_NARRATION_BLOCK,
    SCENE_FORMAT_RULES,
    SYSTEM_PROMPT,
    TEMERARIO_PRICE_BLOCK,
)
from .prompt_snapshot import _compact_snapshot, build_snapshot
from .worldpack import WorldPack


def _extras_block(extras: dict[str, Any] | None) -> str:
    if not extras:
        return ""
    parts: list[str] = []
    if extras.get("is_confront"):
        parts.append(CONFRONT_BLOCK)
    if extras.get("player_narration"):
        parts.append(
            PLAYER_NARRATION_BLOCK.format(player_narration=extras["player_narration"])
        )
    if extras.get("temerario_price"):
        parts.append(TEMERARIO_PRICE_BLOCK.format(temerario_price=extras["temerario_price"]))
    return "\n".join(parts)

def phase2_messages(
    state: WorldState,
    pack: WorldPack,
    player_text: str,
    proposal_dict: dict[str, Any],
    roll_dict: dict[str, Any],
    stake: str,
    extras: dict[str, Any] | None = None,
    compact: bool = False,
) -> list[dict[str, str]]:
    import json

    snapshot = build_snapshot(state, pack, player_text)
    if compact:
        snapshot = _compact_snapshot(snapshot)
    narrative_policy = derive_narrative_policy(state, pack, player_text, phase="final_scene")
    user = (
        "FASE_GM: final_scene\n"
        "OBIETTIVO_FASE: narra soltanto l'esito gia risolto dal runtime Python.\n\n"
        "SNAPSHOT DELLO STATO (fatti autorevoli):\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=1)
        + "\n\nPROVA VALIDATA DAL RUNTIME:\n"
        + json.dumps(proposal_dict, ensure_ascii=False, indent=1)
        + "\n\nESITO AUTOREVOLE:\n"
        + json.dumps(roll_dict, ensure_ascii=False, indent=1)
        + "\n\n"
        + narrative_policy_prompt(narrative_policy)
        + "\n"
        + PHASE2_INSTRUCTIONS.format(
            outcome=roll_dict.get("outcome", roll_dict.get("winner", "")),
            stake=stake,
            extras_block=_extras_block(extras),
        )
        + "\n\n"
        + SCENE_FORMAT_RULES
        + ("\n\n" + ODYSSEY_VISUAL_RULES if pack.visual_policy.speaker_action_focus else "")
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
