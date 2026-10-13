"""Nightly quarantine entry: tests/pilot_cli/test_gateway_integration.py (#1929). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/pilot_cli/test_gateway_integration.py",
    "disposition": "quarantine",
    "issue": "#1929",
    "cause": "behavior removed: coerce_long_gemini_answer was simplified to return raw_text (no second-pass); delete or keep per owner decision",
    "tests": ("test_coerce_long_gemini_answer_uses_second_pass_for_non_json",),
}
