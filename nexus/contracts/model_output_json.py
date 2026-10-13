"""Sanctioned parser for JSON emitted by a model (#1923).

Every ``json.loads`` on raw model text belongs here, not at the call site;
tests/integration/test_legacy_path_blocked.py enforces this. The module lives
in ``nexus.contracts`` so ``nexus.core``, ``nexus.services`` and ``nexus.engine``
may all import it (tests/test_layer_boundaries.py forbids core -> engine);
``SemanticAdapter.parse_json_object`` re-exports it for engine callers.

Callers state the top-level shape they expect and how forgiving to be:

- ``"strict"``: standard JSON only.
- ``"pydict"``: also the Python-dict dialect small local models emit
  (single quotes, None/True/False), mapped onto standard JSON.
- ``"lenient"``: additionally falls back to ``ast.literal_eval``.

Anything that does not parse, or parses to the wrong shape, raises a
``ModelOutputParseError`` (a ``ValueError``): callers treat it as "no decision".
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Literal

ParseMode = Literal["strict", "pydict", "lenient"]
ExpectedShape = Literal["object", "array"]

_SHAPES: dict[str, type] = {"object": dict, "array": list}


class ModelOutputParseError(ValueError):
    """Raw model output could not be parsed as JSON (fail-closed)."""


class ModelOutputShapeError(ModelOutputParseError):
    """Raw model output parsed, but not to the top-level shape the caller expects."""


def _pydict_to_json(raw_output: str) -> str:
    cleaned = raw_output.replace("'", '"')
    cleaned = re.sub(r"\bNone\b", "null", cleaned)
    cleaned = re.sub(r"\bTrue\b", "true", cleaned)
    return re.sub(r"\bFalse\b", "false", cleaned)


def _json_to_pyliteral(raw_output: str) -> str:
    py_str = re.sub(r"\bnull\b", "None", raw_output)
    py_str = re.sub(r"\btrue\b", "True", py_str)
    return re.sub(r"\bfalse\b", "False", py_str)


def parse_model_json(raw_output: str, *, expect: ExpectedShape, mode: ParseMode = "lenient") -> Any:
    """Parse model text into a JSON value of the expected top-level shape, or raise."""
    if expect not in _SHAPES:
        raise ValueError(f"unknown expected shape: {expect!r}")
    if mode not in {"strict", "pydict", "lenient"}:
        raise ValueError(f"unknown parse mode: {mode!r}")
    if not isinstance(raw_output, str):
        raise ModelOutputParseError(f"model output must be str, got {type(raw_output).__name__}")

    attempts: list[Any] = [lambda: json.loads(raw_output)]
    if mode in {"pydict", "lenient"}:
        attempts.append(lambda: json.loads(_pydict_to_json(raw_output)))
    if mode == "lenient":
        attempts.append(lambda: ast.literal_eval(_json_to_pyliteral(raw_output)))

    last_exc: Exception | None = None
    for attempt in attempts:
        try:
            parsed = attempt()
        except Exception as exc:
            last_exc = exc
            continue
        if not isinstance(parsed, _SHAPES[expect]):
            raise ModelOutputShapeError(
                f"model output is a {type(parsed).__name__}, not a JSON {expect}"
            )
        return parsed
    raise ModelOutputParseError(f"Failed to parse response: {last_exc}") from last_exc


def parse_model_json_object(raw_output: str, *, mode: ParseMode = "lenient") -> dict[str, Any]:
    """Parse model text that must be one JSON object."""
    return parse_model_json(raw_output, expect="object", mode=mode)


def parse_model_json_array(raw_output: str, *, mode: ParseMode = "strict") -> list[Any]:
    """Parse model text that must be one JSON array."""
    return parse_model_json(raw_output, expect="array", mode=mode)
