#!/usr/bin/env python3
"""Validate the only trusted-workflow maintenance class: Nexus Core pin-only updates."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "nexus.core.trusted_pin_policy.v1"
PIN_FIELD = "NEXUS_CORE_TOOL_PIN"
PIN_RE = re.compile(
    rb"(?m)^(?P<prefix>[ \t]*NEXUS_CORE_TOOL_PIN:[ \t]*)(?P<pin>[0-9a-f]{40})(?P<suffix>[ \t]*)$"
)


class PinPolicyError(ValueError):
    pass


def _pin_and_normalized(document: bytes) -> tuple[str, bytes]:
    matches = list(PIN_RE.finditer(document))
    if len(matches) != 1:
        raise PinPolicyError(f"NEXUS_CORE_PIN_FIELD_COUNT_INVALID:{len(matches)}")
    match = matches[0]
    pin = match.group("pin").decode("ascii")
    normalized = (
        document[: match.start("pin")]
        + b"__NEXUS_CORE_TOOL_PIN__"
        + document[match.end("pin") :]
    )
    return pin, normalized


def validate_pin_update(base_document: bytes, candidate_document: bytes) -> dict[str, Any]:
    base_pin, normalized_base = _pin_and_normalized(base_document)
    candidate_pin, normalized_candidate = _pin_and_normalized(candidate_document)

    if normalized_candidate != normalized_base:
        raise PinPolicyError("NEXUS_CORE_WORKFLOW_CHANGE_NOT_PIN_ONLY")

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "PASS",
        "change_kind": "UNCHANGED" if base_document == candidate_document else "PIN_ONLY",
        "base_pin": base_pin,
        "candidate_pin": candidate_pin,
    }
    if result["change_kind"] == "UNCHANGED" and base_pin != candidate_pin:
        raise PinPolicyError("NEXUS_CORE_PIN_POLICY_INTERNAL_MISMATCH")
    if result["change_kind"] == "PIN_ONLY" and base_pin == candidate_pin:
        raise PinPolicyError("NEXUS_CORE_WORKFLOW_CHANGE_NOT_PIN_ONLY")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-workflow", required=True)
    parser.add_argument("--candidate-workflow", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        result = validate_pin_update(
            Path(args.base_workflow).read_bytes(),
            Path(args.candidate_workflow).read_bytes(),
        )
    except (OSError, PinPolicyError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "BLOCK", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(1) from exc

    Path(args.output).write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
