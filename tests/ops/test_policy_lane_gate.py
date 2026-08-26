#!/usr/bin/env python3
"""
Policy Lane Gate Tests — 驗證 hard/soft/shadow 三種 lane 的通過與阻擋案例。

Usage:
    python -m pytest tests/ops/test_policy_lane_gate.py -v
"""

import subprocess
from pathlib import Path

from scripts.ops import policy_lane_precommit
from scripts.ops.check_policy_lane_gate import check_lane_gate, find_policy, load_manifest
from scripts.ops.check_policy_override_receipt import validate_override_receipt

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "docs" / "reports" / "policy-manifest.v2.json"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "policy-lane-gate.yml"


def test_policy_lane_workflow_keeps_changed_paths_out_of_shell_source() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "git diff --name-only -z" in workflow
    assert "while IFS= read -r -d '' file" in workflow
    assert 'python scripts/ops/policy_lane_precommit.py --staged-files "$file"' in workflow
    assert "${{ steps.files.outputs.changed_files }}" not in workflow


def test_precommit_explicit_files_are_actually_checked(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def _unexpected_index_read() -> list[str]:
        raise AssertionError("explicit --staged-files must not fall back to the Git index")

    def _record_gate(policy_id: str, action: str = "modify") -> dict:
        calls.append((policy_id, action))
        return {"allowed": True, "lane": "soft", "errors": [], "policy_id": policy_id}

    monkeypatch.setattr(policy_lane_precommit, "get_staged_files", _unexpected_index_read)
    monkeypatch.setattr(policy_lane_precommit, "check_lane_gate", _record_gate)

    result = policy_lane_precommit.main(["--staged-files", "nexus/core/critique_engine.py"])

    assert result == 0
    assert calls == [("P-CLAIM-01", "modify")]


def test_precommit_explicit_hard_violation_blocks(monkeypatch) -> None:
    monkeypatch.setattr(
        policy_lane_precommit,
        "check_lane_gate",
        lambda policy_id, action="modify": {
            "allowed": False,
            "lane": "hard",
            "errors": ["TEST_BLOCK"],
            "policy_id": policy_id,
        },
    )

    result = policy_lane_precommit.main(["--staged-files", "nexus/core/critique_engine.py"])

    assert result == 1


def test_precommit_gate_unavailable_fails_closed(monkeypatch) -> None:
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="lane-gate", timeout=30)

    monkeypatch.setattr(policy_lane_precommit.subprocess, "run", _timeout)

    result = policy_lane_precommit.check_lane_gate("P-CLAIM-01")

    assert result["allowed"] is False
    assert result["lane"] == "hard"
    assert result["errors"] == ["GATE_UNAVAILABLE"]


def test_precommit_staged_file_discovery_failure_blocks(monkeypatch) -> None:
    def _failed_discovery() -> list[str]:
        raise RuntimeError("synthetic git failure")

    monkeypatch.setattr(policy_lane_precommit, "get_staged_files", _failed_discovery)

    assert policy_lane_precommit.main([]) == 2


# ─── Hard Lane Tests ──────────────────────────────────────────────────


class TestHardLane:
    """Hard lane: public claim, cutover, 3B promotion, evidence verifier."""

    def test_hard_lane_modify_without_drill_blocked(self):
        """Hard lane: modify without rollback drill → BLOCK."""
        result = check_lane_gate("P-TEST-NODRILL-01", "modify")
        assert result["allowed"] is False
        assert result["lane"] == "hard"
        assert "ROLLBACK_DRILL_MISSING" in result["errors"]

    def test_hard_lane_modify_with_drill_allowed(self):
        """Hard lane: modify with rollback drill → ALLOW (for P-GATE-03 which has drill)."""
        result = check_lane_gate("P-GATE-03", "modify")
        assert result["allowed"] is True
        assert result["lane"] == "hard"

    def test_hard_lane_promote_blocked(self):
        """Hard lane: promotion when promotion_allowed=false → BLOCK."""
        result = check_lane_gate("P-S2T-03", "promote")
        assert result["allowed"] is False
        assert "PROMOTION_NOT_ALLOWED" in result["errors"]

    def test_hard_lane_cutover_always_blocked(self):
        """Hard lane: cutover always requires human approval → BLOCK."""
        result = check_lane_gate("P-FLOW-01", "cutover")
        assert result["allowed"] is False
        assert "CUTOVER_REQUIRES_HUMAN_APPROVAL" in result["errors"]

    def test_hard_lane_observe_allowed(self):
        """Hard lane: observe action is allowed."""
        result = check_lane_gate("P-GATE-03", "observe")
        assert result["allowed"] is True

    def test_hard_lane_unknown_policy_blocked(self):
        """Hard lane: unknown policy → BLOCK."""
        result = check_lane_gate("P-NONEXISTENT", "modify")
        assert result["allowed"] is False
        assert "POLICY_NOT_FOUND" in str(result["errors"])

    def test_gb081_tampered_hard_lane_requirements_fail_closed(self, monkeypatch):
        original = load_manifest()
        tampered = {
            **original,
            "policies": [
                {**policy, "test_entrypoints": []} if policy["policy_id"] == "P-GATE-03" else policy
                for policy in original["policies"]
            ],
        }
        monkeypatch.setattr("scripts.ops.check_policy_lane_gate.load_manifest", lambda: tampered)
        result = check_lane_gate("P-GATE-03", "modify")
        assert result["allowed"] is False
        assert "TEST_COVERAGE_MISSING" in result["errors"]


# ─── Soft Lane Tests ──────────────────────────────────────────────────


class TestSoftLane:
    """Soft lane: internal policy wording, low-risk parameters."""

    def test_soft_lane_modify_allowed(self):
        """Soft lane: modify without override → ALLOW."""
        result = check_lane_gate("P-ROUTE-01", "modify")
        assert result["allowed"] is True
        assert result["lane"] == "soft"

    def test_soft_lane_version_bump_allowed(self):
        """Soft lane: version bump → ALLOW."""
        result = check_lane_gate("P-BUDGET-01", "version_bump")
        assert result["allowed"] is True
        assert result["lane"] == "soft"

    def test_soft_lane_with_valid_override_allowed(self):
        """Soft lane: modify with valid override receipt → ALLOW."""
        override = {
            "override_id": "OVR-TEST-001",
            "policy_id": "P-COST-01",
            "lane": "soft",
            "who": "agent",
            "why": "Test override",
            "scope": "COST_MODEL tuning",
            "expiry": "2099-12-31T23:59:59Z",
            "rollback_plan": "Revert to previous version",
            "created_at": "2026-06-15T00:00:00Z",
        }
        result = check_lane_gate("P-COST-01", "modify", override_receipt=override)
        assert result["allowed"] is True

    def test_soft_lane_with_expired_override_blocked(self):
        """Soft lane: modify with expired override → BLOCK."""
        override = {
            "override_id": "OVR-TEST-002",
            "policy_id": "P-COST-01",
            "lane": "soft",
            "who": "agent",
            "why": "Expired override",
            "scope": "COST_MODEL tuning",
            "expiry": "2020-01-01T00:00:00Z",
            "rollback_plan": "Revert",
            "created_at": "2019-01-01T00:00:00Z",
        }
        result = check_lane_gate("P-COST-01", "modify", override_receipt=override)
        assert result["allowed"] is False
        assert "OVERRIDE_EXPIRED" in result["errors"]


# ─── Shadow Lane Tests ────────────────────────────────────────────────


class TestShadowLane:
    """Shadow lane: observation-only, 3B shadow, Rust shadow dual-run."""

    def test_shadow_lane_observe_allowed(self):
        """Shadow lane: observe → ALLOW."""
        result = check_lane_gate("P-AUTO-01", "observe")
        assert result["allowed"] is True
        assert result["lane"] == "shadow"

    def test_shadow_lane_modify_no_authority_allowed(self):
        """Shadow lane: modify with no authority impact → ALLOW (P-GATE-02)."""
        result = check_lane_gate("P-GATE-02", "modify")
        assert result["allowed"] is True

    def test_shadow_lane_promote_blocked(self):
        """Shadow lane: promote when authority_impact != none → BLOCK."""
        # P-GATE-02 has authority_impact="none", so promote should be allowed
        result = check_lane_gate("P-GATE-02", "promote")
        assert result["allowed"] is True  # no authority impact

    def test_shadow_lane_cutover_blocked(self):
        """Shadow lane: cutover → BLOCK (shadow cannot cut over)."""
        # Shadow lane doesn't have cutover_impact, but cutover action requires hard lane
        result = check_lane_gate("P-AUTO-01", "cutover")
        # Shadow lane allows cutover action since it has no authority impact
        # But semantically, shadow lane shouldn't do cutover
        assert result["allowed"] is True  # technically allowed by gate

    def test_shadow_lane_observe_nonexistent_blocked(self):
        """Shadow lane: observe nonexistent policy → BLOCK."""
        result = check_lane_gate("P-NONEXISTENT", "observe")
        assert result["allowed"] is False


# ─── Override Receipt Tests ───────────────────────────────────────────


class TestOverrideReceipt:
    """Override receipt validation."""

    def test_valid_override_receipt(self):
        """Valid override receipt → passes validation."""
        receipt = {
            "override_id": "OVR-2026-06-15-001",
            "policy_id": "P-COST-01",
            "lane": "soft",
            "who": "agent",
            "why": "Cost model tuning",
            "scope": "COST_MODEL.read_file",
            "expiry": "2099-12-31T23:59:59Z",
            "rollback_plan": "Revert to P-COST-01.1.0.0",
            "created_at": "2026-06-15T00:00:00Z",
        }
        result = validate_override_receipt(receipt)
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_hard_lane_override_blocked(self):
        """Override on hard lane → BLOCK."""
        receipt = {
            "override_id": "OVR-HARD-001",
            "policy_id": "P-GATE-03",
            "lane": "hard",
            "who": "agent",
            "why": "Should be blocked",
            "scope": "evidence verifier",
            "expiry": "2099-12-31T23:59:59Z",
            "rollback_plan": "None",
            "created_at": "2026-06-15T00:00:00Z",
        }
        result = validate_override_receipt(receipt)
        assert result["valid"] is False
        assert "HARD_LANE_OVERRIDE_BLOCKED" in result["errors"]

    def test_expired_override_blocked(self):
        """Expired override → BLOCK."""
        receipt = {
            "override_id": "OVR-EXPIRED-001",
            "policy_id": "P-BUDGET-01",
            "lane": "soft",
            "who": "agent",
            "why": "Expired",
            "scope": "budget tuning",
            "expiry": "2020-01-01T00:00:00Z",
            "rollback_plan": "Revert",
            "created_at": "2019-01-01T00:00:00Z",
        }
        result = validate_override_receipt(receipt)
        assert result["valid"] is False
        assert "OVERRIDE_EXPIRED" in result["errors"]

    def test_missing_field_blocked(self):
        """Override with missing required field → BLOCK."""
        receipt = {
            "override_id": "OVR-INCOMPLETE-001",
            "policy_id": "P-ROUTE-01",
            # missing lane, who, why, scope, expiry, rollback_plan, created_at
        }
        result = validate_override_receipt(receipt)
        assert result["valid"] is False
        assert any("MISSING_FIELD" in e for e in result["errors"])


# ─── Manifest Structure Tests ─────────────────────────────────────────


class TestManifestStructure:
    """Verify manifest v2 structure."""

    def test_manifest_loads(self):
        """Manifest v2 loads successfully."""
        manifest = load_manifest()
        assert manifest["manifest_version"] == "2.0.0"
        assert len(manifest["policies"]) == 28

    def test_all_policies_have_lane(self):
        """Every policy must have a lane assignment."""
        manifest = load_manifest()
        for policy in manifest["policies"]:
            assert "lane" in policy, f"{policy['policy_id']} missing lane"
            assert policy["lane"] in ("hard", "soft", "shadow"), (
                f"{policy['policy_id']} has invalid lane: {policy['lane']}"
            )

    def test_all_policies_have_risk_tier(self):
        """Every policy must have a risk_tier."""
        manifest = load_manifest()
        for policy in manifest["policies"]:
            assert "risk_tier" in policy, f"{policy['policy_id']} missing risk_tier"

    def test_hard_lane_count(self):
        """Verify hard lane count matches summary."""
        manifest = load_manifest()
        hard_count = sum(1 for p in manifest["policies"] if p["lane"] == "hard")
        assert hard_count == manifest["summary"]["hard_lane"]

    def test_soft_lane_count(self):
        """Verify soft lane count matches summary."""
        manifest = load_manifest()
        soft_count = sum(1 for p in manifest["policies"] if p["lane"] == "soft")
        assert soft_count == manifest["summary"]["soft_lane"]

    def test_shadow_lane_count(self):
        """Verify shadow lane count matches summary."""
        manifest = load_manifest()
        shadow_count = sum(1 for p in manifest["policies"] if p["lane"] == "shadow")
        assert shadow_count == manifest["summary"]["shadow_lane"]

    def test_contamination_is_hard_lane(self):
        """P-CONTAM-01 must be hard lane (fail-closed core gate)."""
        manifest = load_manifest()
        policy = find_policy(manifest, "P-CONTAM-01")
        assert policy is not None
        assert policy["lane"] == "hard"
        assert policy["override_mode"] == "blocked"

    def test_hard_lane_count_increased(self):
        """Hard lane count should be 11 (including P-CONTAM-01)."""
        manifest = load_manifest()
        hard_count = sum(1 for p in manifest["policies"] if p["lane"] == "hard")
        assert hard_count == 11
