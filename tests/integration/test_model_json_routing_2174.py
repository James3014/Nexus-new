"""Characterization tests for model-text JSON sites routed through parse_model_json (#2174).

Valid JSON, fenced or prose-wrapped JSON, garbage and wrong-shape input must behave
exactly as they did with the bare ``json.loads`` call sites.
"""

from __future__ import annotations

import importlib.util

import pytest

from nexus.knowledge.autonomous_memory_curator import _parse_automem_response
from nexus.services.gateway import BattlesuitGateway


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"recommendations": ["a", " b ", ""]}', ["a", "b"]),
        ('Sure!\n```json\n{"recommendations": ["x"]}\n```', ["x"]),
        ('{"recommendations": "not-a-list"}', []),
        ("{'recommendations': ['single']}", []),
        ("{not json}", []),
        ("[1, 2]", []),
        ("", []),
    ],
)
def test_automem_response(raw, expected):
    assert _parse_automem_response(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"verdict": "pass", "confidence": 0.8}', ("pass", 0.8)),
        ('noise {"verdict": "maybe", "confidence": 7} tail', ("fail", 1.0)),
        ('{"verdict": "pass", "confidence": "x"}', ("fail", 0.0)),
        ("{broken", ("fail", 0.0)),
        ("{'verdict': 'pass'}", ("fail", 0.0)),
        ("", ("fail", 0.0)),
    ],
)
def test_verifier_response(raw, expected) -> None:
    del raw
    del expected
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert (
        importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier_runtime")
        is None
    )


def test_advisor_response() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_diagnosis_runtime") is None


def _gateway() -> BattlesuitGateway:
    return object.__new__(BattlesuitGateway)


def _parse(raw: str):
    return _gateway()._parse_json_result(raw, 10, "measured")


@pytest.mark.parametrize(
    "raw",
    [
        '{"status": "APPROVED", "summary": "ok", "violations": []}',
        '```json\n{"status": "APPROVED", "summary": "ok", "violations": []}\n```',
        'Here you go: {"status": "APPROVED", "summary": "ok", "violations": []} done',
    ],
)
def test_gateway_parse_valid_forms(raw):
    data, returned_raw = _parse(raw)
    assert returned_raw == raw
    assert data["status"] == "APPROVED"
    assert data["tokens_used"] == 10


def test_gateway_parse_defaults_filled():
    data, _ = _parse("{}")
    assert data["status"] == "FAIL"
    assert data["summary"] == "No summary provided"
    assert data["violations"] == []


@pytest.mark.parametrize(
    "raw",
    ["no json here", "{broken", "```json\n{broken\n```", "[1, 2]", '"text"', "null", "{'a': 1}"],
)
def test_gateway_parse_bad_input_is_parse_failure(raw):
    data, returned_raw = _parse(raw)
    assert returned_raw == raw
    assert "Parse Error" in str(data)


def _direct_gemini(output_text: str):
    import json

    from scripts.bench.capability_ab_runner import _parse_direct_gemini_json

    return _parse_direct_gemini_json(json.dumps({"output": output_text}))


@pytest.mark.parametrize(
    "output_text",
    [
        '{"status": "APPROVED", "patch": "x"}',
        'prose {"status": "APPROVED", "patch": "x"} tail',
        '```json\n{"status": "APPROVED", "patch": "x"}\n```',
    ],
)
def test_direct_gemini_valid_forms(output_text):
    payload, returned = _direct_gemini(output_text)
    assert returned == output_text
    assert payload["status"] == "APPROVED"
    assert payload["token_capture_status"] == "missing_gateway_stats"


@pytest.mark.parametrize(
    "output_text", ["no json at all", "{broken", "[1, 2]", '"s"', "null", "{'a': 1}", "} {"]
)
def test_direct_gemini_bad_input_raises(output_text):
    # The pre-routing code raised JSONDecodeError (a ValueError) for unparseable text and
    # TypeError for valid non-object JSON (item assignment on a list/str/None).
    with pytest.raises((ValueError, TypeError)):
        _direct_gemini(output_text)


def test_reversed_braces_fail_closed_in_all_slice_parsers() -> None:
    """Text with a closing brace before the opening one (start > end) yields an empty slice."""
    raw = "} {"
    assert _parse_automem_response(raw) == []
    data, returned_raw = _parse(raw)
    assert returned_raw == raw
    assert "Parse Error" in str(data)
    # The two local_heal slice parsers were retired in #2514
    # (ARCHIVED_2026-10-17_deadcode_b2.md); assert their modules are gone.
    assert (
        importlib.util.find_spec("nexus.services.local_heal.p3_local_cheap_verifier_runtime")
        is None
    )
    assert importlib.util.find_spec("nexus.services.local_heal.p3_local_diagnosis_runtime") is None
