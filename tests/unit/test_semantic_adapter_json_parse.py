"""Sanctioned model-output JSON parser (#1923): equivalent on valid input, fail-closed otherwise."""

from __future__ import annotations

import pytest

from nexus.contracts.model_output_json import (
    ModelOutputParseError,
    ModelOutputShapeError,
    parse_model_json,
    parse_model_json_array,
    parse_model_json_object,
)
from nexus.engine.semantic_adapter import SemanticAdapter
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
def test_valid_objects_parse_leniently(raw: str, expected: dict) -> None:
    assert parse_model_json_object(raw) == expected
    assert robust_json_parse(raw) == expected
    assert SemanticAdapter.parse_json_object(raw) == expected


@pytest.mark.parametrize("raw", ["[1, 2]", '"text"', "42", "null"])
def test_non_object_json_fails_closed(raw: str) -> None:
    with pytest.raises(ModelOutputShapeError):
        robust_json_parse(raw)


@pytest.mark.parametrize("raw", ["", "I think candidate A is best", "{'a': ", "```json\n{}\n```"])
def test_unparseable_output_fails_closed(raw: str) -> None:
    with pytest.raises(ModelOutputParseError):
        robust_json_parse(raw)


def test_non_string_input_fails_closed() -> None:
    with pytest.raises(ModelOutputParseError):
        parse_model_json_object(b'{"a": 1}')  # type: ignore[arg-type]


def test_strict_mode_accepts_only_standard_json() -> None:
    assert parse_model_json_object('{"a": 1}', mode="strict") == {"a": 1}
    with pytest.raises(ModelOutputParseError):
        parse_model_json_object("{'a': 1}", mode="strict")


def test_pydict_mode_skips_literal_eval() -> None:
    assert parse_model_json_object("{'a': 1, 'b': True}", mode="pydict") == {"a": 1, "b": True}
    with pytest.raises(ModelOutputParseError):
        parse_model_json_object("{'a': 'it''s'}", mode="pydict")


def test_array_expectation() -> None:
    assert parse_model_json_array('["step one", "step two"]') == ["step one", "step two"]
    with pytest.raises(ModelOutputShapeError):
        parse_model_json_array('{"steps": []}')
    with pytest.raises(ModelOutputParseError):
        parse_model_json_array("['a', 'b']")  # strict by default


def test_unknown_expectation_or_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_model_json("{}", expect="set")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        parse_model_json("{}", expect="object", mode="loose")  # type: ignore[arg-type]
