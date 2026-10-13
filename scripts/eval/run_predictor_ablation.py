#!/usr/bin/env python3
"""Predictor ablation: latent_predictor_v20 and lewm_predictor on / off.

Four arms, memory off in all of them:

    both_on     NEXUS_LATENT_PREDICTOR=on   NEXUS_LEWM_PREDICTOR=on
    latent_off  NEXUS_LATENT_PREDICTOR=off  NEXUS_LEWM_PREDICTOR=on
    lewm_off    NEXUS_LATENT_PREDICTOR=on   NEXUS_LEWM_PREDICTOR=off
    both_off    NEXUS_LATENT_PREDICTOR=off  NEXUS_LEWM_PREDICTOR=off   (baseline)

Two measurements per (arm, task):

1. The local-heal attempt, using the harness helpers of run_memory_ab_v1 (imported,
   not modified). The predictors are not wired into local heal, so this measures
   whether flipping the switches changes anything there, and the process ledger
   records how many times a predictor was consulted on that path.
2. A decision-site probe. The predictors sit in the coordinator preflight
   (ForecastGateService), the ASH selector and RepairAttemptService, which local
   heal never calls. The probe feeds each fixture's problem statement through those
   three sites with the real predictors, with no model call, and counts
   ``consulted`` and ``changed_decision`` from the ``predictor_influence`` entries.

Rows and scorecard go to artifacts/runtime/predictor_ablation/<ts>/ (untracked).
Scoring reuses nexus_learning.effectiveness_measurement. Its paired helper pairs
``memory_on`` with ``memory_off`` rows, so each non-baseline arm is relabelled
``memory_on`` and the baseline ``memory_off`` for one comparison. Memory is off in
every arm; the label is only the pairing slot.

Never starts a model. The local-heal phase needs the Ollama endpoint (the SSH tunnel
to the M5); if it is down, use --probe-only or the run exits with PREFLIGHT_FAILED.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
for entry in (str(REPO_ROOT), str(EVAL_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import run_memory_ab_v1 as harness  # noqa: E402
from nexus_learning.effectiveness_measurement import (  # noqa: E402
    compare_workflows_at_required_quality,
    normalize_attempt_row,
    paired_memory_uplift,
    replay_scorecard,
)

from nexus.learning import predictor_toggle as toggle  # noqa: E402

TASKS_V3 = EVAL_DIR / "memory_ab_tasks_v3"
TASKS_V1 = EVAL_DIR / "memory_ab_tasks_v1"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "runtime" / "predictor_ablation"
DEFAULT_MODEL = "incoai/Qwen3.6-35B-A3B-Splash"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
BASELINE_ARM = "both_off"
EXIT_PREFLIGHT = harness.EXIT_PREFLIGHT

# arm -> (latent switch, lewm switch)
PREDICTOR_ARMS: dict[str, tuple[str, str]] = {
    "both_on": ("on", "on"),
    "latent_off": ("off", "on"),
    "lewm_off": ("on", "off"),
    "both_off": ("off", "off"),
}
PREDICTORS = (toggle.LATENT_PREDICTOR, toggle.LEWM_PREDICTOR)


def workflow_name(arm: str) -> str:
    return f"predictors_{arm}"


@contextlib.contextmanager
def arm_env(arm: str) -> Iterator[None]:
    latent, lewm = PREDICTOR_ARMS[arm]
    names = (toggle.env_name(toggle.LATENT_PREDICTOR), toggle.env_name(toggle.LEWM_PREDICTOR))
    saved = {name: os.environ.get(name) for name in names}
    os.environ[names[0]] = latent
    os.environ[names[1]] = lewm
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class _NullStateIO:
    """The probe must not write run state."""

    def save_global_state(self, state: Any) -> None:
        return None


def probe_decision_sites(task: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Run one fixture through the three predictor sites. No model call."""
    from nexus.core.gate_evaluator import GateEvaluator
    from nexus.core.state_contracts import NexusState
    from nexus.engine.forecast_gate_service import ForecastGateService
    from nexus.engine.repair_attempt_service import RepairAttemptService
    from nexus.engine.self_healing_selector import get_self_healing_selector
    from nexus.learning.latent_predictor_v20 import get_latent_forecaster

    desc = str(task["problem_statement"])
    toggle.drain_ledger()
    selector = get_self_healing_selector(str(root))
    latent = (
        get_latent_forecaster(str(root))
        if toggle.predictor_enabled(toggle.LATENT_PREDICTOR)
        else None
    )

    gate_state = NexusState(task_id=task["id"])
    gate_state.metadata["task_description"] = desc
    ForecastGateService(
        latent_forecaster=latent,
        gate_eval=GateEvaluator(),
        ash_selector=selector,
        state_io=_NullStateIO(),
    ).evaluate(task_id=task["id"], task_desc=desc, state=gate_state, phase="D")

    # The selector only runs on a gate rejection; rank directly so its effect is measured.
    selector.rank_strategies(desc, desc)

    lewm_state = NexusState(task_id=task["id"])
    lewm_state.metadata["sim_lewm"] = True
    lewm_state.metadata["task_description"] = desc
    RepairAttemptService(project_root=root)._run_lewm_sim(lewm_state)

    return [{**entry, "path": "decision_site_probe"} for entry in toggle.drain_ledger()]


def count_influence(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out = {name: {"entries": 0, "consulted": 0, "changed_decision": 0} for name in PREDICTORS}
    for entry in entries:
        bucket = out.get(entry.get("name"))
        if bucket is None:
            continue
        bucket["entries"] += 1
        bucket["consulted"] += 1 if entry.get("consulted") else 0
        bucket["changed_decision"] += 1 if entry.get("changed_decision") else 0
    return out


def sum_influence(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return count_influence([e for r in rows for e in r.get("predictor_influence", [])])


def _decorate(row: dict[str, Any], arm: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    row["workflow"] = workflow_name(arm)
    row["predictor_arm"] = arm
    row["predictor_switches"] = dict(zip(("latent", "lewm"), PREDICTOR_ARMS[arm], strict=True))
    row["predictor_influence"] = entries
    row["predictor_counts"] = count_influence(entries)
    return row


def run_arm_task(
    task: dict[str, Any],
    arm: str,
    *,
    run_id: str,
    run_root: Path,
    model: str,
    patch_timeout: int,
    git_rev: str,
    git_tree: str,
    python: str,
    state_root: Path,
    local_heal: bool = True,
) -> dict[str, Any]:
    with arm_env(arm):
        toggle.drain_ledger()
        if local_heal:
            row = harness.run_attempt(
                task,
                "off",  # memory off in every arm
                run_id=f"{run_id}-{arm}",
                run_root=run_root / arm,
                model=model,
                patch_timeout=patch_timeout,
                git_rev=git_rev,
                git_tree=git_tree,
                python=python,
                state_root=state_root,
            )
        else:
            row = {"task_id": task["id"], "task_fingerprint": task["fingerprint"]}
        heal_entries = [{**e, "path": "local_heal"} for e in toggle.drain_ledger()]
        probe_entries = probe_decision_sites(task, REPO_ROOT)
    return _decorate(row, arm, heal_entries + probe_entries)


def _pairing_rows(rows: list[dict[str, Any]], arm: str) -> list[dict[str, Any]]:
    """Baseline rows as memory_off and ``arm`` rows as memory_on, for the paired helper."""
    out = []
    for row in rows:
        if row["predictor_arm"] not in {arm, BASELINE_ARM}:
            continue
        clone = copy.deepcopy(row)
        clone["memory_arm"] = "memory_on" if row["predictor_arm"] == arm else "memory_off"
        out.append(clone)
    return out


def build_scorecard(
    rows: list[dict[str, Any]], task_count: int, model: str, *, probe_only: bool
) -> dict[str, Any]:
    scorecard: dict[str, Any] = {
        "schema": "nexus.predictor_ablation.scorecard.v1",
        "model": model,
        "task_count": task_count,
        "arms": list(PREDICTOR_ARMS),
        "baseline_arm": BASELINE_ARM,
        "memory_enabled_in_all_arms": False,
        "local_heal_executed": not probe_only,
        "predictor_influence": {
            arm: sum_influence([r for r in rows if r["predictor_arm"] == arm])
            for arm in PREDICTOR_ARMS
        },
        "predictor_influence_by_path": {
            arm: {
                path: count_influence([
                    e
                    for r in rows
                    if r["predictor_arm"] == arm
                    for e in r.get("predictor_influence", [])
                    if e.get("path") == path
                ])
                for path in ("local_heal", "decision_site_probe")
            }
            for arm in PREDICTOR_ARMS
        },
        "observational_only": True,
        "claim_ceiling": "internal observational ablation on synthetic fixtures; no public, training or production claim",
    }
    if probe_only:
        return scorecard
    paired: dict[str, Any] = {}
    for arm in PREDICTOR_ARMS:
        if arm == BASELINE_ARM:
            continue
        pair = _pairing_rows(rows, arm)
        paired[arm] = {
            "pairing_note": f"memory_on slot = {arm}, memory_off slot = {BASELINE_ARM}; memory is off in both",
            "paired_uplift": paired_memory_uplift(pair),
        }
    scorecard["paired_uplift_vs_both_off"] = paired
    scorecard["replay"] = replay_scorecard([
        {**r, "memory_arm": "memory_off"} for r in copy.deepcopy(rows)
    ])["metrics"]
    scorecard["quality_gate"] = compare_workflows_at_required_quality(
        harness.build_workflow_rows(rows, model),
        required_quality_floor=0.0,
        critical_failure_ceiling=task_count,
        baseline_workflow=workflow_name(BASELINE_ARM),
    )
    scorecard["pass_counts"] = {
        arm: sum(
            1
            for r in rows
            if r["predictor_arm"] == arm and r.get("terminal_outcome") == "SUCCEEDED"
        )
        for arm in PREDICTOR_ARMS
    }
    return scorecard


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tasks-dir", type=Path, default=None, help="default: v3, fallback v1")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--arms", default=",".join(PREDICTOR_ARMS))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--task-ids", default="")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--patch-timeout", type=int, default=300)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="skip the local-heal model run; only the no-model decision-site probe",
    )
    args = parser.parse_args(argv)
    args.arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    args.task_ids = [t.strip() for t in args.task_ids.split(",") if t.strip()] or None
    if not args.arms or any(a not in PREDICTOR_ARMS for a in args.arms):
        parser.error(f"--arms must be a subset of {sorted(PREDICTOR_ARMS)}")
    if BASELINE_ARM not in args.arms:
        parser.error(f"--arms must include the baseline {BASELINE_ARM}")
    if args.tasks_dir is None:
        args.tasks_dir = TASKS_V3 if TASKS_V3.is_dir() else TASKS_V1
    args.run_id = args.run_id or harness.utc_run_id()
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tasks = harness.load_tasks(args.tasks_dir, args.limit, args.task_ids)

    if not args.probe_only:
        try:
            harness.preflight_model(args.model, OLLAMA_TAGS_URL)
        except harness.ModelUnavailable as exc:
            print(f"PREFLIGHT_FAILED: {exc}", file=sys.stderr)
            return EXIT_PREFLIGHT

    run_root = args.artifact_root / args.run_id
    if (run_root / "rows.jsonl").exists():
        print(f"run already has rows.jsonl: {run_root}; choose a new --run-id", file=sys.stderr)
        return EXIT_PREFLIGHT
    run_root.mkdir(parents=True, exist_ok=True)
    state_root = run_root / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    python = sys.executable
    git_rev = harness.git_head(REPO_ROOT)
    git_tree = harness.git_tree_head(REPO_ROOT)
    guard = None
    if not args.probe_only:
        harness.redirect_learning_state(state_root, run_root / "reports" / "local_heal")
        os.environ["NEXUS_OLLAMA_MODEL"] = args.model
        os.environ["NEXUS_PATCH_TIMEOUT_SECONDS"] = str(args.patch_timeout)
        os.environ["NEXUS_LEARNING_REFLECT_JUDGE"] = "none"
        from nexus.engine.local_model_policy import LocalModelPolicy

        LocalModelPolicy.PATCH_TIMEOUT_SECONDS = args.patch_timeout
        guard = harness.StateGuard(harness.STATE_WATCH_ROOTS)

    rows_path = run_root / "rows.jsonl"
    rows_path.touch()
    rows: list[dict[str, Any]] = []
    for arm in args.arms:
        for task in tasks:
            row = run_arm_task(
                task,
                arm,
                run_id=args.run_id,
                run_root=run_root,
                model=args.model,
                patch_timeout=args.patch_timeout,
                git_rev=git_rev,
                git_tree=git_tree,
                python=python,
                state_root=state_root,
                local_heal=not args.probe_only,
            )
            if not args.probe_only:
                normalize_attempt_row(row)
            harness.append_row(rows_path, row)
            rows.append(row)
            counts = row["predictor_counts"]
            print(
                f"[{arm}] {task['id']:32} {row.get('terminal_outcome', 'PROBE'):9} "
                + " ".join(
                    f"{n.split('_')[0]}:c{c['consulted']}/d{c['changed_decision']}"
                    for n, c in counts.items()
                ),
                flush=True,
            )

    scorecard = build_scorecard(rows, len(tasks), args.model, probe_only=args.probe_only)
    scorecard["run_id"] = args.run_id
    scorecard["tasks"] = [t["id"] for t in tasks]
    scorecard["tasks_dir"] = str(args.tasks_dir)
    scorecard["state_leaks"] = guard.leaks() if guard else []
    (run_root / "scorecard.json").write_text(
        json.dumps(scorecard, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(scorecard["predictor_influence"], indent=2, sort_keys=True))
    print(f"run_root: {run_root}")
    return harness.EXIT_STATE_LEAK if scorecard["state_leaks"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
