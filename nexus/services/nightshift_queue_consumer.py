"""Fail-closed consumer for the NightShift bounded-candidate manifest."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.services.unified_runtime import UnifiedRuntimeRequest

SCHEMA = "nexus.nightshift_candidate_demand.v1"
REQUIRED_CONTROLS = frozenset({
    "isolated_directory",
    "bounded_context",
    "json_event_receipt",
    "parser",
    "focused_tests",
    "verifier",
})
FORBIDDEN_WORKER_ACTIONS = frozenset({"commit", "push", "approve", "integrate"})


class NightshiftQueueConsumer:
    """Validate one manifest and dispatch only after canonical ALLOW evidence."""

    def __init__(
        self,
        runtime_runner: Callable[[UnifiedRuntimeRequest], Mapping[str, Any]],
        dispatcher: Callable[[Mapping[str, Any]], Any],
        project_root: Path | None = None,
    ) -> None:
        self._runtime_runner = runtime_runner
        self._dispatcher = dispatcher
        self._project_root = project_root.resolve() if project_root else None

    def consume_file(self, manifest_path: Path) -> list[dict[str, Any]]:
        if self._project_root is not None:
            expected = self._project_root / ".nexus/nightshift/pending.json"
            if manifest_path.resolve() != expected:
                return [{"status": "BLOCK", "reason": "noncanonical_manifest_path"}]
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [{"status": "BLOCK", "reason": "manifest_unreadable"}]
        if not isinstance(payload, list):
            return [{"status": "BLOCK", "reason": "manifest_must_be_array"}]
        results = []
        changed = False
        dispatched_ids: set[tuple[str, str]] = set()
        for item in payload:
            if isinstance(item, Mapping) and item.get("disposition") == "DISPATCHED":
                results.append({"status": "SKIP", "reason": "already_dispatched"})
                continue
            if isinstance(item, Mapping):
                identity = (str(item.get("task") or ""), str(item.get("commit_sha") or ""))
                if all(identity) and identity in dispatched_ids:
                    results.append({"status": "SKIP", "reason": "duplicate"})
                    continue
            result = self._consume_item(item)
            results.append(result)
            if isinstance(item, Mapping):
                identity = (str(item.get("task") or ""), str(item.get("commit_sha") or ""))
            if result.get("status") == "DISPATCHED" and isinstance(item, dict):
                identity = (str(item.get("task") or ""), str(item.get("commit_sha") or ""))
                if all(identity):
                    dispatched_ids.add(identity)
                item["disposition"] = "DISPATCHED"
                item["disposition_task"] = result.get("task")
                changed = True
        if changed:
            fd, temporary = tempfile.mkstemp(
                prefix="pending.", suffix=".json", dir=str(manifest_path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, manifest_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return results

    def _consume_item(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, Mapping):
            return {"status": "BLOCK", "reason": "item_malformed"}
        missing = REQUIRED_CONTROLS - set(item.get("required_controls", ()))
        if item.get("schema") != SCHEMA:
            return {"status": "BLOCK", "reason": "schema_invalid"}
        if item.get("demand_role") != "bounded_candidate_generation":
            return {"status": "BLOCK", "reason": "role_invalid"}
        if (
            item.get("mutation_intent") is not False
            or item.get("external_verification_required") is not True
        ):
            return {"status": "BLOCK", "reason": "safety_flags_invalid"}
        permissions = item.get("worker_permissions")
        if not isinstance(permissions, Mapping) or any(
            permissions.get(action) is not False for action in FORBIDDEN_WORKER_ACTIONS
        ):
            return {"status": "BLOCK", "reason": "worker_permissions_invalid"}
        if missing:
            return {
                "status": "BLOCK",
                "reason": "required_controls_missing",
                "missing": sorted(missing),
            }
        task = str(item.get("task") or "").strip()
        revision = str(item.get("commit_sha") or "").strip()
        if not task or not revision:
            return {"status": "BLOCK", "reason": "identity_missing"}
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
        authority = (
            receipt.get("gateway_invocation_authority") if isinstance(receipt, Mapping) else None
        )
        if not isinstance(admission, Mapping) or admission.get("overall_decision") != "ALLOW":
            return {"status": "BLOCK", "reason": "workforce_admission_not_allow", "task": task}
        if (
            not isinstance(authority, Mapping)
            or authority.get("status") != "ALLOW"
            or not authority.get("gate_passed")
        ):
            return {
                "status": "BLOCK",
                "reason": "canonical_invocation_authority_missing",
                "task": task,
            }
        self._dispatcher(item)
        return {"status": "DISPATCHED", "task": task}


__all__ = ["NightshiftQueueConsumer", "REQUIRED_CONTROLS", "SCHEMA"]
