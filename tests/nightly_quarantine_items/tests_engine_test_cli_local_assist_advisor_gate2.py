"""Nightly quarantine entry: tests/engine/test_cli_local_assist_advisor_gate2.py (#1929). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/engine/test_cli_local_assist_advisor_gate2.py",
    "disposition": "quarantine",
    "issue": "#1929",
    "cause": (
        "archived code: nexus/engine/pipeline_repair.py is unreachable from production "
        "(ARCHIVED_2026-10-13-legacy-engine.md row 2, #2047, deletion pending). Its UnifiedRuntime "
        "requests carry no route workforce_bindings, so Workforce Admission BLOCKs "
        "('demand_online: workforce_bindings must be an object mapping') and the result has no "
        "status (KeyError); admitting the request afterwards (tests/research/conftest.py pattern) "
        "fails canonical_planning_bundle_request_binding_mismatch. A fix needs product changes in "
        "archived code; Owner decision: drop these ids with the module deletion or revive the module"
    ),
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
