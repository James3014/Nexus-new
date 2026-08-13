"""Fail-closed consumer for the NightShift bounded-candidate manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.services.unified_runtime import UnifiedRuntimeRequest

SCHEMA = "nexus.nightshift_candidate_demand.v1"
REQUIRED_CONTROLS = frozenset(
    {"isolated_directory", "bounded_context", "json_event_receipt", "parser", "focused_tests", "verifier"}
)
FORBIDDEN_WORKER_ACTIONS = frozenset({"commit", "push", "approve", "integrate"})


class NightshiftQueueConsumer:
    """Validate one manifest and dispatch only after canonical ALLOW evidence."""

    def __init__(
        self,
        runtime_runner: Callable[[UnifiedRuntimeRequest], Mapping[str, Any]],
        dispatcher: Callable[[Mapping[str, Any]], Any],
    ) -> None:
        self._runtime_runner = runtime_runner
        self._dispatcher = dispatcher
        self._seen: set[tuple[str, str]] = set()

    def consume_file(self, manifest_path: Path) -> list[dict[str, Any]]:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [{"status": "BLOCK", "reason": "manifest_unreadable"}]
        if not isinstance(payload, list):
            return [{"status": "BLOCK", "reason": "manifest_must_be_array"}]
        return [self._consume_item(item) for item in payload]

    def _consume_item(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, Mapping):
            return {"status": "BLOCK", "reason": "item_malformed"}
        missing = REQUIRED_CONTROLS - set(item.get("required_controls", ()))
        if item.get("schema") != SCHEMA:
            return {"status": "BLOCK", "reason": "schema_invalid"}
        if item.get("demand_role") != "bounded_candidate_generation":
            return {"status": "BLOCK", "reason": "role_invalid"}
        if item.get("mutation_intent") is not False or item.get("external_verification_required") is not True:
            return {"status": "BLOCK", "reason": "safety_flags_invalid"}
        permissions = item.get("worker_permissions")
        if not isinstance(permissions, Mapping) or any(permissions.get(action) is not False for action in FORBIDDEN_WORKER_ACTIONS):
            return {"status": "BLOCK", "reason": "worker_permissions_invalid"}
        if missing:
            return {"status": "BLOCK", "reason": "required_controls_missing", "missing": sorted(missing)}
        task = str(item.get("task") or "").strip()
        revision = str(item.get("commit_sha") or "").strip()
        if not task or not revision:
            return {"status": "BLOCK", "reason": "identity_missing"}
        key = (task, revision)
        if key in self._seen:
            return {"status": "SKIP", "reason": "duplicate", "task": task}
        self._seen.add(key)
        request = UnifiedRuntimeRequest(
            task_id=f"nightshift-queue-{task}",
            workspace_revision=revision,
            task_statement=task,
            task_type="candidate_generation",
            route={
                "online_enabled": True,
                "candidate_generation_only": True,
                "topology_facts": {"candidate_generation_only": True},
                "workforce_admission_enabled": True,
                "workforce_bindings": item.get("workforce_bindings", {}),
            },
            online_prompt=task,
            online_payload=task,
        )
        try:
            receipt = self._runtime_runner(request)
        except Exception:
            return {"status": "BLOCK", "reason": "runtime_failed", "task": task}
        admission = receipt.get("workforce_admission") if isinstance(receipt, Mapping) else None
        if not isinstance(admission, Mapping) or admission.get("overall_decision") != "ALLOW":
            return {"status": "BLOCK", "reason": "workforce_admission_not_allow", "task": task}
        self._dispatcher(item)
        return {"status": "DISPATCHED", "task": task}


__all__ = ["NightshiftQueueConsumer", "REQUIRED_CONTROLS", "SCHEMA"]
