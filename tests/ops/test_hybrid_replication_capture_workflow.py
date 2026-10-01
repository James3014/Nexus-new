from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/hybrid-replication-capture.yml")


def test_hybrid_replication_capture_workflow_is_event_driven_and_fail_closed() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "issues:" in text
    assert "types: [opened, edited]" in text
    assert "NEXUS_HYBRID_REPLICATION_CAPTURE_V1" not in text
    assert 'EVENT_PATH: ${{ github.event_path }}' not in text
    assert 'os.environ["GITHUB_EVENT_PATH"]' in text
    assert "NEXUS-HYBRID-REPLICATION-CAPTURE-V1" in text
    assert "NEXUS-HYBRID-REPLICATION-ADMISSION-V1" in text
    assert "NEXUS-HYBRID-REPLICATION-CONTRACT-DELTA-V1" in text
    assert "NEXUS-HYBRID-REPLICATION-INTAKE-GAP-V1" in text
    assert "NEXUS_HYBRID_REPLICATION_ACTIVATION_STATE" in text
    assert "NEXUS_HYBRID_REPLICATION_T_AUTO" in text
    assert "NEXUS_HYBRID_REPLICATION_EXCLUSION_SET_SHA256" in text
    assert 'activation_state != "AUTOMATIC_CAPTURE_READY"' in text
    assert "activation exclusion-set hash mismatch; admission blocked" in text
    assert "implementation_pr_numbers" in text
    assert "INTAKE_PROTOCOL_LOSS_IMPLEMENTATION_PRESENT" in text
    assert "INTAKE_PROTOCOL_LOSS_TERMINAL_BEFORE_ADMISSION" in text
    assert "EXCLUDE_PARENT_TASK_PRE_BOUNDARY" in text
    assert "opening_capture_missing_or_ambiguous_before_edit" in text


def test_capture_workflow_has_no_routing_or_merge_authority() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "RESEARCH_OBSERVATION_ONLY / NO_ENGINEERING_AUTHORITY" in text
    assert "pull-requests: write" not in text
    assert "contents: write" not in text
    assert "actions: write" not in text
    assert "issues: write" in text
