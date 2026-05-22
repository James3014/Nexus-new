from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_SKILL_STATUS_REPORT = "docs/reports/archive/sf/2026-05-15/NEXUS_SKILL_STATUS_2026-05-15.json"
DEFAULT_OUTPUT_DIR = ".nexus/reports/zero_trust_v2_behavior"
SECRET_ENV_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "SALT")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _task_ref_from_item(item: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = item.get("task_ref")
    if isinstance(raw, Mapping):
        return raw
    raw = item.get("fresh_task_ref")
    if isinstance(raw, Mapping):
        return raw
    return {}


def build_behavior_runner_env(*, skill_id: str, status_report: str = DEFAULT_SKILL_STATUS_REPORT) -> dict[str, str]:
    return {
        "NEXUS_ZERO_TRUST_V2_PHYSICAL_BEHAVIOR": "1",
        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
        "NEXUS_BENCH_SKILL_MOUNTS": "1",
        "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
        "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps([skill_id], ensure_ascii=False),
        "NEXUS_BENCH_SKILL_STATUS_REPORT": status_report,
    }


def _model_env(*, provider: str, model: str) -> dict[str, str]:
    if provider == "codex":
        return {"NEXUS_CODEX_MODEL_NAME": model, "NEXUS_DIRECT_CODEX_MODEL": model}
    if provider == "gemini":
        return {"NEXUS_GEMINI_MODEL_NAME": model}
    return {}


def validate_behavior_runner_env(env: Mapping[str, Any]) -> dict[str, Any]:
    leaked = [
        key
        for key in env
        if any(marker in str(key).upper() for marker in SECRET_ENV_MARKERS)
        and key not in {"NEXUS_BENCH_SKILL_STATUS_REPORT"}
    ]
    return {
        "status": "PASS" if not leaked else "BLOCKED",
        "failed_security_contract_rules": [f"RUNNER_ENV_SECRET_KEY:{key}" for key in sorted(leaked)],
    }


def build_capability_ab_runner_command(
    *,
    manifest: str,
    task_id: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    provider: str = "codex",
    model: str = "gpt-5.5",
) -> list[str]:
    command = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        manifest,
        "--task-id-filter",
        task_id,
        "--max-tasks",
        "1",
        "--output-dir",
        output_dir,
        "--timeout-sec",
        "300",
        "--per-task-stop-loss-sec",
        "600",
        "--stop-loss-sec",
        "600",
        "--with-model-provider",
        provider,
        "--nexus-only",
        "--with-nexus-runner",
        "subprocess",
        "--with-llm-mode",
        "all",
        "--without-mode",
        provider,
        "--force-flow",
        "hyper_sprint",
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--llm-candidate-cap",
        "3",
        "--neutralize-history",
        "--disable-learning-loop",
        "--evidence-bundle",
    ]
    if provider == "gemini":
        command[command.index("--with-model-provider") : command.index("--with-model-provider") + 2] = [
            "--gemini-model",
            model,
        ]
        command.extend(["--with-model-provider", "gemini"])
    return command


def build_behavior_runner_adapter(
    item: Mapping[str, Any],
    *,
    status_report: str = DEFAULT_SKILL_STATUS_REPORT,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    provider: str = "codex",
    model: str = "gpt-5.5",
) -> dict[str, Any]:
    capability_id = _clean(item.get("capability_id"))
    skill_id = _clean(item.get("skill_id"))
    priority = _clean(item.get("priority"))
    task_ref = _task_ref_from_item(item)
    manifest = _clean(task_ref.get("manifest"))
    task_id = _clean(task_ref.get("task_id") or task_ref.get("id"))
    env = {
        **build_behavior_runner_env(skill_id=skill_id, status_report=status_report),
        **_model_env(provider=provider, model=model),
    }
    env_validation = validate_behavior_runner_env(env)
    failed = list(env_validation["failed_security_contract_rules"])
    command: list[str] = []
    hook_status = "PASS"
    if not skill_id:
        failed.append("MISSING_SKILL_ID")
    if not capability_id:
        failed.append("MISSING_CAPABILITY_ID")
    if not manifest or not task_id:
        failed.append("MISSING_FRESH_TASK_REF_FOR_V2_PHYSICAL_RUN")
        hook_status = "BLOCKED"
    elif not Path(manifest).exists():
        failed.append("FRESH_TASK_MANIFEST_NOT_FOUND")
        hook_status = "BLOCKED"
    if not failed:
        command = build_capability_ab_runner_command(
            manifest=manifest,
            task_id=task_id,
            output_dir=output_dir,
            provider=provider,
            model=model,
        )
    return {
        "capability_id": capability_id,
        "skill_id": skill_id,
        "priority": priority,
        "runner_kind": "capability_ab_runner",
        "model_provider": provider,
        "model_name": model,
        "hook_status": hook_status,
        "status": "READY_FOR_PHYSICAL_BEHAVIOR_RUN" if command else "BLOCKED",
        "command": command,
        "runner_env": env if env_validation["status"] == "PASS" else {},
        "task_ref": {"manifest": manifest, "task_id": task_id} if manifest or task_id else {},
        "expected_evidence_bundle": str(Path(output_dir) / "evidence_bundle.json"),
        "promotion_credit_allowed": False,
        "runtime_mutation_allowed": False,
        "public_benchmark_allowed": False,
        "failed_security_contract_rules": sorted(set(failed)),
        "claim_boundary": "This adapter only prepares a sandboxed fresh behavior run; promotion credit requires the signed V2 physical receipt.",
    }
