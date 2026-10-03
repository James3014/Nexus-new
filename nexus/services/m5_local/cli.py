"""CLI interface for M5 Local Assist and Local Worker bridge.

Provides simple command semantics:
  inspect           Show host hardware, runtimes, and models inventory
  assist            Execute Mode A Local Assist (read-only)
  run               Execute Mode B Local Worker (execution substrate)
  handoff           Generate a durable Local -> Online handoff packet
  status            Check resource safety and operational status
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .assist_adapter import LocalAssistService
from .contracts import (
    LocalAssistRequest,
    LocalWorkerRequest,
)
from .host_inventory import inspect_m5_host
from .telemetry import check_host_resource_safety
from .worker_adapter import LocalWorkerService


def cmd_inspect(args: argparse.Namespace) -> int:
    inventory = inspect_m5_host()
    output = asdict(inventory)
    print(json.dumps(output, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    safe, reason = check_host_resource_safety()
    status_data = {
        "host": inspect_m5_host().cpu_brand,
        "resource_safe": safe,
        "reason": reason or "Host memory and swap are within safe operating limits",
    }
    print(json.dumps(status_data, indent=2))
    return 0 if safe else 1


def cmd_assist(args: argparse.Namespace) -> int:
    hints = (
        [h.strip() for h in args.candidate_hints.split(",") if h.strip()]
        if args.candidate_hints
        else []
    )
    req = LocalAssistRequest(
        task_id=args.task_id or "task-local-assist",
        query=args.query,
        repo_path=args.repo_path,
        base_sha=args.base_sha or "",
        candidate_hints=hints,
        requested_runtime=args.runtime if not args.deterministic_only else None,
        requested_model=args.model if not args.deterministic_only else None,
        timeout_seconds=args.timeout,
        allow_inference=not args.deterministic_only,
    )
    svc = LocalAssistService()
    res = svc.execute(req)
    print(json.dumps(asdict(res), indent=2))
    return 0 if res.status == "SUCCESS" else 1


def cmd_run(args: argparse.Namespace) -> int:
    scope = [s.strip() for s in args.scope.split(",") if s.strip()] if args.scope else []
    req = LocalWorkerRequest(
        task_id=args.task_id or "task-local-worker",
        attempt_id=args.attempt_id or "att-local-1",
        operation_id=args.operation_id or "op-local-1",
        repo_path=args.repo_path,
        base_sha=args.base_sha or "",
        allowed_scope=scope,
        task_instruction=args.instruction,
        requested_runtime=args.runtime,
        requested_model=args.model,
        claim_receipt_ref=args.claim_ref,
        conflict_admission_token=args.conflict_token,
        workspace_root=args.workspace_root or "",
        write_permitted=args.allow_write,
        timeout_seconds=args.timeout,
    )
    svc = LocalWorkerService()
    res = svc.execute(req)
    print(json.dumps(asdict(res), indent=2))
    return 0 if res.status == "COMPLETED" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="m5-local",
        description="M5 Local Assist and qualified Local Worker bridge",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # inspect
    subparsers.add_parser("inspect", help="Inspect M5 hardware, runtimes, and models")

    # status
    subparsers.add_parser("status", help="Check host resource and execution safety status")

    # assist
    p_assist = subparsers.add_parser("assist", help="Execute Mode A Local Assist")
    p_assist.add_argument("--task-id", default="", help="Task identifier")
    p_assist.add_argument("--query", required=True, help="Task query or description")
    p_assist.add_argument("--repo-path", required=True, help="Path to target git repository")
    p_assist.add_argument("--base-sha", default="", help="Expected base revision SHA")
    p_assist.add_argument("--candidate-hints", default="", help="Comma-separated file path hints")
    p_assist.add_argument("--model", default="qwen36-35b-q4", help="Requested local model ID")
    p_assist.add_argument("--runtime", default="llama.cpp", help="Requested local runtime ID")
    p_assist.add_argument(
        "--deterministic-only", action="store_true", help="Force deterministic path without LLM"
    )
    p_assist.add_argument("--timeout", type=float, default=30.0, help="Timeout in seconds")

    # run
    p_run = subparsers.add_parser("run", help="Execute Mode B Local Worker substrate")
    p_run.add_argument("--task-id", default="", help="Task identifier")
    p_run.add_argument("--attempt-id", default="", help="Attempt identifier")
    p_run.add_argument("--operation-id", default="", help="Operation identifier")
    p_run.add_argument("--instruction", required=True, help="Task instruction")
    p_run.add_argument("--repo-path", required=True, help="Repository root path")
    p_run.add_argument("--base-sha", default="", help="Base revision SHA")
    p_run.add_argument("--scope", default="", help="Comma-separated allowed file paths")
    p_run.add_argument("--model", default="qwen36-35b-q4", help="Requested local model ID")
    p_run.add_argument("--runtime", default="llama.cpp", help="Requested local runtime ID")
    p_run.add_argument("--claim-ref", default=None, help="#129 claim receipt reference")
    p_run.add_argument("--conflict-token", default=None, help="#98 conflict admission token")
    p_run.add_argument("--workspace-root", default="", help="Isolated workspace root")
    p_run.add_argument(
        "--allow-write", action="store_true", help="Request write permission (requires authorities)"
    )
    p_run.add_argument("--timeout", type=float, default=60.0, help="Timeout in seconds")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        return cmd_inspect(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "assist":
        return cmd_assist(args)
    elif args.command == "run":
        return cmd_run(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
