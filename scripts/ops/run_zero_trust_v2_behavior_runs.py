#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from nexus.learning.zero_trust_v2_receipts import stamp_runtime_signed_behavior_bundle


DEFAULT_PLAN = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M28_M35_EXECUTION_PLAN_2026-05-21.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUN_HOOK_2026-05-22.json")
DEFAULT_SIGNING_SECRET_PATH = Path(".nexus/reports/zero_trust_v2_behavior/.runtime_signing_secret")
REQUIRED_ENV = {
    "NEXUS_ZERO_TRUST_V2_PHYSICAL_BEHAVIOR": "1",
    "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
    "NEXUS_BENCH_SKILL_MOUNTS": "1",
    "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _slug_path(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value).strip("-") or "unknown"


def _replace_arg(command: list[str], flag: str, value: str) -> list[str]:
    updated = list(command)
    if flag in updated:
        index = updated.index(flag)
        if index + 1 < len(updated):
            updated[index + 1] = value
            return updated
    return [*updated, flag, value]


def _bundle_has_runtime_receipt_export_pass(path: str) -> bool:
    bundle_path = Path(path)
    if not bundle_path.exists():
        return False
    try:
        bundle = read_json(bundle_path)
    except Exception:
        return False
    export = bundle.get("zero_trust_v2_runtime_receipt_export")
    return isinstance(export, dict) and export.get("status") == "PASS"


def _validate_runner_env(env: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key, expected in REQUIRED_ENV.items():
        if str(env.get(key) or "") != expected:
            blockers.append(f"missing_or_invalid_env:{key}")
    if not str(env.get("NEXUS_BENCH_SKILL_MOUNT_REQUESTS") or ""):
        blockers.append("missing_env:NEXUS_BENCH_SKILL_MOUNT_REQUESTS")
    for key in env:
        lowered = str(key).lower()
        if any(token in lowered for token in ("secret", "token", "password", "key")) and key not in {
            "NEXUS_BENCH_SKILL_MOUNT_REQUESTS",
            "NEXUS_BENCH_SKILL_STATUS_REPORT",
        }:
            blockers.append(f"secret_like_env_key:{key}")
    return blockers


def _load_or_create_signing_secret() -> tuple[str, str]:
    env_secret = os.environ.get("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "").strip()
    if env_secret:
        return env_secret, "env"
    DEFAULT_SIGNING_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_SIGNING_SECRET_PATH.exists():
        DEFAULT_SIGNING_SECRET_PATH.write_text(secrets.token_hex(32), encoding="utf-8")
        DEFAULT_SIGNING_SECRET_PATH.chmod(0o600)
    return DEFAULT_SIGNING_SECRET_PATH.read_text(encoding="utf-8").strip(), "local_runtime_secret_file"


def _export_runtime_signed_receipt(
    *,
    bundle_path: str,
    run_id: str,
    capability_id: str,
    skill_id: str,
) -> dict[str, Any]:
    path = Path(bundle_path)
    if not path.exists():
        return {"status": "BLOCKED", "blockers": ["missing_evidence_bundle"]}
    secret, secret_source = _load_or_create_signing_secret()
    bundle = read_json(path)
    stamped = stamp_runtime_signed_behavior_bundle(
        bundle,
        run_id=run_id,
        capability_id=capability_id,
        skill_id=skill_id,
        secret=secret,
    )
    if stamped["status"] == "PASS":
        write_json(path, stamped["bundle"])
    return {
        "status": stamped["status"],
        "blockers": stamped.get("blockers", []),
        "bundle_path": bundle_path,
        "signing_secret_source": secret_source,
    }


def build_zero_trust_v2_behavior_run_hook(*, plan: dict[str, Any], execute: bool = False, run_index: int | None = None) -> dict[str, Any]:
    rows = []
    selected = plan.get("selected_canary_candidate") if isinstance(plan.get("selected_canary_candidate"), dict) else {}
    capability_id = str(selected.get("capability_id") or "")
    skill_id = str(selected.get("skill_id") or "")
    for item in _as_list(plan.get("m29_three_run_plan")):
        if not isinstance(item, dict):
            continue
        current_index = int(item.get("run_index") or 0)
        if run_index is not None and current_index != run_index:
            continue
        command = [str(part) for part in _as_list(item.get("command"))]
        runner_env = item.get("runner_env") if isinstance(item.get("runner_env"), dict) else {}
        blockers = _validate_runner_env(runner_env)
        if not command:
            blockers.append("missing_command")
        result = {
            "run_index": current_index,
            "run_id": str(item.get("run_id") or ""),
            "capability_id": str(item.get("capability_id") or capability_id),
            "skill_id": str(item.get("skill_id") or skill_id),
            "priority": str(item.get("priority") or ""),
            "command": command,
            "runner_env": runner_env,
            "expected_evidence_bundle": str(item.get("expected_evidence_bundle") or ""),
            "status": "BLOCKED" if blockers else ("EXECUTED" if execute else "READY"),
            "blockers": blockers,
        }
        if execute and not blockers:
            completed = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                env={**os.environ, **{str(key): str(value) for key, value in runner_env.items()}},
                text=True,
                capture_output=True,
                timeout=700,
            )
            result.update(
                {
                    "returncode": completed.returncode,
                    "stdout_tail": completed.stdout[-2000:],
                    "stderr_tail": completed.stderr[-2000:],
                    "status": "EXECUTED" if completed.returncode == 0 else "EXECUTION_FAILED",
                }
            )
            if completed.returncode != 0:
                result["blockers"].append(f"execution_failed:{completed.returncode}")
            else:
                receipt_export = _export_runtime_signed_receipt(
                    bundle_path=str(item.get("expected_evidence_bundle") or ""),
                    run_id=str(item.get("run_id") or ""),
                    capability_id=str(result.get("capability_id") or ""),
                    skill_id=str(result.get("skill_id") or ""),
                )
                result["runtime_signed_receipt_export"] = receipt_export
                if receipt_export.get("status") != "PASS":
                    result["blockers"].extend(
                        f"runtime_signed_receipt_export:{blocker}"
                        for blocker in _as_list(receipt_export.get("blockers"))
                    )
                    result["status"] = "EXECUTION_FAILED"
        rows.append(result)
    blockers = sorted({blocker for row in rows for blocker in row["blockers"]})
    return {
        "schema": "nexus.zero_trust_v2.behavior_run_hook.v1",
        "status": "PASS" if rows and not blockers else "BLOCKED",
        "created_at": datetime.now(UTC).isoformat(),
        "source_plan": str(DEFAULT_PLAN),
        "summary": {
            "run_count": len(rows),
            "ready_count": sum(1 for row in rows if row["status"] == "READY"),
            "executed_count": sum(1 for row in rows if row["status"] == "EXECUTED"),
            "blocked_count": sum(1 for row in rows if row["status"] == "BLOCKED"),
            "execute_requested": execute,
            "runtime_mutation_allowed": False,
            "promotion_credit_allowed": False,
        },
        "runs": rows,
        "blockers": blockers,
        "claim_boundary": [
            "This hook binds runner_env to each behavior run command.",
            "Dry-run validation is the default; execution requires --execute.",
            "Successful command execution is not promotion credit until receipt import passes.",
        ],
    }


def _matrix_run_plan(
    matrix: dict[str, Any],
    *,
    run_index: int | None = None,
    priority: str = "",
    capability_id: str = "",
    missing_only: bool = False,
) -> dict[str, Any]:
    selected = []
    for adapter in _as_list(matrix.get("adapters")):
        if not isinstance(adapter, dict):
            continue
        if adapter.get("status") != "READY_FOR_PHYSICAL_BEHAVIOR_RUN":
            continue
        if priority and str(adapter.get("priority") or "") != priority:
            continue
        if capability_id and str(adapter.get("capability_id") or "") != capability_id:
            continue
        selected.append(adapter)
    run_indexes = [run_index] if run_index is not None else [1, 2, 3]
    rows = []
    for adapter in selected:
        cap = str(adapter.get("capability_id") or "")
        skill = str(adapter.get("skill_id") or "")
        command = [str(part) for part in _as_list(adapter.get("command"))]
        runner_env = adapter.get("runner_env") if isinstance(adapter.get("runner_env"), dict) else {}
        for current in run_indexes:
            output_dir = f".nexus/reports/zero_trust_v2_behavior/{_slug_path(cap)}/{_slug_path(skill)}/run-{current:02d}"
            evidence_bundle = f"{output_dir}/evidence_bundle.json"
            if missing_only and _bundle_has_runtime_receipt_export_pass(evidence_bundle):
                continue
            rows.append(
                {
                    "run_index": current,
                    "run_id": f"ztv2-matrix-{cap}-{skill}-{current:02d}",
                    "capability_id": cap,
                    "skill_id": skill,
                    "command": _replace_arg(command, "--output-dir", output_dir) if command else [],
                    "runner_env": runner_env,
                    "expected_evidence_bundle": evidence_bundle,
                }
            )
    return {"selected_canary_candidate": {}, "m29_three_run_plan": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or execute Zero-Trust V2 behavior runs with bound runner env.")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--matrix", default="")
    parser.add_argument("--all-ready", action="store_true")
    parser.add_argument("--priority", default="")
    parser.add_argument("--capability-id", default="")
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--run-index", type=int)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    source = read_json(args.plan)
    if args.all_ready:
        matrix_path = args.matrix or str(DEFAULT_MATRIX)
        source = _matrix_run_plan(
            read_json(matrix_path),
            run_index=args.run_index,
            priority=args.priority,
            capability_id=args.capability_id,
            missing_only=args.missing_only,
        )
    result = build_zero_trust_v2_behavior_run_hook(
        plan=source,
        execute=args.execute,
        run_index=None if args.all_ready else args.run_index,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
