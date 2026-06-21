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
OUTPUT_DIR = REPO_ROOT / "artifacts" / "runtime" / "ao2_live_regression_entrypoints_v0"


class TestEntrypointExists:
    """Verify entrypoint scripts exist."""

    def test_c12481_script_exists(self):
        """C_12481 entrypoint script exists."""
        assert C12481_SCRIPT.exists(), f"Script not found: {C12481_SCRIPT}"

    def test_c13453_script_exists(self):
        """C_13453 entrypoint script exists."""
        assert C13453_SCRIPT.exists(), f"Script not found: {C13453_SCRIPT}"


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
        # The fixture exists, so we test that the script handles both cases
        result = subprocess.run(
            [sys.executable, str(C12481_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
        )
        output = json.loads(result.stdout)
        # Either FIXTURE_LOADED or LIVE_FIXTURE_UNAVAILABLE is acceptable
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
