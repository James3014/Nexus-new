#!/usr/bin/env python3
"""ChatGPT connector cutover adapter for governed self-hosted delivery."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.engine.commands.self_hosted_actions import (
    get_self_hosted_service,
    run_self_hosted_list_actionable,
    run_self_hosted_submit,
    run_self_hosted_wait,
)

DIRECT_MUTATION_TOOLS = frozenset({
    "edit",
    "write",
    "nexus.edit",
    "nexus.write",
    "workspace.edit",
    "workspace.write",
    "open_workspace.edit",
    "open_workspace.write",
})
CONNECTOR_BASH_TOOL = "nexus.bash"
DEFAULT_INTEGRATION_BRANCH = "nexus/integration/self-hosted-lifecycle-closure"
TASK_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


class ChatGPTDeliveryCutoverError(RuntimeError):
    pass


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def discover_repo_root(cwd: Path | None = None) -> Path:
    base = (cwd or Path.cwd()).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=base,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ChatGPTDeliveryCutoverError("controller_repo_root must be inside a Git checkout")
    return Path(result.stdout.strip()).resolve()


def normalize_path_list(values: Sequence[str] | str | None, *, name: str) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = values.split(",")
    else:
        raw_values = values
    paths = [str(item).strip() for item in raw_values if str(item).strip()]
    if not paths:
        return []
    for path in paths:
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ChatGPTDeliveryCutoverError(f"{name} must use bounded relative paths")
    return paths


def normalize_command_list(values: Sequence[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [line.strip() for line in values.splitlines() if line.strip()]
    return [str(item).strip() for item in values if str(item).strip()]


def stable_task_id(what: str, allowed_files: Sequence[str], explicit: str | None = None) -> str:
    seed = explicit or f"{what}:{','.join(sorted(allowed_files))}"
    normalized = TASK_ID_RE.sub("-", seed.strip().lower()).strip(".-")
    if not normalized:
        raise ChatGPTDeliveryCutoverError("task_id could not be derived")
    if re.search(r"-v[0-9]+$", normalized):
        raise ChatGPTDeliveryCutoverError("task_id must be stable; use attempt_id for retries, not -vN suffixes")
    return normalized[:80]


def default_target_worktree_root(controller_repo_root: Path) -> Path:
    return controller_repo_root.resolve().parent / "nexus-runtime-targets"


def connector_tool_policy(tool_name: str) -> dict[str, Any]:
    normalized = tool_name.strip()
    blocked = normalized in DIRECT_MUTATION_TOOLS
    return {
        "schema": "nexus.chatgpt_connector_tool_policy.v1",
        "tool": normalized,
        "allowed": not blocked,
        "required_tool": CONNECTOR_BASH_TOOL if blocked else normalized,
        "reason": (
            "direct_edit_write_delivery_blocked_use_self_hosted_lifecycle"
            if blocked
            else "tool_allowed"
        ),
    }


def _state_dir_args(state_dir: str | Path | None) -> list[str]:
    return ["--state-dir", str(state_dir)] if state_dir else []


def _quote_arg(value: Any) -> str:
    text = str(value)
    if not text:
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_./:=,+@%-]+", text):
        return text
    return "'" + text.replace("'", "'\"'\"'") + "'"


def action_command_for_task(
    state: Mapping[str, Any],
    *,
    state_dir: str | Path | None = None,
    integration_branch: str = DEFAULT_INTEGRATION_BRANCH,
) -> dict[str, Any]:
    action = state.get("task_action") or {}
    recommended_tool = action.get("recommended_tool")
    task_id = action.get("task_id") or state.get("task_id")
    if not task_id:
        return {"task_id": None, "command": None, "missing": ["task_id"]}

    base = [sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted"]
    missing: list[str] = []
    if recommended_tool == "nexus_self_hosted_approve_promotion":
        candidate = action.get("candidate") or {}
        required = [
            "candidate_commit_sha",
            "candidate_tree_sha",
            "candidate_state_hash",
            "verified_receipt_hash",
        ]
        missing = [key for key in required if not candidate.get(key)]
        if missing:
            command = None
        else:
            command = [
                *base,
                "approve",
                "--task-id",
                str(task_id),
                "--candidate-commit-sha",
                str(candidate["candidate_commit_sha"]),
                "--candidate-tree-sha",
                str(candidate["candidate_tree_sha"]),
                "--candidate-state-hash",
                str(candidate["candidate_state_hash"]),
                "--verified-receipt-hash",
                str(candidate["verified_receipt_hash"]),
                *_state_dir_args(state_dir),
            ]
    elif recommended_tool == "nexus_self_hosted_integrate_approved":
        command = [
            *base,
            "integrate",
            "--task-id",
            str(task_id),
            "--integration-branch",
            integration_branch,
            *_state_dir_args(state_dir),
        ]
    elif recommended_tool == "nexus_self_hosted_wait_task":
        command = [
            *base,
            "wait",
            "--task-id",
            str(task_id),
            *_state_dir_args(state_dir),
        ]
    else:
        command = None

    return {
        "task_id": task_id,
        "connector_tool": CONNECTOR_BASH_TOOL,
        "recommended_tool": recommended_tool,
        "next_action": action.get("next_action"),
        "command": " ".join(_quote_arg(part) for part in command) if command else None,
        "missing": missing,
    }


def summarize_actionable(
    actionable: Mapping[str, Any],
    *,
    state_dir: str | Path | None = None,
    integration_branch: str = DEFAULT_INTEGRATION_BRANCH,
) -> dict[str, Any]:
    tasks = list(actionable.get("tasks") or [])
    return {
        "schema": "nexus.chatgpt_delivery_actionable.v1",
        "actionable_count": int(actionable.get("actionable_count") or len(tasks)),
        "tasks": tasks,
        "next_commands": [
            action_command_for_task(task, state_dir=state_dir, integration_branch=integration_branch)
            for task in tasks
        ],
    }


def build_request(
    *,
    what: str,
    why: str,
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str],
    controller_repo_root: Path,
    task_id: str | None = None,
    target_worktree_root: Path | None = None,
    forbidden_files: Sequence[str] | None = None,
    worker: str = "auto",
    execution_preference: str = "auto",
) -> dict[str, Any]:
    if not what.strip() or not why.strip():
        raise ChatGPTDeliveryCutoverError("what and why are required")
    allowed = normalize_path_list(allowed_files, name="allowed_files")
    if not allowed:
        raise ChatGPTDeliveryCutoverError("allowed_files is required")
    verifiers = normalize_command_list(verifier_commands)
    if not verifiers:
        raise ChatGPTDeliveryCutoverError("verifier_commands is required")
    controller = controller_repo_root.resolve()
    revision = _run_git(controller, "rev-parse", "HEAD")
    normalized_task_id = stable_task_id(what, allowed, explicit=task_id)
    requested_preference = str(execution_preference or "auto").strip().upper()
    if requested_preference == "AUTO":
        requested_preference = "auto"
    if requested_preference not in {"auto", "DIRECT_CANONICAL", "ISOLATED_TARGET"}:
        raise ChatGPTDeliveryCutoverError("execution_preference is unsupported")
    normalized_worker = str(worker or "auto").strip().lower() or "auto"
    if normalized_worker not in {"auto", "codex", "primary", "agy", "gemini", "opencode", "mimo", "ollama"}:
        raise ChatGPTDeliveryCutoverError("worker is unsupported")
    # Automatic and delegated delivery is governed through an isolated Target.
    # Direct canonical mutation remains only an explicit primary-agent choice.
    if requested_preference == "DIRECT_CANONICAL" and normalized_worker != "primary":
        raise ChatGPTDeliveryCutoverError(
            "DIRECT_CANONICAL requires explicit primary worker authority"
        )
    direct = requested_preference == "DIRECT_CANONICAL"
    execution_lane = "DIRECT_CANONICAL" if direct else "ISOLATED_TARGET"
    # The service owns Target derivation.  Keep this compatibility field only
    # for the governed isolated request and always derive the canonical root.
    target_root = default_target_worktree_root(controller).resolve()
    request = {
        "task_id": normalized_task_id,
        "what": what.strip(),
        "why": why.strip(),
        "controller_revision": revision,
        "target_base_revision": revision,
        "controller_repo_root": str(controller),
        "allowed_files": allowed,
        "forbidden_files": normalize_path_list(forbidden_files, name="forbidden_files"),
        "verifier_commands": verifiers,
        "worker": "codex" if direct else normalized_worker,
        "execution_lane": execution_lane,
        "primary_agent": direct,
        "delivery_channel": "chatgpt_connector_nexus_bash",
        "execution_preference": requested_preference,
    }
    if not direct:
        request.update({
            "target_repo_root": str(target_root / normalized_task_id),
            "target_worktree_root": str(target_root),
        })
    return request


def run_delivery_cutover(
    *,
    what: str,
    why: str,
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str],
    forbidden_files: Sequence[str] | None = None,
    task_id: str | None = None,
    controller_repo_root: Path | None = None,
    target_worktree_root: Path | None = None,
    state_dir: str | Path | None = None,
    worker: str = "auto",
    execution_preference: str = "auto",
    timeout_seconds: float = 10.0,
    poll_interval_seconds: float = 0.25,
    service: Any | None = None,
) -> dict[str, Any]:
    service_obj = service or get_self_hosted_service(state_dir=state_dir)
    controller = (controller_repo_root or discover_repo_root()).resolve()
    request = build_request(
        what=what,
        why=why,
        allowed_files=allowed_files,
        forbidden_files=forbidden_files,
        verifier_commands=verifier_commands,
        controller_repo_root=controller,
        task_id=task_id,
        target_worktree_root=target_worktree_root,
        worker=worker,
        execution_preference=execution_preference,
    )
    direct = request["execution_lane"] == "DIRECT_CANONICAL"
    if not direct:
        before = run_self_hosted_list_actionable(state_dir=state_dir, service=service_obj)
        actionable_before = summarize_actionable(before, state_dir=state_dir)
        if actionable_before["actionable_count"] > 0:
            return {
                "schema": "nexus.chatgpt_delivery_cutover.v1",
                "status": "ACTION_REQUIRED",
                "submitted": False,
                "submission_blocked": True,
                "blocker": "existing_actionable_self_hosted_work",
                "connector_tool": CONNECTOR_BASH_TOOL,
                "execution_lane": request["execution_lane"],
                "actionable": actionable_before,
            }
    submitted = run_self_hosted_submit(request, state_dir=state_dir, service=service_obj)
    if direct:
        return {
            "schema": "nexus.chatgpt_delivery_cutover.v1",
            "status": submitted.get("status", "DIRECT_CANONICAL_READY"),
            "submitted": True,
            "submission_blocked": False,
            "connector_tool": CONNECTOR_BASH_TOOL,
            "execution_lane": "DIRECT_CANONICAL",
            "completion_surface": "nexus_task_finish",
            "next_action": "edit_canonical_checkout",
            "request": request,
            "submitted_state": submitted,
            "actionable": {"actionable_count": 0, "tasks": []},
        }
    waited = run_self_hosted_wait(
        request["task_id"],
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        state_dir=state_dir,
        service=service_obj,
    )
    after = run_self_hosted_list_actionable(state_dir=state_dir, service=service_obj)
    return {
        "schema": "nexus.chatgpt_delivery_cutover.v1",
        "status": (waited or submitted).get("task_action", {}).get("action_state", (waited or submitted).get("status")),
        "submitted": True,
        "submission_blocked": False,
        "connector_tool": CONNECTOR_BASH_TOOL,
        "execution_lane": request["execution_lane"],
        "managed_target": {
            "target_worktree_root": request["target_worktree_root"],
            "target_repo_root": request["target_repo_root"],
        },
        "request": request,
        "submitted_state": submitted,
        "waited_state": waited,
        "actionable": summarize_actionable(after, state_dir=state_dir),
    }


def _print_json(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChatGPT connector governed delivery adapter")
    sub = parser.add_subparsers(dest="command", required=True)

    guard = sub.add_parser("guard-tool", help="Fail closed for direct connector mutation tools")
    guard.add_argument("--tool", required=True)

    actionable = sub.add_parser("actionable", help="List approval or integration work")
    actionable.add_argument("--state-dir")

    launch = sub.add_parser("launch", help="Submit one governed self-hosted lifecycle task")
    launch.add_argument("--what", required=True)
    launch.add_argument("--why", required=True)
    launch.add_argument("--task-id")
    launch.add_argument("--allowed-files", required=True)
    launch.add_argument("--forbidden-files", default="")
    launch.add_argument("--verifier-command", action="append", default=[])
    launch.add_argument("--controller-repo-root")
    launch.add_argument("--target-worktree-root")
    launch.add_argument("--state-dir")
    launch.add_argument("--worker", default="auto")
    launch.add_argument("--execution-preference", choices=["auto", "DIRECT_CANONICAL", "ISOLATED_TARGET"], default="auto")
    launch.add_argument("--timeout", type=float, default=10.0)
    launch.add_argument("--poll-interval", type=float, default=0.25)
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        if args.command == "guard-tool":
            policy = connector_tool_policy(args.tool)
            _print_json(policy)
            return 0 if policy["allowed"] else 2
        if args.command == "actionable":
            actionable = run_self_hosted_list_actionable(state_dir=args.state_dir)
            _print_json(summarize_actionable(actionable, state_dir=args.state_dir))
            return 0
        if args.command == "launch":
            payload = run_delivery_cutover(
                what=args.what,
                why=args.why,
                task_id=args.task_id,
                allowed_files=normalize_path_list(args.allowed_files, name="allowed_files"),
                forbidden_files=normalize_path_list(args.forbidden_files, name="forbidden_files"),
                verifier_commands=args.verifier_command,
                controller_repo_root=Path(args.controller_repo_root).resolve() if args.controller_repo_root else None,
                target_worktree_root=Path(args.target_worktree_root).resolve() if args.target_worktree_root else None,
                state_dir=args.state_dir,
                worker=args.worker,
                execution_preference=args.execution_preference,
                timeout_seconds=args.timeout,
                poll_interval_seconds=args.poll_interval,
            )
            _print_json(payload)
            return 0 if not payload.get("submission_blocked") else 3
    except ChatGPTDeliveryCutoverError as exc:
        _print_json({"schema": "nexus.chatgpt_delivery_cutover_error.v1", "status": "FINAL_BLOCK", "error": str(exc)})
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
