from __future__ import annotations

from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)


def test_cloud_primary_local_assist_deterministic():
    """Deterministic test: cloud_available=True, local assist mode."""
    req = LocalModelExecutorRequest(
        task_id="cloud-assist-1",
        problem_statement="fix code",
        repo_root="/ws",
        target_file="a.py",
        selected_capabilities=("local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"),
        evidence_refs=("ref1",),
        dry_run=True,
        execution_topology="local_committee_only",
        route_context={
            "signal_snapshot": {"execution_topology": "local_committee_only"},
            "cloud_available": True,
        },
    )
    resp = LocalModelExecutor.run(req)

    # In dry_run mode, we get a response but no real execution
    assert resp.invoked is False
    assert resp.raw_model_metadata.get("execution_topology") == "local_committee_only"


def test_cloud_unavailable_falls_to_local():
    """When cloud unavailable, execution falls to local topology."""
    req = LocalModelExecutorRequest(
        task_id="cloud-unavail-1",
        problem_statement="fix code",
        repo_root="/ws",
        target_file="a.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=("ref1",),
        dry_run=True,
        execution_topology="local_committee_only",
        route_context={
            "signal_snapshot": {"execution_topology": "local_committee_only"},
            "cloud_available": False,
        },
    )
    resp = LocalModelExecutor.run(req)
    assert resp.invoked is False
    assert resp.raw_model_metadata.get("execution_topology") == "local_committee_only"
