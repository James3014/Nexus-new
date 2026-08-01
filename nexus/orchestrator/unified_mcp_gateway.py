"""Single GPT-visible MCP gateway for bounded Nexus workspace/lifecycle actions.

The gateway deliberately exposes a small public surface.  The existing
29-action self-hosted server remains an internal lifecycle provider; callers
must not need to know its Target paths or internal action names.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.orchestrator.self_hosted_task_service import CANONICAL_SOURCE_ROOT, SelfHostedTaskService

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

    def __init__(self, service: Optional[SelfHostedTaskService] = None):
        self.service = service or SelfHostedTaskService()

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
                        "task_card_path": {"type": "string"},
                        "task_card_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
            {
                "name": "nexus_task_status",
                "description": "Read one durable task's status and next action.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
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
        task_id = self._task_id(arguments, what, why, allowed)
        route = self._plan_route(what=what, allowed=allowed, preference=preference, worker=worker)
        base = _git("rev-parse", "HEAD").strip()
        envelope = {
            "schema": "nexus.task_dispatch.v1",
            "task_id": task_id,
            "what": what,
            "why": why,
            "controller_revision": base,
            "allowed_files": allowed,
            **route,
        }
        if route["execution_lane"] == "ASSISTED_CANONICAL":
            return {**envelope, "status": "FINAL_BLOCK", "blocker": "ASSISTED_CANONICAL_NOT_IMPLEMENTED", "next_action": "implement_assisted_canonical"}
        request = {
            "task_id": task_id,
            "what": what,
            "why": why,
            "controller_revision": base,
            "target_base_revision": base,
            "controller_repo_root": str(CANONICAL_SOURCE_ROOT),
            "target_repo_root": f"/Users/jameschen/Workspace/nexus-runtime-targets/{task_id}",
            "target_worktree_root": "/Users/jameschen/Workspace/nexus-runtime-targets",
            "allowed_files": allowed,
            "verifier_commands": list(arguments.get("verifier_commands") or ["git diff --check"]),
            "execution_lane": route["execution_lane"],
        }
        if route["execution_lane"] == "DIRECT_CANONICAL":
            request.update({"primary_agent": True, "worker": "primary"})
            return {**envelope, "status": "DIRECT_CANONICAL_READY", "next_action": "edit_canonical_then_nexus_task_finish", "handoff": self.service.submit_task(request)}
        if not arguments.get("task_card_path") or not arguments.get("task_card_hash"):
            return {**envelope, "status": "FINAL_BLOCK", "blocker": "TASK_CARD_BINDING_REQUIRED", "next_action": "provide_task_card_path_and_hash"}
        request.update({"worker": worker if worker != "auto" else "codex", "task_card_path": arguments["task_card_path"], "task_card_hash": arguments["task_card_hash"]})
        return {**envelope, "status": "ISOLATED_TARGET_SUBMITTED", "next_action": "wait_for_task", "handoff": self.service.submit_task(request)}

    def _finish(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        lane = _text(arguments.get("execution_lane"), "execution_lane").upper()
        if lane == "DIRECT_CANONICAL":
            request = dict(arguments.get("request") or {})
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
