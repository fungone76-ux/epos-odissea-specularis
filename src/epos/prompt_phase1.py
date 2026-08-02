"""Phase 1 Game Master prompt builder."""

from __future__ import annotations

from .models import WorldState
from .narrative_policy import derive_narrative_policy, narrative_policy_prompt
from .prompt_rules import ODYSSEY_VISUAL_RULES, PHASE1_INSTRUCTIONS, SYSTEM_PROMPT
from .prompt_snapshot import _compact_snapshot, build_snapshot
from .prompt_visual_rules import RESORT_VISUAL_GENERATION_RULES
from .worldpack import WorldPack


def _system_prompt_for_pack(pack: WorldPack) -> str:
    if getattr(pack, "id", "") != "resort_world":
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + "\n\n" + RESORT_VISUAL_GENERATION_RULES


def phase1_messages(
    state: WorldState,
    pack: WorldPack,
    player_text: str,
    compact: bool = False,
) -> list[dict[str, str]]:
    import json

    snapshot = build_snapshot(state, pack, player_text)
    if compact:
        snapshot = _compact_snapshot(snapshot)
    user = (
        "FASE_GM: proposal\n"
        "OBIETTIVO_FASE: interpreta l'input e restituisci no_check, check_proposal, confront_proposal o clarification.\n\n"
        "SNAPSHOT DELLO STATO (fatti autorevoli):\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=1)
        + "\n\n"
        + narrative_policy_prompt(derive_narrative_policy(state, pack, player_text, phase="proposal"))
        + "\n"
        + PHASE1_INSTRUCTIONS
        + ("\n\n" + ODYSSEY_VISUAL_RULES if pack.visual_policy.speaker_action_focus else "")
    )
    return [
        {"role": "system", "content": _system_prompt_for_pack(pack)},
        {"role": "user", "content": user},
    ]
