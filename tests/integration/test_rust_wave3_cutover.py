"""Rust wave-3 cutover retired (Owner decision A, 2026-10-16, #2359).

These tests used to dual-run the nexus-core-rs flow_machine binary against a Python
reference through nexus.bridge.rust_kernel. The crate, the bridge and policy P-FLOW-01
were retired together. The test ids are kept on purpose (the exact-base impact gate
reads a vanished id as lost coverage); each one now asserts the retired state.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "reports" / "policy-manifest.v2.json"


def test_dual_run_all_transitions():
    """The Rust side of the dual run is gone: no crate, no kernel source."""
    assert not (ROOT / "nexus-core-rs" / "src" / "flow_machine.rs").exists()
    assert not (ROOT / "nexus-core-rs" / "Cargo.toml").exists()


def test_dual_run_legal_counts_match():
    """P-FLOW-01, which named this file as its entrypoint, is no longer a policy."""
    policies = json.loads(MANIFEST.read_text(encoding="utf-8"))["policies"]
    ids = {policy["policy_id"] for policy in policies}
    assert "P-FLOW-01" not in ids
    for policy in policies:
        bound = [policy.get("source_file", ""), *policy.get("test_entrypoints", [])]
        assert all("nexus-core-rs" not in str(item) for item in bound), policy["policy_id"]


def test_fail_closed_on_unknown_transition():
    """The Rust IPC adapter is not importable any more."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("nexus.bridge.rust_kernel")


def test_flow_transition_ipc_basic():
    """Without a kernel binary the governance bridge falls back to its Python contract path."""
    from nexus.engine.governance_bridge import GovernanceBridge

    bridge = GovernanceBridge()
    assert bridge.rs_client.binary_path is None
    reply = bridge.rs_client.validate_transition("intake", "clarify")
    assert reply["success"] is False
    assert reply["error_message"].startswith("Binary not found")
    assert bridge.can_transition("intake", "clarify") == bridge._python_validate(
        "intake", "clarify"
    )
