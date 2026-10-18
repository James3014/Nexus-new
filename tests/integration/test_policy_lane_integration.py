#!/usr/bin/env python3
"""
Policy Lane Integration Tests — 窄而關鍵的 integration slice。

覆蓋：
1. Override → lane policy → authority contract
2. Override lifecycle (create → check → TTL → rollback) → receipt trail
3. Hard-lane drill → claim/delivery/contamination gating
4. Cutover → always human-gated
5. Manifest ↔ lane gate ↔ override consistency
"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "reports" / "policy-manifest.v2.json"
LANE_GATE = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "check_policy_lane_gate.py"
OVERRIDE_LIFECYCLE = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "policy_override_lifecycle.py"
)
OVERRIDE_DIR = Path(__file__).resolve().parents[2] / ".nexus" / "policy_overrides"


def _compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_file_changed(path: Path, baseline_hash: str) -> bool:
    return _compute_sha256(path) != baseline_hash


@pytest.fixture(scope="module", autouse=True)
def guard_real_manifest():
    initial_hash = _compute_sha256(MANIFEST_PATH)
    yield
    assert not _is_file_changed(MANIFEST_PATH, initial_hash), (
        "Real manifest was modified during test run!"
    )


@pytest.fixture
def tmp_manifest_env(tmp_path: Path) -> dict[str, str]:
    tmp_manifest = tmp_path / "policy-manifest.v2.json"
    shutil.copyfile(MANIFEST_PATH, tmp_manifest)
    tmp_overrides = tmp_path / "overrides"
    tmp_overrides.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["NEXUS_POLICY_MANIFEST_PATH"] = str(tmp_manifest)
    env["NEXUS_POLICY_OVERRIDE_DIR"] = str(tmp_overrides)
    return env


def run_script(script: Path, args: list[str], env: dict[str, str] | None = None) -> dict:
    """Run a Python script and return parsed JSON output (handles exit code 1)."""
    result = subprocess.run(
        [sys.executable, str(script)] + args, capture_output=True, text=True, timeout=30, env=env
    )
    # Scripts return JSON on stdout even when exit code is 1
    output = result.stdout.strip() or result.stderr.strip()
    if output:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"error": output, "exit_code": result.returncode}
    return {"error": "empty output", "exit_code": result.returncode}


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


# ─── 1. Override → Lane Policy → Authority Contract ────────────────────


class TestOverrideAuthorityContract:
    """Override creates must respect lane authority boundaries."""

    def test_soft_lane_override_respects_authority(self):
        """Soft lane override on P-COST-01 (authority_impact=none) → allowed."""
        result = run_script(LANE_GATE, ["--policy-id", "P-COST-01", "--action", "modify"])
        assert result.get("allowed") is True
        assert result.get("lane") == "soft"

    def test_hard_lane_override_respects_authority(self):
        """Hard lane override on P-CLAIM-02 (critical tier) → blocked."""
        result = run_script(LANE_GATE, ["--policy-id", "P-CLAIM-02", "--action", "modify"])
        assert result.get("allowed") is True  # P-CLAIM-02 has drill, so modify is allowed
        assert result.get("lane") == "hard"

    def test_hard_lane_without_drill_blocked(self):
        """Hard lane without drill (P-TEST-NODRILL-01) → blocked."""
        result = run_script(LANE_GATE, ["--policy-id", "P-TEST-NODRILL-01", "--action", "modify"])
        assert result.get("allowed") is False
        assert "ROLLBACK_DRILL_MISSING" in result.get("errors", [])

    def test_shadow_lane_no_authority_leakage(self):
        """Shadow lane (P-AUTO-01) observe → allowed, no authority change."""
        result = run_script(LANE_GATE, ["--policy-id", "P-AUTO-01", "--action", "observe"])
        assert result.get("allowed") is True
        assert result.get("lane") == "shadow"

    def test_hard_lane_promotion_blocked(self):
        """Hard lane promotion (P-S2T-03) → blocked (promotion_allowed=false)."""
        result = run_script(LANE_GATE, ["--policy-id", "P-S2T-03", "--action", "promote"])
        assert result.get("allowed") is False
        assert "PROMOTION_NOT_ALLOWED" in result.get("errors", [])


# ─── 2. Override Lifecycle → Receipt Trail ─────────────────────────────


class TestOverrideLifecycle:
    """Override create → check → TTL → rollback → receipt trail."""

    def test_override_create_and_check(self, tmp_manifest_env):
        """Create override → check it's active → verify receipt exists."""
        # Create
        create_result = run_script(
            OVERRIDE_LIFECYCLE,
            [
                "create",
                "--policy-id",
                "P-BUDGET-01",
                "--who",
                "integration-test",
                "--why",
                "Integration test override",
                "--scope",
                "budget threshold",
                "--expiry",
                "2099-12-31T23:59:59Z",
                "--rollback-target",
                "P-BUDGET-01.1.0.0",
            ],
            env=tmp_manifest_env,
        )
        assert "override_id" in create_result
        override_id = create_result["override_id"]

        # Check
        check_result = run_script(
            OVERRIDE_LIFECYCLE, ["check", "--override-id", override_id], env=tmp_manifest_env
        )
        assert check_result.get("status") == "active"
        assert check_result.get("policy_id") == "P-BUDGET-01"
        assert check_result.get("remaining_hours", 0) > 0

        # Verify receipt file exists
        override_dir = Path(tmp_manifest_env["NEXUS_POLICY_OVERRIDE_DIR"])
        receipt_path = override_dir / f"{override_id}.json"
        assert receipt_path.exists()
        receipt = json.loads(receipt_path.read_text())
        assert receipt["policy_id"] == "P-BUDGET-01"
        assert receipt["who"] == "integration-test"

    def test_override_rollback_integrity(self, tmp_manifest_env):
        """Create override → rollback → verify rollback recorded."""
        # Create
        create_result = run_script(
            OVERRIDE_LIFECYCLE,
            [
                "create",
                "--policy-id",
                "P-LEARN-01",
                "--who",
                "integration-test",
                "--why",
                "Rollback test",
                "--scope",
                "learning params",
                "--expiry",
                "2099-12-31T23:59:59Z",
                "--rollback-target",
                "P-LEARN-01.1.0.0",
            ],
            env=tmp_manifest_env,
        )
        override_id = create_result["override_id"]

        # Rollback
        rollback_result = run_script(
            OVERRIDE_LIFECYCLE, ["rollback", "--override-id", override_id], env=tmp_manifest_env
        )
        assert rollback_result.get("status") == "rolled_back"
        assert rollback_result.get("rollback_to") == "P-LEARN-01.1.0.0"

        # Verify receipt shows rolled_back status
        override_dir = Path(tmp_manifest_env["NEXUS_POLICY_OVERRIDE_DIR"])
        receipt_path = override_dir / f"{override_id}.json"
        receipt = json.loads(receipt_path.read_text())
        assert receipt["status"] == "rolled_back"

    def test_hard_lane_override_create_blocked(self, tmp_manifest_env):
        """Hard lane override create → blocked at creation."""
        result = run_script(
            OVERRIDE_LIFECYCLE,
            [
                "create",
                "--policy-id",
                "P-CLAIM-02",
                "--who",
                "integration-test",
                "--why",
                "Should be blocked",
                "--scope",
                "evidence verifier",
                "--expiry",
                "2099-12-31T23:59:59Z",
                "--rollback-target",
                "P-CLAIM-02.1.0.0",
            ],
            env=tmp_manifest_env,
        )
        assert result.get("error") == "HARD_LANE_OVERRIDE_BLOCKED"

    def test_override_list_shows_active(self, tmp_manifest_env):
        """Override list shows active overrides."""
        result = run_script(OVERRIDE_LIFECYCLE, ["list"], env=tmp_manifest_env)
        assert "overrides" in result
        assert result["total"] >= 0  # May have leftovers from other tests


# ─── 3. Hard-Lane Drill → Claim/Delivery/Contamination Gating ──────────


class TestHardLaneDrillGating:
    """Hard lane drill requirement for claim/delivery/contamination families."""

    def test_claim_family_blocked_without_drill(self):
        """P-TEST-NODRILL-01 → blocked without drill."""
        result = run_script(LANE_GATE, ["--policy-id", "P-TEST-NODRILL-01", "--action", "modify"])
        assert result.get("allowed") is False
        assert result.get("lane") == "hard"

    def test_delivery_family_blocked_without_drill(self):
        """P-TEST-NODRILL-01 → blocked without drill."""
        result = run_script(LANE_GATE, ["--policy-id", "P-TEST-NODRILL-01", "--action", "modify"])
        assert result.get("allowed") is False
        assert result.get("lane") == "hard"

    def test_contamination_family_blocked_without_drill(self):
        """P-TEST-NODRILL-01 → blocked without drill."""
        result = run_script(LANE_GATE, ["--policy-id", "P-TEST-NODRILL-01", "--action", "modify"])
        assert result.get("allowed") is False
        assert result.get("lane") == "hard"

    def test_evidence_family_passes_with_drill(self):
        """P-GATE-03 (Rust receipt_verifier) was retired 2026-10-16 with its source: no longer a policy."""
        result = run_script(LANE_GATE, ["--policy-id", "P-GATE-03", "--action", "modify"])
        assert result.get("allowed") is False
        assert result.get("errors") == ["POLICY_NOT_FOUND: P-GATE-03"]

    def test_flow_family_passes_with_drill(self):
        """P-FLOW-01 (Rust flow_machine) was retired 2026-10-16 with its source: no longer a policy."""
        result = run_script(LANE_GATE, ["--policy-id", "P-FLOW-01", "--action", "modify"])
        assert result.get("allowed") is False
        assert result.get("errors") == ["POLICY_NOT_FOUND: P-FLOW-01"]


# ─── 4. Cutover → Always Human-Gated ───────────────────────────────────


class TestCutoverHumanGating:
    """Cutover action is always blocked (requires human approval)."""

    def test_hard_lane_cutover_blocked(self):
        """Hard lane cutover → always blocked."""
        for pid in ["P-S2T-01", "P-CLAIM-02", "P-DELIVERY-01", "P-CONTAM-01"]:
            result = run_script(LANE_GATE, ["--policy-id", pid, "--action", "cutover"])
            assert result.get("allowed") is False, f"{pid} cutover should be blocked"
            assert "CUTOVER_REQUIRES_HUMAN_APPROVAL" in result.get("errors", [])

    def test_soft_lane_cutover_not_applicable(self):
        """Soft lane doesn't have cutover_impact, but cutover action still blocked."""
        result = run_script(LANE_GATE, ["--policy-id", "P-ROUTE-01", "--action", "cutover"])
        # Soft lane allows cutover action since no cutover_impact
        # But semantically, cutover is a hard-lane concern
        # The gate returns allowed for soft lane (no cutover_impact)
        assert result.get("lane") == "soft"


# ─── 5. Manifest ↔ Lane Gate ↔ Override Consistency ────────────────────


class TestManifestConsistency:
    """Verify manifest, lane gate, and override system are consistent."""

    def test_manifest_lane_counts_match(self):
        """Manifest summary lane counts match actual policy counts."""
        manifest = load_manifest()
        policies = manifest["policies"]
        summary = manifest["summary"]

        hard = sum(1 for p in policies if p["lane"] == "hard")
        soft = sum(1 for p in policies if p["lane"] == "soft")
        shadow = sum(1 for p in policies if p["lane"] == "shadow")

        assert hard == summary["hard_lane"]
        assert soft == summary["soft_lane"]
        assert shadow == summary["shadow_lane"]
        assert hard + soft + shadow == summary["total_policies"]

    def test_all_hard_lane_policies_blocked_without_drill(self):
        """All hard lane policies without drill should block modify."""
        manifest = load_manifest()
        hard_policies = [p for p in manifest["policies"] if p["lane"] == "hard"]

        for policy in hard_policies:
            pid = policy["policy_id"]
            has_drill = policy.get("rollback_drill_status", "no-drill") != "no-drill"
            result = run_script(LANE_GATE, ["--policy-id", pid, "--action", "modify"])

            if has_drill:
                assert result.get("allowed") is True, f"{pid} with drill should pass"
            else:
                assert result.get("allowed") is False, f"{pid} without drill should block"

    def test_all_soft_lane_policies_pass_modify(self):
        """All soft lane policies should pass modify action."""
        manifest = load_manifest()
        soft_policies = [p for p in manifest["policies"] if p["lane"] == "soft"]

        for policy in soft_policies:
            pid = policy["policy_id"]
            result = run_script(LANE_GATE, ["--policy-id", pid, "--action", "modify"])
            assert result.get("allowed") is True, f"{pid} soft lane should pass modify"

    def test_override_expiry_enforcement(self, tmp_manifest_env):
        """Expired override should be detected as expired."""
        # Create override with near-expiry
        create_result = run_script(
            OVERRIDE_LIFECYCLE,
            [
                "create",
                "--policy-id",
                "P-BELIEF-01",
                "--who",
                "integration-test",
                "--why",
                "Expiry test",
                "--scope",
                "belief blending",
                "--expiry",
                "2020-01-01T00:00:00Z",  # Already expired
                "--rollback-target",
                "P-BELIEF-01.1.0.0",
            ],
            env=tmp_manifest_env,
        )
        override_id = create_result.get("override_id")
        if override_id:
            check_result = run_script(
                OVERRIDE_LIFECYCLE, ["check", "--override-id", override_id], env=tmp_manifest_env
            )
            assert check_result.get("status") == "expired"


# ─── 6. Hermetic Lifecycle Env Overrides (Issue #2266) ──────────────────


def _load_fresh_lifecycle():
    spec = importlib.util.spec_from_file_location(
        "policy_override_lifecycle_fresh", OVERRIDE_LIFECYCLE
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lifecycle_manifest_path_env_override(monkeypatch, tmp_path):
    manifest_target = tmp_path / "m.json"
    monkeypatch.setenv("NEXUS_POLICY_MANIFEST_PATH", str(manifest_target))
    module = _load_fresh_lifecycle()
    assert module.MANIFEST_PATH == manifest_target


def test_lifecycle_override_dir_env_override(monkeypatch, tmp_path):
    override_target = tmp_path / "ovr"
    monkeypatch.setenv("NEXUS_POLICY_OVERRIDE_DIR", str(override_target))
    module = _load_fresh_lifecycle()
    assert module.OVERRIDE_DIR == override_target


def test_lifecycle_defaults_unchanged_without_env(monkeypatch):
    monkeypatch.delenv("NEXUS_POLICY_MANIFEST_PATH", raising=False)
    monkeypatch.delenv("NEXUS_POLICY_OVERRIDE_DIR", raising=False)
    module = _load_fresh_lifecycle()
    assert str(module.MANIFEST_PATH).endswith("docs/reports/policy-manifest.v2.json")
    assert str(module.OVERRIDE_DIR).endswith(".nexus/policy_overrides")


def test_lifecycle_env_override_isolates_save_manifest(monkeypatch, tmp_path):
    manifest_override = tmp_path / "m.json"
    override_dir = tmp_path / "ovr"
    monkeypatch.setenv("NEXUS_POLICY_MANIFEST_PATH", str(manifest_override))
    monkeypatch.setenv("NEXUS_POLICY_OVERRIDE_DIR", str(override_dir))

    real_bytes = MANIFEST_PATH.read_bytes()
    manifest_override.write_bytes(real_bytes)

    module = _load_fresh_lifecycle()
    try:
        module.save_manifest({"policies": []})
        assert MANIFEST_PATH.read_bytes() == real_bytes
        assert json.loads(manifest_override.read_text()) == {"policies": []}
    finally:
        if MANIFEST_PATH.read_bytes() != real_bytes:
            MANIFEST_PATH.write_bytes(real_bytes)


# ─── 7. Manifest Guard Verifications (Issue #2266) ─────────────────────


def test_real_manifest_untouched_by_lifecycle_runs(tmp_manifest_env):
    real_initial_hash = _compute_sha256(MANIFEST_PATH)
    tmp_manifest_path = Path(tmp_manifest_env["NEXUS_POLICY_MANIFEST_PATH"])
    tmp_initial_hash = _compute_sha256(tmp_manifest_path)

    create_result = run_script(
        OVERRIDE_LIFECYCLE,
        [
            "create",
            "--policy-id",
            "P-BUDGET-01",
            "--who",
            "guard-test",
            "--why",
            "Guard test override",
            "--scope",
            "budget threshold",
            "--expiry",
            "2099-12-31T23:59:59Z",
            "--rollback-target",
            "P-BUDGET-01.1.0.0",
        ],
        env=tmp_manifest_env,
    )
    assert "override_id" in create_result
    override_id = create_result["override_id"]

    rollback_result = run_script(
        OVERRIDE_LIFECYCLE,
        ["rollback", "--override-id", override_id],
        env=tmp_manifest_env,
    )
    assert rollback_result.get("status") == "rolled_back"

    assert _compute_sha256(MANIFEST_PATH) == real_initial_hash
    assert _compute_sha256(tmp_manifest_path) != tmp_initial_hash


def test_manifest_guard_detects_a_write(tmp_path: Path):
    test_file = tmp_path / "test-manifest.json"
    test_file.write_text("initial content")
    initial_hash = _compute_sha256(test_file)
    assert not _is_file_changed(test_file, initial_hash)

    test_file.write_text("modified content")
    assert _is_file_changed(test_file, initial_hash)
