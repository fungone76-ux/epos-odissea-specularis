from __future__ import annotations

from dataclasses import dataclass

from epos.worldpack import load_pack

from epos.visual import (
    DEFAULT_NEGATIVE,
    _avoid_facial_policy_enabled,
    _concise_role_policy_enabled,
    _identity_layer_policy_enabled,
    _multi_character_negative,
    _single_character_negative,
)


@dataclass
class _Policy:
    sanitize_identity_layers: bool = False
    avoid_facial_expressions: bool = False
    concise_role_prompts: bool = False


@dataclass
class _Pack:
    visual_policy: _Policy


def test_visual_policy_accessors_default_false():
    pack = _Pack(_Policy())

    assert _identity_layer_policy_enabled(pack) is False
    assert _avoid_facial_policy_enabled(pack) is False
    assert _concise_role_policy_enabled(pack) is False


def test_visual_policy_accessors_explicit_true_and_false():
    pack = _Pack(
        _Policy(
            sanitize_identity_layers=True,
            avoid_facial_expressions=True,
            concise_role_prompts=False,
        )
    )

    assert _identity_layer_policy_enabled(pack) is True
    assert _avoid_facial_policy_enabled(pack) is True
    assert _concise_role_policy_enabled(pack) is False


def test_negative_policy_fragments_are_stable_and_distinct():
    single = _single_character_negative()
    multi = _multi_character_negative()

    assert "multiple people" in single
    assert "background people" in single
    assert "merged bodies" in multi
    assert "identical faces" in multi
    assert single != multi


def test_default_negative_keeps_short_safety_terms():
    assert "child" in DEFAULT_NEGATIVE
    assert "young-looking" in DEFAULT_NEGATIVE
    assert len(DEFAULT_NEGATIVE.split(",")) <= 25


def test_worldpack_without_visual_policy_uses_default_false_accessors(tmp_path):
    (tmp_path / "world.yaml").write_text(
        "id: temp_policy_pack\ntitle: Temp Policy\nstart_location_id: room\n"
        "locations:\n  - id: room\n    name: Room\n",
        encoding="utf-8",
    )
    pack = load_pack(tmp_path)

    assert _identity_layer_policy_enabled(pack) is False
    assert _avoid_facial_policy_enabled(pack) is False
    assert _concise_role_policy_enabled(pack) is False