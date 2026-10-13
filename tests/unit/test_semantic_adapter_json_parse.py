"""Sanctioned model-output JSON parser (#1923): equivalent on valid objects, fail-closed otherwise."""

from __future__ import annotations

import pytest

from nexus.engine.semantic_adapter import (
    ModelOutputNotObjectError,
    ModelOutputParseError,
    SemanticAdapter,
    parse_model_json_object,
)
from nexus.services.s2t_strict import robust_json_parse


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('{"a": 1, "b": null, "c": true}', {"a": 1, "b": None, "c": True}),
        ("{'a': 1, 'b': None, 'c': True}", {"a": 1, "b": None, "c": True}),
        ("{'a': 'it''s'}", {"a": "its"}),
        ("{'reason': 'annull', 'flag': 'None_id'}", {"reason": "annull", "flag": "None_id"}),
    ],
)
def test_valid_objects_parse(raw: str, expected: dict) -> None:
    assert parse_model_json_object(raw) == expected
    assert robust_json_parse(raw) == expected
    assert SemanticAdapter.parse_json_object(raw) == expected


@pytest.mark.parametrize("raw", ["[1, 2]", '"text"', "42", "null"])
def test_non_object_json_fails_closed(raw: str) -> None:
    with pytest.raises(ModelOutputNotObjectError):
        robust_json_parse(raw)


@pytest.mark.parametrize("raw", ["", "I think candidate A is best", "{'a': ", "```json\n{}\n```"])
def test_unparseable_output_fails_closed(raw: str) -> None:
    with pytest.raises(ModelOutputParseError):
        robust_json_parse(raw)


def test_non_string_input_fails_closed() -> None:
    with pytest.raises(ModelOutputParseError):
        parse_model_json_object(b'{"a": 1}')  # type: ignore[arg-type]
