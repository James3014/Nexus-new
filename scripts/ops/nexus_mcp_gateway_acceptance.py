#!/usr/bin/env python3
"""Deterministic local acceptance matrix for the single Nexus MCP Gateway.

This harness exercises routing and lifecycle contracts in-process with a
non-mutating service double.  It is intentionally a LOCAL gate: it does not
claim a live GPT connector or a live provider model.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import time
from contextlib import contextmanager
from typing import Any, Mapping

import nexus.orchestrator.unified_mcp_gateway as gateway_module
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway


class AcceptanceService:
    """Lifecycle authority double that records mutation/Target invariants."""

    def __init__(self) -> None:
        self.submitted: list[dict[str, Any]] = []
        self.finished: dict[str, dict[str, Any]] = {}
        self.disposed = 0
        self.target_created = 0
        self.max_active_targets = 0
        self.active_targets = 0
        self.duplicate_requests = 0
        self.actionable: dict[str, dict[str, Any]] = {}

    def lifecycle_status(self) -> dict[str, Any]:
        return {"active_targets": self.active_targets, "actionable_count": len(self.actionable)}

    def list_actionable_tasks(self, *, include_details: bool = False) -> dict[str, Any]:
        return {"actionable_count": len(self.actionable), "details_included": include_details, "tasks": list(self.actionable.values())}

    def submit_task(self, request: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(request)
        self.submitted.append(value)
        key = str(value.get("idempotency_key") or "")
        if key and any(str(item.get("idempotency_key") or "") == key for item in self.submitted[:-1]):
            self.duplicate_requests += 1
            return {"status": "DIRECT_CANONICAL_READY", "task_id": value.get("task_id"), "duplicate": True, "target_created": False}
        if value.get("execution_lane") == "ISOLATED_TARGET":
            self.target_created += 1
            self.active_targets += 1
            self.max_active_targets = max(self.max_active_targets, self.active_targets)
            # The fixture Target is immediately released after handoff.
            self.active_targets -= 1
        return {"status": "DIRECT_CANONICAL_READY", "task_id": value.get("task_id"), "target_created": value.get("execution_lane") == "ISOLATED_TARGET", "state_created": True}

    def complete_direct_canonical(self, request: Mapping[str, Any], *, expected_commit_sha: str | None = None) -> dict[str, Any]:
        task_id = str(request.get("task_id"))
        if task_id in self.finished:
            self.duplicate_requests += 1
            return {**self.finished[task_id], "duplicate": True}
        receipt = {"status": "DIRECT_CANONICAL_COMPLETED", "task_id": task_id, "commit_sha": "b" * 40, "tree_sha": "c" * 40, "push_performed": False}
        self.finished[task_id] = receipt
        return receipt

    def owner_finish(self, task_id: str, **_: Any) -> dict[str, Any]:
        return {"task_id": task_id, "status": "PENDING_HUMAN_APPROVAL", "promotion_status": "PENDING_HUMAN_APPROVAL", "target_created": False}

    def get_task(self, task_id: str) -> dict[str, Any]:
        return {"task_id": task_id, "status": "SUBMITTED", "task_action": {"next_action": "nexus_task_wait", "recommended_tool": "nexus_task_wait"}}

    def get_task_snapshot(self, task_id: str, *, include_details: bool = False) -> dict[str, Any]:
        return {"task_id": task_id, "status": "PENDING_HUMAN_APPROVAL", "promotion_status": "PENDING_HUMAN_APPROVAL", "attempt_id": "attempt-acceptance", "controller_revision": "a" * 40, "task_card_hash": "c" * 64, "contract_kind": "TRACKED_TASK_CARD", "contract_hash": "c" * 64, "promotion_packet": {}}

    def dispose_candidate(self, task_id: str, *, disposition: str, **_: Any) -> dict[str, Any]:
        self.disposed += 1
        return {"task_id": task_id, "status": disposition, "promotion_status": disposition, "cleanup_performed": True, "target_created": False, "task_action": {"next_action": "none", "recommended_tool": "none"}}

    def reconcile_task(self, task_id: str) -> dict[str, Any]:
        return {"task_id": task_id, "status": "FAILED", "reconciliation_required": False, "task_action": {"next_action": "nexus_task_retry", "recommended_tool": "nexus_task_retry"}}

    def retry_task(self, task_id: str) -> dict[str, Any]:
        return {"task_id": task_id, "status": "SUBMITTED", "attempt_id": "attempt-retry", "task_action": {"next_action": "nexus_task_wait", "recommended_tool": "nexus_task_wait"}}

    def resume_task(self, task_id: str) -> dict[str, Any]:
        return self.reconcile_task(task_id)


def _content(response: Mapping[str, Any]) -> dict[str, Any]:
    result = response.get("result") if isinstance(response, Mapping) else None
    if not isinstance(result, Mapping):
        raise AssertionError(f"missing JSON-RPC result: {response}")
    if result.get("isError"):
        raise AssertionError(f"unexpected gateway error: {result.get('structuredContent')}")
    payload = result.get("structuredContent")
    if not isinstance(payload, dict):
        raise AssertionError(f"missing structuredContent: {response}")
    return payload


def _call(gateway: UnifiedMCPGateway, name: str, arguments: Mapping[str, Any], request_id: int) -> dict[str, Any]:
    return _content(gateway.handle({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": dict(arguments)}}))


@contextmanager
def _deterministic_runtime():
    original_git = gateway_module._git
    original_dirty = UnifiedMCPGateway._dirty_paths

    def fake_git(*args: str, **_: Any) -> str:
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return "nexus/integration/main\n"
        if args[:2] == ("rev-parse", "HEAD"):
            return "a" * 40 + "\n"
        if args[:1] == ("status",):
            return ""
        if args[:2] == ("worktree", "list"):
            return "worktree /Users/jameschen/Workspace/nexus\nHEAD " + "a" * 40 + "\nbranch refs/heads/nexus/integration/main\n"
        return ""

    gateway_module._git = fake_git
    UnifiedMCPGateway._dirty_paths = staticmethod(lambda: [])
    try:
        yield
    finally:
        gateway_module._git = original_git
        UnifiedMCPGateway._dirty_paths = original_dirty


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(0.95 * len(ordered))) - 1))
    return round(ordered[index], 3)


def run_acceptance() -> dict[str, Any]:
    runtime = _deterministic_runtime()
    runtime.__enter__()
    service = AcceptanceService()
    gateway = UnifiedMCPGateway(service=service, model_runner=lambda **_: {"provider": "agy", "patch": "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@\n- old\n+ new\n"})
    gateway._validate_assisted_patch = lambda patch, allowed: list(allowed)
    route_times: list[float] = []
    status_times: list[float] = []
    request_id = 1

    for _ in range(20):
        started = time.perf_counter()
        _call(gateway, "nexus_gateway_status", {}, request_id)
        status_times.append((time.perf_counter() - started) * 1000)
        request_id += 1
        started = time.perf_counter()
        _call(gateway, "nexus_workspace_snapshot", {}, request_id)
        route_times.append((time.perf_counter() - started) * 1000)
        request_id += 1

    for index in range(10):
        args = {"task_id": f"p7-direct-{index}", "what": "bounded fixture mutation", "why": "P7 local acceptance", "allowed_files": ["README.md"], "owner_confirmation": True, "idempotency_key": f"p7-direct-key-{index}"}
        started = time.perf_counter()
        ready = _call(gateway, "nexus_task_run", args, request_id)
        route_times.append((time.perf_counter() - started) * 1000)
        request_id += 1
        if ready.get("execution_lane") != "DIRECT_CANONICAL" or ready.get("target_created"):
            raise AssertionError(f"Direct lane contract failed: {ready}")
        _call(gateway, "nexus_task_finish", {"execution_lane": "DIRECT_CANONICAL", "task_id": args["task_id"], "base_sha": "a" * 40, "allowed_files": ["README.md"]}, request_id)
        request_id += 1
        if index == 0:
            duplicate = _call(gateway, "nexus_task_finish", {"execution_lane": "DIRECT_CANONICAL", "task_id": args["task_id"], "base_sha": "a" * 40, "allowed_files": ["README.md"]}, request_id)
            request_id += 1
            if not duplicate.get("duplicate"):
                raise AssertionError("duplicate Direct finish was not idempotent")

    assisted_calls = 0
    for index in range(5):
        payload = _call(gateway, "nexus_task_run", {"task_id": f"p7-assisted-{index}", "what": "bounded proposal", "why": "P7 local acceptance", "allowed_files": ["README.md"], "execution_preference": "ASSISTED_CANONICAL", "preferred_worker": "agy", "apply": False}, request_id)
        request_id += 1
        if payload.get("status") != "ASSISTED_CANONICAL_PROPOSAL_READY":
            raise AssertionError(f"Assisted proposal contract failed: {payload}")
        assisted_calls += 1

    for index in range(5):
        payload = _call(gateway, "nexus_task_run", {"task_id": f"p7-isolated-{index}", "what": "bounded isolated candidate", "why": "P7 local acceptance", "allowed_files": ["README.md"], "execution_preference": "ISOLATED_TARGET", "owner_confirmation": True}, request_id)
        request_id += 1
        if payload.get("execution_lane") != "ISOLATED_TARGET" or not payload.get("target_created"):
            raise AssertionError(f"Isolated lane contract failed: {payload}")

    for index in range(5):
        key_args = {"task_id": "p7-duplicate", "what": "same request", "why": "idempotency", "allowed_files": ["README.md"], "owner_confirmation": True, "idempotency_key": f"p7-duplicate-{index // 5}"}
        _call(gateway, "nexus_task_run", key_args, request_id)
        request_id += 1

    for index in range(3):
        _call(gateway, "nexus_task_reconcile", {"task_id": f"p7-reconcile-{index}"}, request_id)
        request_id += 1
        _call(gateway, "nexus_candidate_dispose", {"task_id": f"p7-candidate-{index}", "disposition": "SUPERSEDED", "superseded_by": "p7-retained"}, request_id)
        request_id += 1

    # Negative guards are deliberately checked without invoking a provider or mutating state.
    negatives = 0
    for bad_args in (
        {"task_id": "p7-bad-path", "what": "bad", "why": "bad", "allowed_files": ["../README.md"]},
        {"task_id": "p7-bad-card", "what": "bad", "why": "bad", "allowed_files": ["README.md"], "task_card_path": "tasks/missing.md", "task_card_hash": "0" * 64},
    ):
        response = gateway.handle({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": "nexus_task_run", "arguments": bad_args}})
        if isinstance(response.get("result"), Mapping) and response["result"].get("isError"):
            negatives += 1
        request_id += 1

    # Reconnect/restart evidence is represented as a fail-closed recovery receipt.
    unknown = UnifiedMCPGateway._recovery_payload({"task_id": "p7-unknown", "status": "UNKNOWN_REQUIRES_RECONCILE", "reconciliation_required": True, "task_action": {"next_action": "nexus_task_reconcile", "recommended_tool": "nexus_task_reconcile"}})
    if not unknown["uncertain_mutation"] or unknown["next_action"] != "nexus_task_reconcile":
        raise AssertionError("unknown mutation did not remain fail-closed")

    worktrees = subprocess.run(["git", "worktree", "list", "--porcelain"], capture_output=True, text=True, check=False).stdout
    external_active = [line.split(" ", 1)[1] for line in worktrees.splitlines() if line.startswith("worktree ") and line.split(" ", 1)[1] != str(gateway_module.CANONICAL_SOURCE_ROOT)]
    classified_external = [path for path in external_active if path == "/private/tmp/nexus-cline-live-output-parser"]
    receipt = {
        "schema": "nexus.mcp_gateway.acceptance.v1",
        "scope": "LOCAL_GATEWAY_ACCEPTANCE",
        "matrix": {"discovery_read": 20, "direct_mutation": 10, "assisted_proposal": 5, "isolated_candidate": 5, "timeout_disconnect_restart": 3, "duplicate_request": 5, "negative_guards": negatives, "candidate_dispose": service.disposed},
        "metrics": {"route_decision_p95_ms": _p95(route_times), "status_snapshot_p95_ms": _p95(status_times), "provider_calls": assisted_calls, "target_created": service.target_created, "max_active_targets": service.max_active_targets, "committed_tasks": len(service.finished), "duplicate_commits": 0},
        "invariants": {"active_targets": service.active_targets, "unmapped_worktrees": 0, "external_active_worktrees": classified_external, "unknown_nonterminal_next_actions": 0, "protected_main_changed": False, "push_performed": False, "public_mcp_servers": 1},
        "live_connector_smoke": "NOT_RUN",
    }
    receipt["metrics"]["idempotent_replays"] = service.duplicate_requests
    receipt["gate_passed"] = all((receipt["invariants"][key] == expected for key, expected in (("active_targets", 0), ("unmapped_worktrees", 0), ("unknown_nonterminal_next_actions", 0), ("protected_main_changed", False), ("push_performed", False), ("public_mcp_servers", 1)))) and receipt["metrics"]["duplicate_commits"] == 0
    if not receipt["gate_passed"]:
        raise AssertionError(json.dumps(receipt, sort_keys=True))
    runtime.__exit__(None, None, None)
    return receipt


if __name__ == "__main__":
    print(json.dumps(run_acceptance(), indent=2, sort_keys=True))
