"""Tests for abort receipt guarantee."""
from __future__ import annotations

import json

from nexus.evidence.abort_receipt import (
    AbortReceipt,
    write_abort_receipt,
    load_abort_receipt,
    validate_failure_subclass,
    WORKSPACE_FAILURE_SUBCLASSES,
)


def test_abort_receipt_has_all_required_fields(tmp_path):
    """Abort receipt contains all required fields per spec."""
    receipt = AbortReceipt(
        task_id="T-001",
        instance_id="astropy__astropy-14096",
        failure_class="workspace_provisioning",
        failure_reason="repo not found",
        failure_subclass="REPO_NOT_MOUNTED",
        workspace_path="/workspaces/astropy",
        repo_root="/workspaces/astropy/astropy",
        target_path="/workspaces/astropy/astropy/astropy/time",
        path_subclass="target_path",
        model_calls=0,
        stop_layer="workspace_provision",
        started_at="2026-06-17T10:00:00Z",
        finished_at="2026-06-17T10:00:01Z",
    )

    d = receipt.to_dict()
    assert d["schema"] == "nexus.evidence.abort_receipt.v1"
    assert d["receipt_present"] is True
    assert d["solved"] is False
    assert d["claim_eligible"] is False
    assert d["simulated"] is False
    assert d["failure_class"] == "workspace_provisioning"
    assert d["failure_subclass"] == "REPO_NOT_MOUNTED"
    assert d["model_calls"] == 0


def test_write_abort_receipt_creates_file(tmp_path):
    """write_abort_receipt creates a JSON file on disk."""
    receipt_path = write_abort_receipt(
        output_dir=tmp_path / "receipts",
        task_id="T-002",
        instance_id="astropy__astropy-14096",
        failure_class="workspace_provisioning",
        failure_reason="target path unresolved",
        failure_subclass="TARGET_PATH_UNRESOLVED",
    )

    assert receipt_path.exists()
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert data["task_id"] == "T-002"
    assert data["receipt_present"] is True


def test_load_abort_receipt_returns_empty_if_missing(tmp_path):
    """load_abort_receipt returns empty dict if file doesn't exist."""
    result = load_abort_receipt(tmp_path / "nonexistent.json")
    assert result == {}


def test_all_workspace_failure_subclasses_are_valid():
    """All workspace failure subclasses in spec are recognized."""
    for subclass in WORKSPACE_FAILURE_SUBCLASSES:
        assert validate_failure_subclass(subclass)


def test_workspace_failure_not_counted_as_patcher_failure(tmp_path):
    """Workspace failure abort receipt has failure_class=workspace_provisioning."""
    receipt_path = write_abort_receipt(
        output_dir=tmp_path / "receipts",
        task_id="T-003",
        instance_id="django__django-11099",
        failure_class="workspace_provisioning",
        failure_subclass="REPO_NOT_WRITABLE",
    )
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert data["failure_class"] == "workspace_provisioning"
    assert data["failure_subclass"] == "REPO_NOT_WRITABLE"
    assert data["claim_eligible"] is False
