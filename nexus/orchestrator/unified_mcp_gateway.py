"""Single GPT-visible MCP gateway for bounded Nexus workspace/lifecycle actions.

The gateway deliberately exposes a small public surface.  The existing
29-action self-hosted server remains an internal lifecycle provider; callers
must not need to know its Target paths or internal action names.
"""

from __future__ import annotations

import hashlib
import json
import fcntl
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.contracts.lifecycle_action import (
    LifecycleActionType,
    PermissionProfile,
    build_action_envelope,
)
from nexus.orchestrator.self_hosted_task_service import CANONICAL_SOURCE_ROOT, SelfHostedTaskService
from nexus.services.unified_runtime import ONLINE_CLI_SPEC_REGISTRY
from nexus.services.model_workforce_policy import NON_ADMISSIBLE_STATES, WorkforcePolicyLoader

GATEWAY_NAME = "nexus-mcp-gateway"
GATEWAY_VERSION = "0.1.0"
MAX_READ_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 1024 * 1024
MAX_SEARCH_RESULTS = 200
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

PUBLIC_TOOL_NAMES = (
    "nexus_gateway_status",
    "nexus_workspace_snapshot",
    "nexus_read",
    "nexus_search",
    "nexus_git_diff",
    "nexus_task_run",
    "nexus_task_status",
    "nexus_task_wait",
    "nexus_task_finish",
    "nexus_task_cancel",
)
TOOL_MANIFEST_REVISION = hashlib.sha256(
    json.dumps(PUBLIC_TOOL_NAMES, separators=(",", ":")).encode("utf-8")
).hexdigest()


class GatewayInputError(ValueError):
    """Raised when a public gateway request is outside its bounded contract."""


def _text(value: Any, field: str, *, max_length: int = 4096) -> str:
    result = str(value or "").strip()
    if not result:
        raise GatewayInputError(f"{field} is required")
    if len(result) > max_length:
        raise GatewayInputError(f"{field} exceeds {max_length} characters")
    return result


def _safe_relative_path(value: Any, field: str = "path") -> Path:
    raw = _text(value, field, max_length=1024)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise GatewayInputError(f"{field} must be a bounded relative path")
    if ".git" in candidate.parts:
        raise GatewayInputError(f"{field} cannot access .git")
    resolved = (CANONICAL_SOURCE_ROOT / candidate).resolve()
    try:
        resolved.relative_to(CANONICAL_SOURCE_ROOT)
    except ValueError as exc:
        raise GatewayInputError(f"{field} escapes canonical root") from exc
    return resolved


def _git(*args: str, timeout: float = 3.0) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=CANONICAL_SOURCE_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git command failed: {' '.join(args)}")
    return result.stdout


def _bounded_text(value: str, field: str) -> str:
    if len(value.encode("utf-8")) > MAX_RESULT_BYTES:
        raise RuntimeError(f"{field} exceeds {MAX_RESULT_BYTES} bytes")
    return value


class UnifiedMCPGateway:
    """JSON-RPC MCP server with one public identity and bounded tools."""

    def __init__(self, service: Optional[SelfHostedTaskService] = None, *, model_runner: Any = None, apply_runner: Any = None):
        self.service = service or SelfHostedTaskService()
        self._model_runner = model_runner or self._run_agy_plan
        self._apply_runner = apply_runner or self._apply_assisted_patch
        self._workforce_loader = WorkforcePolicyLoader()

    def _resolve_assisted_worker(self, requested: str, requested_model: str) -> tuple[str, str, str | None]:
        """Resolve provider, exact model, and policy worker ID from one request."""
        key = str(requested or "auto").strip().lower() or "auto"
        model = str(requested_model or "").strip()
        if key == "auto":
            provider = os.environ.get("NEXUS_ASSIST_PROVIDER", "agy").strip().lower() or "agy"
            return provider, model, None
        snapshot = self._workforce_loader.load()
        worker = snapshot.workers.get(key)
        if worker is None:
            matches = [item for item in snapshot.workers.values() if item.model == key]
            if len(matches) == 1:
                worker = matches[0]
            elif key not in ONLINE_CLI_SPEC_REGISTRY and key not in {"mimo", "ollama"}:
                raise GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        if worker is not None:
            if worker.state in NON_ADMISSIBLE_STATES:
                raise GatewayInputError(f"ASSIST_MODEL_NOT_ADMISSIBLE:{worker.worker_id}")
            if model and model != worker.model:
                raise GatewayInputError("ASSIST_MODEL_IDENTITY_MISMATCH")
            return worker.provider, worker.model, worker.worker_id
        return key, model, None

    @staticmethod
    def tool_specs() -> list[dict[str, Any]]:
        return [
            {
                "name": "nexus_gateway_status",
                "description": "Read the single gateway identity, manifest, route stages, and lifecycle counts.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_workspace_snapshot",
                "description": "Read the canonical checkout snapshot without creating state or a Target.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_read",
                "description": "Read a bounded UTF-8 file inside the canonical checkout.",
                "inputSchema": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 1, "default": 1},
                        "max_lines": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
                    },
                },
            },
            {
                "name": "nexus_search",
                "description": "Search bounded literal text inside one canonical relative path.",
                "inputSchema": {
                    "type": "object",
                    "required": ["pattern"],
                    "properties": {
                        "pattern": {"type": "string", "maxLength": 200},
                        "path": {"type": "string", "default": "."},
                    },
                },
            },
            {
                "name": "nexus_git_diff",
                "description": "Read a bounded canonical diff; no arbitrary Git flags are accepted.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "base_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "staged": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "nexus_task_run",
                "description": "Route one bounded task through CapabilityPlanner and the governed lifecycle.",
                "inputSchema": {
                    "type": "object",
                    "required": ["what", "why", "allowed_files"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "what": {"type": "string"},
                        "why": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "execution_preference": {"type": "string", "enum": ["auto", "DIRECT_CANONICAL", "ASSISTED_CANONICAL", "ISOLATED_TARGET"], "default": "auto"},
                        "preferred_worker": {"type": "string", "default": "auto"},
                        "preferred_model": {"type": "string", "default": ""},
                        "task_card_path": {"type": "string"},
                        "task_card_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "idempotency_key": {"type": "string", "maxLength": 256},
                        "apply": {"type": "boolean", "default": True},
                    },
                },
            },
            {
                "name": "nexus_task_status",
                "description": "Read one durable task's status and next action.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_wait",
                "description": "Poll one bounded lifecycle task until attention, terminal, or timeout.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 60, "default": 10},
                        "poll_interval_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 5, "default": 0.25},
                    },
                },
            },
            {
                "name": "nexus_task_finish",
                "description": "Finish a Direct receipt or owner-finish an exact isolated Candidate binding.",
                "inputSchema": {
                    "type": "object",
                    "required": ["execution_lane"],
                    "properties": {
                        "execution_lane": {"type": "string", "enum": ["DIRECT_CANONICAL", "ISOLATED_TARGET"]},
                        "request": {"type": "object"},
                        "base_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "controller_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "expected_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "task_id": {"type": "string"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
            {
                "name": "nexus_task_cancel",
                "description": "Cancel one non-running lifecycle task through formal cleanup authority.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
        ]

    @staticmethod
    def _success(request_id: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}], "structuredContent": dict(payload), "isError": False}}

    @staticmethod
    def _error(request_id: Any, error: Exception | str) -> dict[str, Any]:
        payload = {"schema": "nexus.mcp_gateway_error.v1", "error": str(error)}
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "structuredContent": payload, "isError": True}}

    def _gateway_status(self) -> dict[str, Any]:
        lifecycle = self.service.lifecycle_status()
        return {
            "schema": "nexus.mcp_gateway_status.v1",
            "server": GATEWAY_NAME,
            "version": GATEWAY_VERSION,
            "tool_manifest_revision": TOOL_MANIFEST_REVISION,
            "tool_count": len(PUBLIC_TOOL_NAMES),
            "route_authority": "CapabilityPlanner",
            "execution_lanes": ["DIRECT_CANONICAL", "ASSISTED_CANONICAL", "ISOLATED_TARGET"],
            "canonical_repo_root": str(CANONICAL_SOURCE_ROOT),
            "lifecycle": lifecycle,
        }

    def _workspace_snapshot(self) -> dict[str, Any]:
        status = _git("status", "--porcelain=v1")
        branch = _git("branch", "--show-current").strip()
        head = _git("rev-parse", "HEAD").strip()
        worktree_lines = _git("worktree", "list", "--porcelain").splitlines()
        worktrees = [line.removeprefix("worktree ") for line in worktree_lines if line.startswith("worktree ")]
        actionable = self.service.list_actionable_tasks()
        return {
            "schema": "nexus.workspace_snapshot.v1",
            "root": str(CANONICAL_SOURCE_ROOT),
            "branch": branch,
            "head": head,
            "clean": not bool(status.strip()),
            "registered_worktrees": worktrees,
            "registered_worktree_count": len(worktrees),
            "actionable_count": int(actionable.get("actionable_count", 0)),
            "target_root": "/Users/jameschen/Workspace/nexus-runtime-targets",
        }

    def _read(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        path = _safe_relative_path(arguments.get("path"))
        if not path.is_file():
            raise GatewayInputError("path is not a regular file")
        if path.stat().st_size > MAX_READ_BYTES:
            raise GatewayInputError(f"path exceeds {MAX_READ_BYTES} bytes")
        start = max(1, int(arguments.get("start_line", 1)))
        limit = min(1000, max(1, int(arguments.get("max_lines", 200))))
        lines = path.read_text(encoding="utf-8").splitlines()
        selected = lines[start - 1 : start - 1 + limit]
        return {"schema": "nexus.workspace_read.v1", "path": str(path.relative_to(CANONICAL_SOURCE_ROOT)), "start_line": start, "lines": selected, "truncated": start - 1 + limit < len(lines)}

    def _search(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        pattern = _text(arguments.get("pattern"), "pattern", max_length=200)
        path = _safe_relative_path(arguments.get("path", "."), "path")
        relative = str(path.relative_to(CANONICAL_SOURCE_ROOT)) or "."
        result = subprocess.run(
            ["rg", "-n", "--fixed-strings", "--no-heading", "--color", "never", "--max-count", "200", pattern, relative],
            cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, timeout=3, check=False,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip() or "search failed")
        output = result.stdout.splitlines()[:MAX_SEARCH_RESULTS]
        return {"schema": "nexus.workspace_search.v1", "pattern": pattern, "path": relative, "matches": output, "truncated": len(result.stdout.splitlines()) > MAX_SEARCH_RESULTS}

    def _diff(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        base = arguments.get("base_revision")
        if base is not None and not _SHA_RE.fullmatch(str(base)):
            raise GatewayInputError("base_revision must be an exact lowercase Git SHA")
        args = ["diff", "--no-ext-diff", "--unified=3"]
        if bool(arguments.get("staged", False)):
            args.append("--cached")
        if base:
            args.append(str(base))
        output = _bounded_text(_git(*args), "git diff")
        return {"schema": "nexus.workspace_diff.v1", "base_revision": base, "staged": bool(arguments.get("staged", False)), "diff": output}

    @staticmethod
    def _task_id(arguments: Mapping[str, Any], what: str, why: str, allowed: list[str]) -> str:
        explicit = str(arguments.get("task_id") or "").strip()
        if explicit:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", explicit):
                raise GatewayInputError("task_id must be a stable bounded slug")
            return explicit
        seed = json.dumps([what, why, sorted(allowed)], ensure_ascii=False, separators=(",", ":"))
        return "dispatch-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def _plan_route(self, *, what: str, allowed: list[str], preference: str, worker: str) -> dict[str, Any]:
        cross_module = len(allowed) > 4 or any("/" in path and path.split("/", 1)[0] in {"nexus", "scripts", "tests"} for path in allowed)
        plan = CapabilityPlanner().plan(
            task_desc=what,
            task_type="code",
            route={
                "recommended_flow": "execute",
                "mutation_requested": True,
                "route_features": {"impact_complexity": 0.8 if cross_module else 0.1, "is_cross_module_task": cross_module},
            },
        )
        planner_snapshot = plan.signal_snapshot
        if preference != "auto":
            lane = preference
            reason = "caller_explicit_preference"
        elif worker not in {"", "auto", "primary", "codex"}:
            lane = "ISOLATED_TARGET"
            reason = "delegated_worker_requires_target"
        elif plan.execution_depth == "LIGHT":
            lane = "DIRECT_CANONICAL"
            reason = "CapabilityPlanner_light_execution_depth"
        else:
            lane = "ISOLATED_TARGET"
            reason = "CapabilityPlanner_non_light_execution_depth"
        return {
            "execution_lane": lane,
            "route_reason": reason,
            "route_authority": "CapabilityPlanner",
            "planner_execution_depth": plan.execution_depth,
            "planner_routing_tier": planner_snapshot.get("routing_tier"),
            "planner_decision_id": hashlib.sha256(json.dumps(planner_snapshot, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16],
        }

    def _task_run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        dispatch_started = time.perf_counter()
        what = _text(arguments.get("what"), "what")
        why = _text(arguments.get("why"), "why")
        allowed = [str(path).strip() for path in (arguments.get("allowed_files") or []) if str(path).strip()]
        if not allowed or len(allowed) > 4:
            raise GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in allowed:
            _safe_relative_path(path, "allowed_files")
        preference = str(arguments.get("execution_preference", "auto")).strip().upper()
        if preference == "AUTO":
            preference = "auto"
        if preference not in {"auto", "DIRECT_CANONICAL", "ASSISTED_CANONICAL", "ISOLATED_TARGET"}:
            raise GatewayInputError("execution_preference is unsupported")
        worker = str(arguments.get("preferred_worker", "auto")).strip().lower() or "auto"
        requested_model = str(arguments.get("preferred_model") or "").strip()
        resolved_provider, resolved_model, resolved_worker_id = self._resolve_assisted_worker(worker, requested_model)
        task_id = self._task_id(arguments, what, why, allowed)
        route_started = time.perf_counter()
        route_worker = worker if worker == "auto" else resolved_provider
        route = self._plan_route(what=what, allowed=allowed, preference=preference, worker=route_worker)
        route["requested_worker"] = worker
        route["resolved_provider"] = resolved_provider
        if resolved_model:
            route["resolved_model"] = resolved_model
        if resolved_worker_id:
            route["resolved_worker_id"] = resolved_worker_id
        route_decision_ms = max(0, int((time.perf_counter() - route_started) * 1000))
        base = _git("rev-parse", "HEAD").strip()
        action_request = {
            "task_id": task_id,
            "what": what,
            "why": why,
            "allowed_files": allowed,
            "verifier_commands": list(arguments.get("verifier_commands") or ["git diff --check"]),
            "execution_preference": preference,
            "preferred_worker": worker,
            "preferred_model": requested_model,
            "task_card_path": arguments.get("task_card_path"),
            "task_card_hash": arguments.get("task_card_hash"),
        }
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.TASK_RUN,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=base,
            allowed_paths=allowed,
            mutation=True,
            task_card_path=arguments.get("task_card_path"),
            task_card_hash=arguments.get("task_card_hash"),
            idempotency_key=arguments.get("idempotency_key"),
            permission_profile=PermissionProfile.MUTATE_BOUNDED,
        )
        envelope = {
            "schema": "nexus.task_dispatch.v1",
            "task_id": task_id,
            "what": what,
            "why": why,
            "controller_revision": base,
            "allowed_files": allowed,
            "action": action.model_dump(mode="json"),
            **route,
        }
        def telemetry(**values: int) -> dict[str, int]:
            defaults = {
                "control_plane_ms": 0,
                "route_decision_ms": route_decision_ms,
                "context_build_ms": 0,
                "provider_start_ms": 0,
                "provider_time_ms": 0,
                "patch_validation_ms": 0,
                "verifier_time_ms": 0,
                "commit_time_ms": 0,
                "worktree_time_ms": 0,
                "cleanup_time_ms": 0,
                "total_wall_time_ms": max(0, int((time.perf_counter() - dispatch_started) * 1000)),
            }
            defaults.update(values)
            defaults["total_wall_time_ms"] = max(0, int((time.perf_counter() - dispatch_started) * 1000))
            defaults["control_plane_ms"] = max(0, defaults["total_wall_time_ms"] - defaults["provider_time_ms"])
            return defaults
        if route["execution_lane"] == "ASSISTED_CANONICAL":
            context_started = time.perf_counter()
            prompt = self._assist_prompt(what, why, allowed, list(arguments.get("verifier_commands") or ["git diff --check"]))
            context_build_ms = max(0, int((time.perf_counter() - context_started) * 1000))
            provider_start_ms = max(0, int((time.perf_counter() - dispatch_started) * 1000))
            started = time.perf_counter()
            try:
                proposal = self._model_runner(
                    prompt=prompt,
                    allowed_files=allowed,
                    provider=resolved_provider,
                    model=resolved_model,
                )
            except Exception as exc:
                return {**envelope, "status": "FINAL_BLOCK", "blocker": "ASSIST_PROVIDER_FAILED", "provider_error": str(exc), "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms), "next_action": "inspect_provider_or_retry_same_task"}
            provider_time_ms = max(0, int((time.perf_counter() - started) * 1000))
            if not proposal.get("patch"):
                return {**envelope, "status": "FINAL_BLOCK", "blocker": str(proposal.get("blocker") or "EMPTY_ASSIST_PATCH"), "provider": proposal.get("provider", "unknown"), "provider_error": str(proposal.get("error") or ""), "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms), "next_action": "inspect_provider_or_retry_same_task"}
            patch_validation_started = time.perf_counter()
            try:
                changed = self._validate_assisted_patch(str(proposal["patch"]), allowed)
            except Exception as exc:
                patch_validation_ms = max(0, int((time.perf_counter() - patch_validation_started) * 1000))
                return {**envelope, "status": "FINAL_BLOCK", "blocker": "ASSIST_PATCH_REJECTED", "error": str(exc), "provider": proposal.get("provider", "unknown"), "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms, patch_validation_ms=patch_validation_ms), "next_action": "inspect_provider_or_retry_same_task"}
            patch_validation_ms = max(0, int((time.perf_counter() - patch_validation_started) * 1000))
            if not bool(arguments.get("apply", True)):
                return {**envelope, "status": "ASSISTED_CANONICAL_PROPOSAL_READY", "provider": proposal.get("provider", "unknown"), "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms, patch_validation_ms=patch_validation_ms), "patch": str(proposal["patch"]), "changed_files": changed, "next_action": "apply_assisted_candidate"}
            request = self._canonical_request(task_id, what, why, allowed, list(arguments.get("verifier_commands") or ["git diff --check"]), base, action=action.model_dump(mode="json"))
            try:
                applied = self._apply_runner(patch=str(proposal["patch"]), request=request, provider=str(proposal.get("provider") or "agy"), provider_time_ms=provider_time_ms)
            except Exception as exc:
                return {**envelope, "status": "FINAL_BLOCK", "blocker": "ASSIST_APPLY_FAILED", "error": str(exc), "provider": proposal.get("provider", "unknown"), "telemetry": telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms, patch_validation_ms=patch_validation_ms), "next_action": "inspect_provider_or_retry_same_task"}
            applied_telemetry = dict(applied.get("telemetry") or {}) if isinstance(applied, Mapping) else {}
            applied_telemetry.update(telemetry(context_build_ms=context_build_ms, provider_start_ms=provider_start_ms, provider_time_ms=provider_time_ms, patch_validation_ms=patch_validation_ms, verifier_time_ms=int(applied_telemetry.get("verifier_time_ms", 0) or 0), commit_time_ms=int(applied_telemetry.get("commit_time_ms", 0) or 0), worktree_time_ms=int(applied_telemetry.get("worktree_time_ms", 0) or 0), cleanup_time_ms=int(applied_telemetry.get("cleanup_time_ms", 0) or 0)))
            return {**envelope, "status": "ASSISTED_CANONICAL_COMPLETED", "provider": proposal.get("provider", "unknown"), "telemetry": applied_telemetry, "changed_files": changed, "receipt": applied, "next_action": "none"}
        request = self._canonical_request(task_id, what, why, allowed, list(arguments.get("verifier_commands") or ["git diff --check"]), base, action=action.model_dump(mode="json"))
        request.update({"execution_lane": route["execution_lane"]})
        if route["execution_lane"] == "DIRECT_CANONICAL":
            request.update({"primary_agent": True, "worker": "primary"})
            return {**envelope, "status": "DIRECT_CANONICAL_READY", "telemetry": telemetry(), "next_action": "edit_canonical_checkout", "completion_surface": "nexus_task_finish", "base_sha": base, "mutation_lease": {"type": "canonical_mutation_lock", "path": "/tmp/nexus-mcp-gateway-canonical.lock", "required_for_apply": True}, "handoff": self.service.submit_task(request)}
        if not arguments.get("task_card_path") or not arguments.get("task_card_hash"):
            return {**envelope, "status": "FINAL_BLOCK", "blocker": "TASK_CARD_BINDING_REQUIRED", "telemetry": telemetry(), "next_action": "provide_task_card_path_and_hash"}
        request.update({"worker": worker if worker != "auto" else "codex", "task_card_path": arguments["task_card_path"], "task_card_hash": arguments["task_card_hash"]})
        return {**envelope, "status": "ISOLATED_TARGET_SUBMITTED", "telemetry": telemetry(), "next_action": "wait_for_task", "handoff": self.service.submit_task(request)}

    @staticmethod
    def _canonical_request(task_id: str, what: str, why: str, allowed: list[str], verifiers: list[str], base: str, *, action: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        request = {
            "task_id": task_id, "what": what, "why": why,
            "controller_revision": base, "target_base_revision": base,
            "controller_repo_root": str(CANONICAL_SOURCE_ROOT),
            "target_repo_root": f"/Users/jameschen/Workspace/nexus-runtime-targets/{task_id}",
            "target_worktree_root": "/Users/jameschen/Workspace/nexus-runtime-targets",
            "allowed_files": allowed, "verifier_commands": verifiers,
        }
        if action:
            request["action"] = dict(action)
            request["action_id"] = action.get("action_id")
            request["attempt_id"] = action.get("attempt_id")
            request["idempotency_key"] = action.get("idempotency_key")
            request["action_request_hash"] = action.get("request_hash")
        return request

    @staticmethod
    def _assist_prompt(what: str, why: str, allowed: list[str], verifiers: list[str]) -> str:
        context: list[str] = []
        for raw in allowed:
            path = _safe_relative_path(raw, "allowed_files")
            if path.is_file() and path.stat().st_size <= 128 * 1024:
                context.append(f"FILE {raw}\n{path.read_text(encoding='utf-8')}\nEND FILE")
        return (
            "You are a bounded patch proposer. Use plan/read-only mode. Do not edit files, run tools, or commit. "
            "Return only JSON matching the requested schema, with a unified diff in patch. "
            f"WHAT: {what}\nWHY: {why}\nALLOWED FILES: {', '.join(allowed)}\nVERIFIERS: {verifiers}\n" + "\n".join(context)
        )

    @staticmethod
    def _run_agy_plan(*, prompt: str, allowed_files: list[str], provider: str, model: str = "") -> dict[str, Any]:
        """Run any registered assisted provider with one bounded JSON contract.

        The historical name is retained for compatibility, but the provider
        edge is no longer hard-coded to Agy. Unknown providers fail closed;
        registered providers still require an installed executable and return
        parser/transport failures as non-success receipts.
        """
        requested = str(provider or "auto").strip().lower() or "auto"
        if requested == "auto":
            requested = os.environ.get("NEXUS_ASSIST_PROVIDER", "agy").strip().lower() or "agy"
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(requested)
        if metadata is None:
            return {"provider": requested, "blocker": "ASSIST_PROVIDER_NOT_REGISTERED"}
        binary_env = metadata.get("binary_env", "")
        configured = os.environ.get(binary_env, "").strip() if binary_env else ""
        executable = configured or shutil.which(metadata.get("binary_name", requested))
        if not executable or not Path(executable).is_file():
            return {"provider": requested, "blocker": "ASSIST_PROVIDER_UNAVAILABLE"}
        schema = json.dumps({"type": "object", "required": ["patch"], "properties": {"patch": {"type": "string"}, "summary": {"type": "string"}, "tests": {"type": "array", "items": {"type": "string"}}}}, separators=(",", ":"))
        selected_model = str(model or os.environ.get("NEXUS_ASSIST_MODEL", "") or metadata.get("default_model", "")).strip()
        if requested == "agy":
            command = [executable, "--mode", "plan", "--sandbox", "--output-format", "json", "--json-schema", schema, "--effort", "low"]
            if selected_model:
                command.extend(["--model", selected_model])
            command.extend(["--print-timeout", "25s", "--prompt", prompt])
        elif requested == "cline":
            # Cline's JSON mode is non-interactive; yolo is restricted to the
            # bounded canonical apply path or an isolated Target by the caller.
            command = [executable, "--json", "--yolo", "--model", selected_model or "glm-5.2", prompt]
        elif requested == "gemini":
            command = [executable, "--skip-trust", "--approval-mode", "auto_edit", "-m", selected_model, "-p", prompt, "--output-format", "json"]
        elif requested == "opencode":
            command = [executable, "run", "--model", selected_model, prompt]
        elif requested == "codex":
            command = [executable, "exec", "--json", "--full-auto", "-m", selected_model, prompt]
        elif requested == "mimo":
            command = [executable, "run", "--model", selected_model, prompt]
        elif requested == "ollama":
            command = [executable, "run", selected_model, prompt]
        else:
            command = [executable, "--model", selected_model, "--prompt", prompt]
        result = subprocess.run(command, cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0:
            return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_FAILED", "error": result.stderr.strip()[-1000:]}
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = None
            for line in reversed(result.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    payload = candidate
                    break
            if payload is None:
                return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_MALFORMED_OUTPUT"}
        if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
            payload = payload["result"]
        if not isinstance(payload, dict):
            return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_MALFORMED_OUTPUT"}
        payload["provider"] = requested
        payload["model"] = selected_model
        return payload

    @staticmethod
    def _validate_assisted_patch(patch: str, allowed: list[str]) -> list[str]:
        if not patch.startswith("diff --git "):
            raise GatewayInputError("assist output must begin with diff --git")
        changed: list[str] = []
        for line in patch.splitlines():
            if line.startswith("+++ b/"):
                path = line[6:]
                _safe_relative_path(path, "assist patch")
                changed.append(path)
            if line.startswith("+++ /dev/null"):
                raise GatewayInputError("assist deletions are forbidden")
        changed = sorted(set(changed))
        if not changed:
            raise GatewayInputError("assist patch has no changed files")
        for path in changed:
            if not any(path == boundary or boundary.endswith("/") and path.startswith(boundary) for boundary in allowed):
                raise GatewayInputError(f"assist patch changed file outside allowed_files: {path}")
        check = subprocess.run(["git", "apply", "--check", "--binary", "--whitespace=nowarn", "-"], cwd=CANONICAL_SOURCE_ROOT, input=patch, capture_output=True, text=True, timeout=5, check=False)
        if check.returncode != 0:
            raise GatewayInputError(check.stderr.strip() or "assist patch does not apply cleanly")
        return changed

    def _apply_assisted_patch(self, *, patch: str, request: Mapping[str, Any], provider: str, provider_time_ms: int) -> dict[str, Any]:
        apply_started = time.perf_counter()
        lock_path = Path("/tmp/nexus-mcp-gateway-canonical.lock")
        with lock_path.open("w", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            if _git("status", "--porcelain=v1").strip():
                raise RuntimeError("canonical checkout must be clean")
            base = _git("rev-parse", "HEAD").strip()
            if base != request["controller_revision"]:
                raise RuntimeError("canonical revision drift")
            changed = self._validate_assisted_patch(patch, list(request["allowed_files"]))
            applied = False
            try:
                apply_result = subprocess.run(["git", "apply", "--binary", "--whitespace=nowarn", "-"], cwd=CANONICAL_SOURCE_ROOT, input=patch, capture_output=True, text=True, timeout=10, check=False)
                if apply_result.returncode != 0:
                    raise RuntimeError(apply_result.stderr.strip() or "assist patch apply failed")
                applied = True
                changed_after = _git("diff", "--name-only").splitlines()
                if sorted(changed_after) != changed or _git("diff", "--diff-filter=D", "--name-only").strip():
                    raise RuntimeError("assist patch scope or deletion gate failed")
                for command in request.get("verifier_commands") or ["git diff --check"]:
                    tokens = shlex.split(str(command))
                    if not tokens or any(token in {";", "&&", "||", "|", ">", "`"} for token in tokens):
                        raise RuntimeError("verifier command is not bounded")
                    if tokens[:2] in (["git", "commit"], ["git", "push"], ["git", "merge"], ["git", "reset"], ["git", "clean"]):
                        raise RuntimeError("verifier command may not mutate lifecycle state")
                    result = subprocess.run(tokens, cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, timeout=30, check=False)
                    if result.returncode != 0:
                        raise RuntimeError(f"verifier failed: {command}: {result.stderr.strip()}")
                commit_started = time.perf_counter()
                subprocess.run(["git", "add", "--", *changed], cwd=CANONICAL_SOURCE_ROOT, check=True, capture_output=True, text=True)
                commit = subprocess.run(["git", "commit", "-m", f"feat(assist): apply bounded model patch {request['task_id']}"], cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, check=False)
                if commit.returncode != 0:
                    raise RuntimeError(commit.stderr.strip() or "assist commit failed")
                receipt = self.service.complete_direct_canonical({**dict(request), "execution_lane": "DIRECT_CANONICAL", "primary_agent": True, "worker": "primary"}, expected_commit_sha=_git("rev-parse", "HEAD").strip())
                receipt.setdefault("telemetry", {}).update({"provider_time_ms": provider_time_ms, "worktree_time_ms": 0, "commit_time_ms": max(0, int((time.perf_counter() - commit_started) * 1000)), "cleanup_time_ms": 0, "total_wall_time_ms": max(0, int((time.perf_counter() - apply_started) * 1000))})
                return receipt
            except Exception:
                if applied:
                    subprocess.run(["git", "reset", "--", *changed], cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, check=False)
                    subprocess.run(["git", "apply", "-R", "--binary", "--whitespace=nowarn", "-"], cwd=CANONICAL_SOURCE_ROOT, input=patch, capture_output=True, text=True, check=False)
                raise

    def _finish(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        lane = _text(arguments.get("execution_lane"), "execution_lane").upper()
        if lane == "DIRECT_CANONICAL":
            request = dict(arguments.get("request") or {})
            if not request:
                task_id = _text(arguments.get("task_id"), "task_id")
                base = arguments.get("base_sha") or arguments.get("controller_revision")
                if not isinstance(base, str) or not _SHA_RE.fullmatch(base):
                    raise GatewayInputError("base_sha is required for minimal Direct finish")
                allowed = [str(path).strip() for path in (arguments.get("allowed_files") or []) if str(path).strip()]
                if not allowed or len(allowed) > 4:
                    raise GatewayInputError("allowed_files is required for minimal Direct finish")
                for path in allowed:
                    _safe_relative_path(path, "allowed_files")
                request = self._canonical_request(
                    task_id,
                    "Complete bounded canonical task",
                    "Finish the prior gateway Direct handoff",
                    allowed,
                    list(arguments.get("verifier_commands") or ["git diff --check"]),
                    base,
                )
            request.setdefault("execution_lane", "DIRECT_CANONICAL")
            request.setdefault("primary_agent", True)
            request.setdefault("worker", "primary")
            return self.service.complete_direct_canonical(request, expected_commit_sha=arguments.get("expected_commit_sha"))
        if lane == "ISOLATED_TARGET":
            task_id = _text(arguments.get("task_id"), "task_id")
            fields = ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")
            values = {field: _text(arguments.get(field), field) for field in fields}
            return self.service.owner_finish(task_id, **values)
        raise GatewayInputError("execution_lane is unsupported")

    def _call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name == "nexus_gateway_status":
            return self._gateway_status()
        if name == "nexus_workspace_snapshot":
            return self._workspace_snapshot()
        if name == "nexus_read":
            return self._read(arguments)
        if name == "nexus_search":
            return self._search(arguments)
        if name == "nexus_git_diff":
            return self._diff(arguments)
        if name == "nexus_task_run":
            return self._task_run(arguments)
        if name == "nexus_task_status":
            task_id = _text(arguments.get("task_id"), "task_id")
            return self.service.get_task(task_id)
        if name == "nexus_task_wait":
            task_id = _text(arguments.get("task_id"), "task_id")
            timeout = min(60.0, max(0.0, float(arguments.get("timeout_seconds", 10.0))))
            poll = min(5.0, max(0.01, float(arguments.get("poll_interval_seconds", 0.25))))
            return self.service.wait_task(task_id, timeout_seconds=timeout, poll_interval_seconds=poll)
        if name == "nexus_task_finish":
            return self._finish(arguments)
        if name == "nexus_task_cancel":
            task_id = _text(arguments.get("task_id"), "task_id")
            return self.service.cancel_task(task_id)
        raise GatewayInputError(f"unknown public tool: {name}")

    def handle(self, request: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized" or request_id is None:
            return None
        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": GATEWAY_NAME, "version": GATEWAY_VERSION, "toolManifestRevision": TOOL_MANIFEST_REVISION},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tool_specs()}}
        if method == "tools/call":
            params = request.get("params") or {}
            try:
                return self._success(request_id, self._call_tool(str(params.get("name", "")), params.get("arguments") or {}))
            except Exception as exc:
                return self._error(request_id, exc)
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}

    def serve(self, input_stream, output_stream) -> None:
        for line in input_stream:
            if not line.strip():
                continue
            response = self.handle(json.loads(line))
            if response is not None:
                output_stream.write(json.dumps(response, sort_keys=True, ensure_ascii=False) + "\n")
                output_stream.flush()
