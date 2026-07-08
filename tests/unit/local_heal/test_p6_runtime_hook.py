"""P6-B4: Env-Guarded Runtime Hook Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.p6_runtime_hook import evaluate_p6_runtime_hook


def test_flag_off_runtime_unchanged():
    """P6-B4: flag off → runtime route unchanged."""
    os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)
    result = evaluate_p6_runtime_hook()
    assert result.p6_enabled is False
    assert result.degradation_action == "keep_full_committee"
    assert result.runtime_route_changed is False


def test_flag_on_healthy_keep_committee():
    """P6-B4: flag on + healthy → keep_full_committee."""
    os.environ["NEXUS_ENABLE_P6_QUOTA_DEGRADATION"] = "1"
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "10"
    try:
        result = evaluate_p6_runtime_hook()
        assert result.p6_enabled is True
        assert result.degradation_action == "keep_full_committee"
    finally:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def test_flag_on_constrained_reduce():
    """P6-B4: flag on + constrained → candidate_count reduced."""
    os.environ["NEXUS_ENABLE_P6_QUOTA_DEGRADATION"] = "1"
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "5"
    try:
        result = evaluate_p6_runtime_hook(requested_candidate_count=5)
        assert result.p6_enabled is True
        assert result.degradation_action == "reduce_candidate_count"
        assert result.candidate_count_limit is not None
        assert result.candidate_count_limit >= 2
    finally:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def test_flag_on_exhausted_local_only():
    """P6-B4: flag on + exhausted + local → local_only."""
    os.environ["NEXUS_ENABLE_P6_QUOTA_DEGRADATION"] = "1"
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "0"
    try:
        result = evaluate_p6_runtime_hook(local_available=True)
        assert result.p6_enabled is True
        assert result.degradation_action == "local_only"
        assert result.cloud_allowed is False
    finally:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def test_flag_on_unknown_fail_closed():
    """P6-B4: flag on + unknown → fail_closed, never healthy."""
    os.environ["NEXUS_ENABLE_P6_QUOTA_DEGRADATION"] = "1"
    os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)
    try:
        result = evaluate_p6_runtime_hook()
        assert result.p6_enabled is True
        assert result.degradation_action == "fail_closed"
    finally:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)


def test_memory_cannot_change_action():
    """P6-B4: memory/belief cannot change action."""
    os.environ["NEXUS_ENABLE_P6_QUOTA_DEGRADATION"] = "1"
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "10"
    try:
        result = evaluate_p6_runtime_hook()
        # Memory is not part of the hook decision
        assert result.decision.memory_signal_used_for_quota is False
    finally:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def test_verifier_claim_required():
    """P6-B4: verifier and claim gate remain required."""
    os.environ["NEXUS_ENABLE_P6_QUOTA_DEGRADATION"] = "1"
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "10"
    try:
        result = evaluate_p6_runtime_hook()
        assert result.decision.verifier_required is True
        assert result.decision.claim_gate_required is True
    finally:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)


def test_env_guard_recorded():
    """P6-B4: receipt records env_guard=true."""
    os.environ["NEXUS_ENABLE_P6_QUOTA_DEGRADATION"] = "1"
    os.environ["NEXUS_CLOUD_BUDGET_REMAINING"] = "10"
    try:
        result = evaluate_p6_runtime_hook()
        assert result.decision.env_guard_required is True
        assert result.decision.runtime_route_mutation_allowed is False
    finally:
        os.environ.pop("NEXUS_ENABLE_P6_QUOTA_DEGRADATION", None)
        os.environ.pop("NEXUS_CLOUD_BUDGET_REMAINING", None)
