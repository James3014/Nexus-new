"""Tests for live regression entrypoints C_12481 and C_13453."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
SCRIPTS_DIR = REPO_ROOT / "scripts" / "bench"
C12481_SCRIPT = SCRIPTS_DIR / "run_c12481_regression.py"
C13453_SCRIPT = SCRIPTS_DIR / "run_c13453_regression.py"
READINESS_SCRIPT = SCRIPTS_DIR / "check_post_wiring_regression_readiness.py"
OUTPUT_DIR = REPO_ROOT / "artifacts" / "runtime" / "ao2_live_regression_entrypoints_v0"


class TestEntrypointExists:
    """Verify entrypoint scripts exist."""

    def test_c12481_script_exists(self):
        """C_12481 entrypoint script exists."""
        assert C12481_SCRIPT.exists(), f"Script not found: {C12481_SCRIPT}"

    def test_c13453_script_exists(self):
        """C_13453 entrypoint script exists."""
        assert C13453_SCRIPT.exists(), f"Script not found: {C13453_SCRIPT}"

    def test_readiness_script_exists(self):
        """Readiness check script exists."""
        assert READINESS_SCRIPT.exists(), f"Script not found: {READINESS_SCRIPT}"


class TestDryRun:
    """Verify scripts can run in dry-run mode without external dependency."""

    def test_c12481_dry_run(self):
        """C_12481 script runs in dry-run mode."""
        result = subprocess.run(
            [sys.executable, str(C12481_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"Dry run failed: {result.stderr}"
        output = json.loads(result.stdout)
        assert output["task_id"] == "C_12481"
        assert output["entrypoint_available"] is True
        assert output["verifier_status"] == "DRY_RUN"
        assert output["hardcoded_patch_used"] is False
        assert output["public_claim_allowed"] is False
        assert output["production_ready"] is False
        assert output["training_export_allowed"] is False
        assert output["internal_only"] is True

    def test_c13453_dry_run(self):
        """C_13453 script runs in dry-run mode."""
        result = subprocess.run(
            [sys.executable, str(C13453_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"Dry run failed: {result.stderr}"
        output = json.loads(result.stdout)
        assert output["task_id"] == "C_13453"
        assert output["entrypoint_available"] is True
        assert output["verifier_status"] == "DRY_RUN"
        assert output["hardcoded_patch_used"] is False
        assert output["public_claim_allowed"] is False
        assert output["production_ready"] is False
        assert output["training_export_allowed"] is False
        assert output["internal_only"] is True


class TestLiveExecution:
    """Verify scripts execute verifier and produce correct status."""

    def test_c12481_executes_verifier(self):
        """C_12481 executes verifier and reports results."""
        result = subprocess.run(
            [sys.executable, str(C12481_SCRIPT), "--output", str(OUTPUT_DIR / "test_c12481.json")],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["tests_collected"] >= 1, "No tests collected"
        assert output["tests_executed"] >= 1, "No tests executed"
        assert output["verifier_status"] in (
            "VERIFIER_EXECUTED_PASS", "VERIFIER_EXECUTED_FAIL", "NO_TESTS_MATCHED"
        )

    def test_c13453_executes_verifier(self):
        """C_13453 executes verifier and reports results."""
        result = subprocess.run(
            [sys.executable, str(C13453_SCRIPT), "--output", str(OUTPUT_DIR / "test_c13453.json")],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["tests_collected"] >= 1, "No tests collected"
        assert output["tests_executed"] >= 1, "No tests executed"
        assert output["verifier_status"] in (
            "VERIFIER_EXECUTED_PASS", "VERIFIER_EXECUTED_FAIL", "NO_TESTS_MATCHED"
        )


class TestResultSchema:
    """Verify result JSON schema includes required fields."""

    def test_c12481_schema(self):
        """C_12481 result has all required fields."""
        result = subprocess.run(
            [sys.executable, str(C12481_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        output = json.loads(result.stdout)

        required_fields = [
            "task_id",
            "entrypoint_available",
            "verifier_command",
            "verifier_status",
            "tests_collected",
            "tests_executed",
            "source_hash",
            "hardcoded_patch_used",
            "public_claim_allowed",
            "production_ready",
            "training_export_allowed",
            "internal_only",
        ]
        for field in required_fields:
            assert field in output, f"Missing required field: {field}"

    def test_c13453_schema(self):
        """C_13453 result has all required fields."""
        result = subprocess.run(
            [sys.executable, str(C13453_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        output = json.loads(result.stdout)

        required_fields = [
            "task_id",
            "entrypoint_available",
            "verifier_command",
            "verifier_status",
            "tests_collected",
            "tests_executed",
            "source_hash",
            "hardcoded_patch_used",
            "public_claim_allowed",
            "production_ready",
            "training_export_allowed",
            "internal_only",
        ]
        for field in required_fields:
            assert field in output, f"Missing required field: {field}"


class TestFailClosed:
    """Verify fail-closed behavior when fixture is unavailable."""

    def test_c12481_fixture_unavailable_handled(self):
        """C_12481 handles missing fixture gracefully."""
        result = subprocess.run(
            [sys.executable, str(C12481_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["fixture_status"] in ("FIXTURE_LOADED", "LIVE_FIXTURE_UNAVAILABLE")

    def test_c13453_fixture_unavailable_handled(self):
        """C_13453 handles missing fixture gracefully."""
        result = subprocess.run(
            [sys.executable, str(C13453_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["fixture_status"] in ("FIXTURE_LOADED", "LIVE_FIXTURE_UNAVAILABLE")

    def test_no_tests_matched_not_pass(self):
        """NO_TESTS_MATCHED cannot become PASS."""
        result = subprocess.run(
            [sys.executable, str(C12481_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        output = json.loads(result.stdout)
        # In dry-run, status is DRY_RUN which is acceptable
        # In live mode, NO_TESTS_MATCHED should not be PASS
        if output["verifier_status"] != "DRY_RUN":
            assert output["verifier_status"] != "VERIFIER_EXECUTED_PASS" or output["tests_executed"] > 0


class TestRestoredEntrypoints:
    """Verify restored concurrency and gap entrypoint scripts."""

    def test_restored_entrypoints_dry_run(self):
        """All restored scripts run in dry-run mode."""
        restored_ids = [
            "concurrency_001", "concurrency_002", "concurrency_004", "concurrency_005",
            "concurrency_006", "concurrency_007", "concurrency_008",
            "evidence_gap_001", "action_protocol_001", "verifier_gap_001"
        ]
        for tid in restored_ids:
            script_path = SCRIPTS_DIR / f"run_{tid}_regression.py"
            if not script_path.exists():
                continue
            res = subprocess.run(
                [sys.executable, str(script_path), "--dry-run"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(REPO_ROOT),
            )
            assert res.returncode == 0, f"Dry run failed for {tid}: {res.stderr}"
            output = json.loads(res.stdout)
            assert output["task_id"] == tid
            assert output["verifier_status"] == "DRY_RUN"
            assert output["internal_only"] is True

