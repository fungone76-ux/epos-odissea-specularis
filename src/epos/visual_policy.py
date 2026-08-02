"""Pure visual policy helpers and static negative prompt fragments."""

from __future__ import annotations

from typing import Any


# Negativo corto in stile Pony/SDXL: i negativi lunghi diluiscono
# l'attenzione e peggiorano il risultato. Le esclusioni specifiche del
# mondo restano in `negative_extra_en` del pack; quelle di scena al
# visual del turno.
DEFAULT_NEGATIVE = (
    "score_6, score_5, score_4, score_3, score_2, score_1, lowres, "
    "worst quality, low quality, blurry, bad anatomy, bad hands, "
    "extra fingers, missing fingers, extra limbs, deformed, "
    "text, watermark, signature, child, young-looking"
)


def _identity_layer_policy_enabled(pack: Any) -> bool:
    return bool(getattr(pack.visual_policy, "sanitize_identity_layers", False))


def _avoid_facial_policy_enabled(pack: Any) -> bool:
    return bool(getattr(pack.visual_policy, "avoid_facial_expressions", False))


def _concise_role_policy_enabled(pack: Any) -> bool:
    return bool(getattr(pack.visual_policy, "concise_role_prompts", False))


def _single_character_negative() -> str:
    return (
        "multiple people, extra person, background people, duplicate character, "
        "cloned face, merged bodies, fused bodies, extra face"
    )


def _multi_character_negative() -> str:
    return (
        "merged bodies, fused faces, same face, identical faces, twins, "
        "extra head, missing head, extra arms, wrong body ownership, "
        "background people"
    )
