from pathlib import Path

from nexus.engine.completion_contract import build_completion_envelope
from nexus.engine.completion_contract import ensure_verified_completion


def test_build_completion_envelope_marks_verified_when_runtime_passes():
    payload = build_completion_envelope(
        command_name="run",
        task_name="fix queue race",
        runtime_ok=True,
        execution_path="cli->command_service->engine",
        artifact_paths=["/tmp/report.json"],
    )

    assert payload["status"] == "SUCCESS"
    assert payload["semantic_status"] == "VERIFIED"
    assert payload["runtime_classification"] == "verified_pass"
    assert payload["retryable"] is False
    assert payload["blocker_type"] == "none"


def test_build_completion_envelope_marks_retryable_runtime_failure():
    payload = build_completion_envelope(
        command_name="run",
        task_name="fix queue race",
        runtime_ok=False,
        execution_path="cli->command_service->engine",
    )

    assert payload["status"] == "FAILED"
    assert payload["semantic_status"] == "UNVERIFIED"
    assert payload["retryable"] is True
    assert payload["next_action"] == "retry_repair"
    assert payload["semantic_failures"] == ["runtime_execution_failed"]


def test_ensure_verified_completion_raises_for_unverified():
    payload = build_completion_envelope(
        command_name="run",
        task_name="broken task",
        runtime_ok=False,
        execution_path="cli->command_service->engine",
    )

    try:
        ensure_verified_completion(payload, context="run")
    except RuntimeError as exc:
        assert "semantic completion failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_build_completion_envelope_supports_blocked_governance_state():
    payload = build_completion_envelope(
        command_name="research:run",
        task_name="governance blocked task",
        runtime_ok=False,
        execution_path="cli->research_control_plane",
        semantic_failures=["low_disk_space"],
        semantic_status="BLOCKED",
        blocker_type="governance",
        retryable=False,
        next_action="stop",
    )

    assert payload["semantic_status"] == "BLOCKED"
    assert payload["runtime_classification"] == "governance_state_block"
    assert payload["retryable"] is False
    assert payload["blocker_type"] == "governance"
    assert payload["next_action"] == "stop"
