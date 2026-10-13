"""Nightly quarantine entry: tests/engine/test_cli_local_assist_advisor_gate2.py (#1929). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/engine/test_cli_local_assist_advisor_gate2.py",
    "disposition": "quarantine",
    "issue": "#1929",
    "cause": "fixture Gateway/Online callables are classified physical by the unified runtime, so Workforce Admission (ALLOW) is now mandatory and the fixtures are BLOCKed; needs governed admission fixtures or an owner decision on non-physical fixture transports",
    "tests": (
        "test_advisor_degrades_when_local_provider_fails",
        "test_advisor_empty_local_outputs_does_not_force_forward",
        "test_advisor_success_forwards_local_diagnosis_to_online",
        "test_disabled_mode_does_not_invoke_local",
        "test_execute_single_repair_nonsurgical_advisor_path",
        "test_execute_single_repair_surgical_advisor_path",
        "test_repair_paths_enforce_task_deny_before_gateway_cli[disabled_direct]",
    ),
}
