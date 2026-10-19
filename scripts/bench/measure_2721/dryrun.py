"""Zero-model dry run: prove every arm receives identical task inputs.

Runs BARE (``FakeProvider``: no model call), NOOP and NEXUS (``FakeGateway``
transport: no Gateway, no worker) on the given manifest, then diffs the
captured inputs.  The check is verbatim: the same what / why / scope /
verifiers / base tree / base prompt bytes for every arm, and the NEXUS arm's
P1 ``nexus_worker_candidate`` arguments rendered with the Gateway's own
worker-prompt template must equal the BARE prompt.

Exit status 0 only when every check passes.  Output: ``symmetry_report.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.arms import load_manifest, run_bare, run_noop
from scripts.bench.measure_2721.common import read_jsonl, sha256_text, write_json
from scripts.bench.measure_2721.fakes import FakeGateway
from scripts.bench.measure_2721.nexus_driver import (
    EXTERNAL_TARGET_FIELD,
    GatewayClient,
    NexusArmDriver,
)
from scripts.bench.measure_2721.providers import FakeProvider
from scripts.bench.measure_2721.task_text import render_worker_prompt

SHARED_FIELDS = ("what", "why", "allowed_files", "verifier_commands", "base_commit", "base_tree_sha",
                 "text_sha256", "base_prompt", "base_prompt_sha256", "task_id", "repeat", "agy_run_settings")


def real_gateway_prompt_template():
    """``SelfHostedTaskService._prompt`` or None when Nexus is not importable."""
    try:
        from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    except Exception:  # pragma: no cover - outside a Nexus venv
        return None
    return SelfHostedTaskService._prompt


def gateway_rendered_prompt(worker_args: Mapping[str, Any]) -> str:
    """The base prompt the Gateway worker would build from these P1 arguments.

    Uses the real ``SelfHostedTaskService._prompt`` when Nexus is importable,
    else the harness copy (pinned to it by the harness tests).
    """
    real = real_gateway_prompt_template()
    if real is None:
        return render_worker_prompt(worker_args)
    contract = SimpleNamespace(
        goal=SimpleNamespace(what=worker_args["what"], why=worker_args["why"]),
        allowed_files=list(worker_args["allowed_files"]),
        verifier_commands=list(worker_args["verifier_commands"]),
    )
    return real(contract)


def check_task(inputs: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    by_arm = {item["arm"]: item for item in inputs}
    if set(by_arm) != {"BARE", "NOOP", "NEXUS"}:
        failures.append(f"arms captured: {sorted(by_arm)}")
    reference = by_arm.get("BARE") or next(iter(by_arm.values()))
    for arm, item in by_arm.items():
        for field in SHARED_FIELDS:
            if item.get(field) != reference.get(field):
                failures.append(f"{arm}.{field} differs from BARE")
    nexus = by_arm.get("NEXUS") or {}
    worker_args = nexus.get("gateway_worker_args")
    if not worker_args:
        failures.append("NEXUS gateway_worker_args missing")
    else:
        for field in ("what", "why", "allowed_files", "verifier_commands"):
            if worker_args.get(field) != reference.get(field):
                failures.append(f"NEXUS worker_candidate.{field} differs from BARE")
        if gateway_rendered_prompt(worker_args) != reference.get("base_prompt"):
            failures.append("Gateway-rendered P1 prompt differs from the BARE prompt")
        extra = set(worker_args) - {"owner_confirmation", "task_id", "what", "why", "allowed_files",
                                    "verifier_commands", "task_card_path", "task_card_hash",
                                    EXTERNAL_TARGET_FIELD}
        if extra:
            failures.append(f"NEXUS worker_candidate carries extra fields: {sorted(extra)}")
        target = worker_args.get(EXTERNAL_TARGET_FIELD)
        if target and target.get("base_revision") != reference.get("base_commit"):
            failures.append("NEXUS external_target base differs from the task base")
    for row in rows:
        if row["arm"] in ("BARE", "NOOP") and not row["empty"]:
            failures.append(f"{row['arm']} produced a non-empty diff in a zero-model run")
        if row["arm"] in ("BARE", "NOOP") and row.get("model_calls"):
            failures.append(f"{row['arm']} reported model calls in a zero-model run")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures,
            "base_prompt_sha256": reference.get("base_prompt_sha256")}


def dry_run(manifest: Path, out: Path, *, external_target: bool = True) -> dict[str, Any]:
    tasks = load_manifest(manifest)
    provider = FakeProvider()
    gateway = FakeGateway(external_target=external_target)
    driver = NexusArmDriver(GatewayClient("http://127.0.0.1:18766", "dry-run-token", transport=gateway),
                            campaign_id="measure-2721-dryrun", goal_id="issue-2721-dryrun",
                            scope_id="dryrun", sleep=lambda _s: None)
    for task in tasks:
        run_bare(task, 1, out, provider, timeout_seconds=900.0)
        run_noop(task, 1, out)
        driver.run(task, 1, out, timeout_seconds=900.0)
    inputs = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((out / "inputs").glob("*.json"))]
    rows = list(read_jsonl(out / "rows.jsonl"))
    per_task = {
        task["task_id"]: check_task([i for i in inputs if i["task_id"] == task["task_id"]],
                                    [r for r in rows if r["task_id"] == task["task_id"]])
        for task in tasks
    }
    prompts_seen = {sha256_text(item["prompt"]) for item in provider.prompts}
    report = {
        "schema": "nexus.measure_2721.symmetry_report.v1",
        "manifest": str(manifest),
        "tasks": len(tasks),
        "model_calls": 0,
        "fake_provider_prompts": len(provider.prompts),
        "fake_provider_prompt_sha256": sorted(prompts_seen),
        "gateway_calls": [call["tool"] for call in gateway.calls],
        "prompt_template_source": (
            "nexus.SelfHostedTaskService._prompt" if real_gateway_prompt_template() else "harness_copy"
        ),
        "per_task": per_task,
        "status": "PASS" if tasks and all(item["status"] == "PASS" for item in per_task.values()) else "FAIL",
    }
    write_json(out / "symmetry_report.json", report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    report = dry_run(Path(args.manifest), Path(args.out))
    print(json.dumps({"status": report["status"], "tasks": report["tasks"],
                      "report": str(Path(args.out) / "symmetry_report.json")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
