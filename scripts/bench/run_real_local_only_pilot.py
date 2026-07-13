#!/usr/bin/env python3
"""Run real Local-only Advisor pilot tasks via LocalAssistService + Ollama.

No injected transports. Writes jsonl receipts for campaign evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus.services.local_assist_service import (  # noqa: E402
    REQUEST_SCHEMA,
    LocalAssistRequest,
    LocalAssistService,
)


def _git_head(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo), text=True
        ).strip()
    except Exception:
        return "unknown"


def _resolve_revision(raw: str, repo: Path) -> str:
    if str(raw).strip().upper() == "HEAD":
        return _git_head(repo)
    return str(raw).strip()


def load_tasks(tasks_dir: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for path in sorted(tasks_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("task_id"):
            data["_path"] = str(path)
            tasks.append(data)
    return tasks


def to_request(task: dict[str, Any], repo: Path, model: str) -> LocalAssistRequest:
    allowed = tuple(str(x) for x in (task.get("allowed_files") or []) if str(x).strip())
    evidence = tuple(str(x) for x in (task.get("evidence_refs") or []) if str(x).strip())
    if not evidence:
        evidence = (f"real_pilot:{task['task_id']}:request",)
    revision = _resolve_revision(str(task.get("workspace_revision") or "HEAD"), repo)
    model_name = str(task.get("local_model") or model).strip()
    return LocalAssistRequest(
        schema=REQUEST_SCHEMA,
        task_id=str(task["task_id"]),
        parent_task_id=str(task.get("parent_task_id") or task["task_id"]),
        workspace_root=str(repo),
        workspace_revision=revision,
        task_statement=str(task["task_statement"]),
        action="advisor",
        allowed_files=allowed,
        target_file=str(task.get("target_file") or (allowed[0] if allowed else "")),
        target_symbol=str(task.get("target_symbol") or ""),
        evidence_refs=evidence,
        time_budget=float(task.get("timeout_sec") or 180),
        requested_role="advisor",
        mutation_policy="isolated_only",
        planner_snapshot={
            "route_truth_source": "CapabilityPlanner",
            "execution_topology": "single_local_model",
            "protocol_mode": "unified_diff",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": model_name,
        },
    )


def run_one(task: dict[str, Any], repo: Path, model: str, report_dir: Path) -> dict[str, Any]:
    req = to_request(task, repo, model)
    req.validate()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"{req.task_id}.response.json"
    t0 = time.perf_counter()
    # Real Ollama path — no InjectedLocalModelProvider.
    service = LocalAssistService()
    response = service.handle(req, report_file=report_file)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    receipt: dict[str, Any] = {}
    if response.receipt_path and Path(response.receipt_path).is_file():
        receipt = json.loads(Path(response.receipt_path).read_text(encoding="utf-8"))
    usage = receipt.get("usage") if isinstance(receipt.get("usage"), dict) else {}
    input_tokens = usage.get("input_tokens") if usage else None
    output_tokens = usage.get("output_tokens") if usage else None
    # Prefer ledger/provider fields; missing → UNAVAILABLE not zero.
    row = {
        "task_id": req.task_id,
        "task_family": task.get("task_family"),
        "workspace_revision": req.workspace_revision,
        "provider": response.provider,
        "model": (response.resolved_models[0] if response.resolved_models else ""),
        "provider_call_count": int(receipt.get("provider_call_count") or 0),
        "local": {
            "invoked": bool(response.local_model_invoked),
            "output_delivered": bool(response.output_delivered),
        },
        "latency_ms": {"value": latency_ms, "quality": "LOCALLY_MEASURED"},
        "input_tokens": {
            "value": input_tokens,
            "quality": "PROVIDER_REPORTED" if input_tokens is not None else "UNAVAILABLE",
        },
        "output_tokens": {
            "value": output_tokens,
            "quality": "PROVIDER_REPORTED" if output_tokens is not None else "UNAVAILABLE",
        },
        "output_hash": str(receipt.get("output_hash") or ""),
        "evidence_refs": list(response.evidence_refs),
        "receipt_path": response.receipt_path,
        "report_path": str(report_file),
        "formal_workspace_mutated": False,
        "status": response.status,
        "fallback_reason": response.fallback_reason,
        "git_head": _git_head(repo),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "claim_boundary": {"public_claim_allowed": False, "real_local_only": True},
    }
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tasks-dir",
        default=str(ROOT / "docs/bench/local_assist/real_pilot_tasks"),
    )
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--model", default="qwen2.5-coder:7b-instruct")
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    tasks = load_tasks(Path(args.tasks_dir))
    if args.limit > 0:
        tasks = tasks[: args.limit]
    out = Path(args.out_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with out.open("w", encoding="utf-8") as fh:
        for task in tasks:
            print(f"[local-only] {task['task_id']} ...", flush=True)
            try:
                row = run_one(task, repo, args.model, Path(args.report_dir))
            except Exception as exc:  # noqa: BLE001
                row = {
                    "task_id": task.get("task_id"),
                    "status": "FAILED",
                    "error": f"{exc.__class__.__name__}:{exc}",
                    "formal_workspace_mutated": False,
                    "provider": "ollama",
                    "local": {"invoked": False, "output_delivered": False},
                    "provider_call_count": 0,
                    "git_head": _git_head(repo),
                }
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            print(
                f"  status={row.get('status')} invoked={row.get('local', {}).get('invoked')} "
                f"calls={row.get('provider_call_count')}",
                flush=True,
            )

    ok = sum(
        1
        for r in rows
        if r.get("status") == "SUCCEEDED"
        and r.get("local", {}).get("invoked")
        and r.get("local", {}).get("output_delivered")
        and int(r.get("provider_call_count") or 0) >= 1
        and r.get("provider") == "ollama"
        and r.get("formal_workspace_mutated") is False
    )
    summary = {
        "task_count": len(rows),
        "succeeded_real_local": ok,
        "required": 5,
        "pass": ok >= 5,
        "out_jsonl": str(out),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
