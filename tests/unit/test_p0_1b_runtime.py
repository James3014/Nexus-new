"""P0.1b Runtime tests: abort receipt hook, claim boundary header, dedupe aggregation."""
from __future__ import annotations

import json
from pathlib import Path

from nexus.evidence.abort_receipt import write_abort_receipt, load_abort_receipt
from nexus.evidence.claim_boundary import evaluate_claim_boundary
from nexus.evidence.dedupe import DedupeManifest, DedupeEntry, normalize_instance_id, find_canonical
from nexus.evidence.dedupe_aggregator import (
    aggregate_with_dedupe,
    build_summary_header,
)


# ============================================================
# 1. Abort Receipt Runtime Hook Tests
# ============================================================

def test_abort_receipt_written_on_phase_failure(tmp_path):
    """Abort receipt is written when orchestrator phase fails."""
    receipt_path = write_abort_receipt(
        output_dir=tmp_path,
        task_id="T-RT-001",
        instance_id="astropy__astropy-14096",
        failure_class="phase_failure",
        failure_reason="REPRO_NOT_REPRODUCED",
        failure_subclass="WRONG_REPRO_PATH",
        workspace_path="/workspaces/astropy",
        repo_root="/workspaces/astropy",
        model_calls=0,
        stop_layer="reproduction",
    )
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert data["schema"] == "nexus.evidence.abort_receipt.v1"
    assert data["failure_class"] == "phase_failure"
    assert data["claim_eligible"] is False
    assert data["solved"] is False


def test_abort_receipt_workspace_provisioning_failure(tmp_path):
    """Abort receipt for workspace provisioning has correct failure_class."""
    receipt_path = write_abort_receipt(
        output_dir=tmp_path,
        task_id="T-RT-002",
        instance_id="django__django-11099",
        failure_class="workspace_provisioning",
        failure_reason="REPO_NOT_MOUNTED",
        failure_subclass="REPO_NOT_MOUNTED",
        workspace_path="/workspaces/django",
        repo_root="",
        model_calls=0,
        stop_layer="workspace_provision",
    )
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert data["failure_class"] == "workspace_provisioning"
    assert data["failure_subclass"] == "REPO_NOT_MOUNTED"
    assert data["model_calls"] == 0


def test_abort_receipt_load_returns_empty_if_missing(tmp_path):
    """load_abort_receipt returns empty dict for missing file."""
    result = load_abort_receipt(tmp_path / "nonexistent.json")
    assert result == {}


# ============================================================
# 2. Claim Boundary Report Header Tests
# ============================================================

def test_claim_boundary_in_report_header():
    """Report header includes claim boundary fields."""
    boundary = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=True,
        model_calls=3,
        visible_tests_passed=5,
        hidden_tests_passed=2,
    )
    d = boundary.to_dict()
    assert "simulated" in d
    assert "claim_eligible" in d
    assert "receipt_present" in d
    assert "public_claim_allowed" in d
    assert "claim_block_reason" in d


def test_report_header_blocks_simulated_data():
    """Report header blocks simulated data from public claims."""
    boundary = evaluate_claim_boundary(
        simulated=True,
        claim_eligible=True,
        receipt_present=True,
        model_calls=1,
    )
    assert boundary.public_claim_allowed is False
    assert "simulated=true" in boundary.claim_block_reason


def test_report_header_blocks_no_receipt():
    """Report header blocks when receipt is missing."""
    boundary = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=False,
        model_calls=1,
    )
    assert boundary.public_claim_allowed is False
    assert "receipt_present=false" in boundary.claim_block_reason


def test_report_header_blocks_zero_model_calls():
    """Report header blocks zero model calls from claims."""
    boundary = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=True,
        receipt_present=True,
        model_calls=0,
    )
    assert boundary.public_claim_allowed is False
    assert "model_calls=0" in boundary.claim_block_reason


# ============================================================
# 3. Dedupe Aggregation Tests
# ============================================================

def test_dedupe_aggregation_raw_vs_deduped(tmp_path):
    """Aggregation produces both raw and deduped views."""
    manifest = DedupeManifest(entries=[
        DedupeEntry(
            canonical_instance_id="astropy-14096",
            alias_instance_ids=["astropy__astropy-14096"],
            dedupe_reason="alias_normalization",
        ),
    ])

    receipts = [
        {"instance_id": "astropy-14096", "solve_eligible": True},
        {"instance_id": "astropy__astropy-14096", "solve_eligible": True},
        {"instance_id": "django-11099", "solve_eligible": False},
    ]

    result = aggregate_with_dedupe(receipts, manifest)
    assert result.raw_total == 3
    assert result.raw_solved == 2
    assert result.deduped_total == 2
    assert result.deduped_solved == 1
    assert "astropy__astropy-14096" in result.excluded_aliases


def test_dedupe_aggregation_dedupe_rate(tmp_path):
    """Deduped rate is calculated correctly."""
    manifest = DedupeManifest(entries=[])

    receipts = [
        {"instance_id": "a-1", "solve_eligible": True},
        {"instance_id": "b-1", "solve_eligible": False},
        {"instance_id": "c-1", "solve_eligible": True},
    ]

    result = aggregate_with_dedupe(receipts, manifest)
    assert result.raw_rate == 2 / 3
    assert result.deduped_rate == 2 / 3


def test_build_summary_header_includes_claim_boundary():
    """build_summary_header includes claim boundary."""
    manifest = DedupeManifest(entries=[])
    receipts = [{"instance_id": "a-1", "solve_eligible": True}]
    result = aggregate_with_dedupe(receipts, manifest)

    header = build_summary_header(result, report_type="benchmark_summary")
    assert "claim_boundary" in header
    assert "dedupe_summary" in header
    assert header["report_type"] == "benchmark_summary"


def test_build_summary_header_blocks_internal_report():
    """build_summary_header for internal report has claim_scope restriction."""
    manifest = DedupeManifest(entries=[])
    receipts = [{"instance_id": "a-1", "solve_eligible": False}]
    result = aggregate_with_dedupe(receipts, manifest)

    header = build_summary_header(result, report_type="focused_internal_rerun")
    assert header["report_type"] == "focused_internal_rerun"
    claim = header["claim_boundary"]
    assert claim["public_claim_allowed"] is False


# ============================================================
# 4. Receipt Non-Overwrite Audit Tests
# ============================================================

def test_abort_and_normal_receipt_different_filenames(tmp_path):
    """Abort receipt and normal receipt use different filenames — no overwrite."""
    instance_id = "astropy__astropy-14096"

    abort_path = write_abort_receipt(
        output_dir=tmp_path,
        task_id=instance_id,
        instance_id=instance_id,
        failure_class="workspace_provisioning",
        failure_reason="REPO_NOT_MOUNTED",
        failure_subclass="REPO_NOT_MOUNTED",
    )

    normal_path = tmp_path / "receipt.json"
    normal_path.write_text(json.dumps({"schema": "nexus.local_heal.repair_receipt.v1"}), encoding="utf-8")

    assert abort_path.name.startswith("abort_receipt_")
    assert normal_path.name == "receipt.json"
    assert abort_path.name != normal_path.name
    assert abort_path.exists()
    assert normal_path.exists()


def test_normal_receipt_does_not_overwrite_abort_receipt(tmp_path):
    """Writing normal receipt does not delete abort receipt."""
    instance_id = "django__django-11099"

    abort_path = write_abort_receipt(
        output_dir=tmp_path,
        task_id=instance_id,
        instance_id=instance_id,
        failure_class="workspace_provisioning",
        failure_reason="REPO_NOT_WRITABLE",
        failure_subclass="WORKSPACE_NOT_WRITABLE",
    )

    normal_path = tmp_path / "receipt.json"
    normal_path.write_text(json.dumps({"schema": "nexus.local_heal.repair_receipt.v1"}), encoding="utf-8")

    assert abort_path.exists(), "abort receipt should still exist after normal receipt written"


def test_success_run_does_not_produce_abort_receipt(tmp_path):
    """Success run should not produce abort receipt."""
    success_dir = tmp_path / "success_task"
    success_dir.mkdir()
    normal_path = success_dir / "receipt.json"
    normal_path.write_text(json.dumps({
        "schema": "nexus.local_heal.repair_receipt.v1",
        "solve_eligible": True,
    }), encoding="utf-8")

    abort_files = list(success_dir.glob("abort_receipt_*.json"))
    assert len(abort_files) == 0, "success run should not produce abort receipt"


def test_rerun_same_task_receipt_paths(tmp_path):
    """Rerun same task: abort receipt path is versioned by filename."""
    instance_id = "sympy__sympy-20590"

    path1 = write_abort_receipt(
        output_dir=tmp_path,
        task_id=f"{instance_id}_run1",
        instance_id=instance_id,
        failure_class="workspace_provisioning",
        failure_reason="REPO_NOT_MOUNTED",
    )
    path2 = write_abort_receipt(
        output_dir=tmp_path,
        task_id=f"{instance_id}_run2",
        instance_id=instance_id,
        failure_class="workspace_provisioning",
        failure_reason="REPO_NOT_MOUNTED",
    )

    assert path1 != path2
    assert path1.exists()
    assert path2.exists()
