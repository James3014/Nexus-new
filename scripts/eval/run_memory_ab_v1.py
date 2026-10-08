#!/usr/bin/env python3
"""Memory-on vs memory-off local-heal A/B runner (issue #1639).

Each memory_ab_tasks_v1 fixture is repaired by the real local-heal pipeline
(Ollama) twice: first with memory off, then with memory on. Both arms share one
learning state root under <artifact_root>/<run_id>/state/, so the on arm can
retrieve lessons reflected by the off arm. Every attempt is decided by an
independent re-run of repro.py in the attempt's work dir, not by the pipeline.

Outputs under <artifact_root>/<run_id>/: rows.jsonl (one canonical row per
attempt, appended as each completes), scorecard.json, validation.json.

Exit codes: 0 ok, 2 preflight failed (model/Ollama/learning-writeback), 3 state leak.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

NEXUS_LEARNING_BRANCH_ROOT = Path("/Users/jameschen/Workspace/nexus-learning")


def _import_adoption():
    """Import nexus_learning.adoption. The installed a366cad package predates it, so fall back
    to the nexus-learning branch checkout: purge the installed nexus_learning modules and
    re-import the package from the branch so every nexus_learning import is one version."""
    try:
        from nexus_learning import adoption as module

        return module, "installed"
    except ImportError:
        if str(NEXUS_LEARNING_BRANCH_ROOT) not in sys.path:
            sys.path.insert(0, str(NEXUS_LEARNING_BRANCH_ROOT))
        for name in [m for m in sys.modules if m == "nexus_learning" or m.startswith("nexus_learning.")]:
            del sys.modules[name]
        from nexus_learning import adoption as module

        return module, "branch"


adoption, NEXUS_LEARNING_SOURCE = _import_adoption()

from nexus_learning.effectiveness_measurement import (  # noqa: E402
    compare_workflows_at_required_quality,
    normalize_attempt_row,
    replay_scorecard,
)

DEFAULT_TASKS_DIR = Path(__file__).resolve().parent / "memory_ab_tasks_v1"
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "runtime" / "memory_ab_v1"
DEFAULT_MODEL = "qwen2.5-coder:7b"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
LESSON_WRITEBACK_ENV = "NEXUS_LOCAL_HEAL_LEARNING_WRITEBACK"
DISABLED_VALUES = {"0", "false", "no", "off"}
REPRO_TIMEOUT_SECONDS = 60
FORBIDDEN_STRATEGY_IDENTITY = "none-declared-v1"
EVAL_ID = "MEMORY_AB_V1_1639"
EXIT_PREFLIGHT = 2
EXIT_STATE_LEAK = 3

# Arm name -> (workflow / nexus memory arm, memory_enabled, row memory_arm required by normalize_attempt_row)
ADOPTION_VALIDATOR = "memory_ab_v1"
ADOPTION_OWNER_REFERENCE = "James3014/Nexus-new#1639"

ARMS: dict[str, tuple[str, bool, str]] = {
    "off": ("nexus_memory_off", False, "memory_off"),
    "on": ("nexus_memory_on", True, "memory_on"),
}

# Paths whose files must not change during a run.
STATE_WATCH_ROOTS: list[Path] = [
    REPO_ROOT / ".nexus",
    Path("/Users/jameschen/Workspace/Nexus-new/.nexus/memory"),
]


class ModelUnavailable(RuntimeError):
    """Ollama is down or the requested model is not installed."""


class AttemptTimeout(BaseException):
    """Raised from SIGALRM. BaseException so pipeline-internal `except Exception` cannot swallow it."""


# ---------------------------------------------------------------- helpers

def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(str(path.relative_to(root)).encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def git_rev_parse(repo: Path, spec: str) -> str:
    proc = subprocess.run(["git", "rev-parse", spec], cwd=str(repo), capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"cannot resolve git {spec} for {repo}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_head(repo: Path) -> str:
    return git_rev_parse(repo, "HEAD")


def git_tree_head(repo: Path) -> str:
    return git_rev_parse(repo, "HEAD^{tree}")


def load_tasks(tasks_dir: Path, limit: int | None) -> list[dict[str, Any]]:
    task_dirs = sorted(p for p in tasks_dir.iterdir() if (p / "task.json").is_file())
    tasks = []
    for task_dir in task_dirs:
        meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
        meta["dir"] = task_dir
        identity = "\0".join([meta["bug_class"], meta["variant"], meta["problem_statement"]])
        meta["fingerprint"] = sha256_bytes(identity.encode("utf-8"))
        meta["fixture_tree_sha"] = hash_tree(task_dir)
        tasks.append(meta)
    if limit is not None:
        tasks = tasks[:limit]
    if not tasks:
        raise RuntimeError(f"no tasks found under {tasks_dir}")
    return tasks


def preflight_model(model: str, url: str = OLLAMA_TAGS_URL) -> None:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ModelUnavailable(f"Ollama not reachable at {url}: {exc}") from exc
    names = {str(m.get("name", "")) for m in data.get("models", [])}
    if model not in names and f"{model}:latest" not in names:
        raise ModelUnavailable(f"model {model!r} not installed in Ollama; available: {sorted(names)}")
    if os.environ.get(LESSON_WRITEBACK_ENV, "1").strip().lower() in DISABLED_VALUES:
        raise ModelUnavailable(f"{LESSON_WRITEBACK_ENV} disables learning writeback; the on arm needs it")


# ------------------------------------------------- learning state isolation

_ACTIVE_STATE_ROOT: Path | None = None
_ACTIVE_REPORTS_ROOT: Path | None = None
_REDIRECT_INSTALLED = False


def redirect_learning_state(state_root: Path, reports_root: Path | None = None) -> None:
    """Point learning state and repair/abort receipts at this run's artifact root.

    nexus/services/local_heal derives its project root from its own file location
    (Path(__file__).parents[3]) and ignores NEXUS_LEARNING_STATE_ROOT, so ledger,
    lessons, findings and closure writes would land in the worktree's .nexus/.
    This wraps those constructor defaults. Repair receipts are also refused under
    OS temp unless an explicit reports_root is injected (receipt.py documents this
    injection for operators), so the reports root is injected here. No file under
    nexus/ is modified.
    """
    global _ACTIVE_STATE_ROOT, _ACTIVE_REPORTS_ROOT, _REDIRECT_INSTALLED
    _ACTIVE_STATE_ROOT = Path(state_root).resolve()
    _ACTIVE_REPORTS_ROOT = Path(reports_root or state_root.parent / "reports" / "local_heal").resolve()
    os.environ["NEXUS_LEARNING_STATE_ROOT"] = str(_ACTIVE_STATE_ROOT)
    if _REDIRECT_INSTALLED:
        return
    from nexus.services.local_heal import learning_closure_bridge as lcb
    from nexus.services.local_heal import memory_retrieval_adapter as mra
    from nexus.services.local_heal import pipeline as pipe

    def active_root() -> Path:
        if _ACTIVE_STATE_ROOT is None:
            raise RuntimeError("learning state root is not set")
        return _ACTIVE_STATE_ROOT

    def active_reports() -> Path:
        if _ACTIVE_REPORTS_ROOT is None:
            raise RuntimeError("reports root is not set")
        return _ACTIVE_REPORTS_ROOT

    from nexus.services.local_heal import orchestrator as orch

    repair_receipt = pipe.write_repair_receipt

    def repair_receipt_redirected(ctx, *args, **kwargs):
        kwargs.setdefault("reports_root", active_reports())
        return repair_receipt(ctx, *args, **kwargs)

    def wrap_abort(original):
        def abort_receipt_redirected(*args, **kwargs):
            if kwargs.get("output_dir") is not None:
                kwargs["output_dir"] = active_reports() / Path(kwargs["output_dir"]).name
            return original(*args, **kwargs)

        return abort_receipt_redirected

    pipe.write_repair_receipt = repair_receipt_redirected
    # Both the pipeline and the orchestrator hard-wire the worktree's .nexus/reports for abort receipts.
    pipe.write_abort_receipt = wrap_abort(pipe.write_abort_receipt)
    orch.write_abort_receipt = wrap_abort(orch.write_abort_receipt)

    bridge_init = lcb.LearningClosureBridge.__init__

    def bridge_init_redirected(self, path=None, *, findings_store=None, project_root=None, enable_findings=True):
        root = Path(project_root) if project_root else active_root()
        bridge_init(
            self,
            path or root / ".nexus/reports/learn/learning_closure.jsonl",
            findings_store=findings_store,
            project_root=root,
            enable_findings=enable_findings,
        )

    lcb.LearningClosureBridge.__init__ = bridge_init_redirected

    jsonl_init = mra.LocalJsonlLessonStore.__init__

    def jsonl_init_redirected(self, path=None):
        jsonl_init(self, path or active_root() / ".nexus/reports/learn/learning_closure.jsonl")

    mra.LocalJsonlLessonStore.__init__ = jsonl_init_redirected

    for store_cls in (mra.FindingsMemoryLessonStore, mra.MemoryRepositoryLessonStore, mra.CanonicalEpisodicMemoryLessonStore):
        original = store_cls.__init__

        def store_init(self, project_root=None, *args, _orig=original, **kwargs):
            _orig(self, project_root or active_root(), *args, **kwargs)

        store_cls.__init__ = store_init
    _REDIRECT_INSTALLED = True


class StateGuard:
    """Snapshot (mtime, size) of every file under the watched roots; report changes."""

    def __init__(self, roots: list[Path]):
        self.roots = list(roots)
        self.before = self._snapshot()

    def _snapshot(self) -> dict[str, tuple[int, int]]:
        snap: dict[str, tuple[int, int]] = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if path.is_file():
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    snap[str(path)] = (st.st_mtime_ns, st.st_size)
        return snap

    def leaks(self) -> list[str]:
        after = self._snapshot()
        changed = [p for p, sig in after.items() if self.before.get(p) != sig]
        removed = [p for p in self.before if p not in after]
        return sorted(set(changed) | set(removed))


# ------------------------------------------------------- per-attempt logic

class ModelCallCounter:
    """Wraps the Ollama generate function: pins the model and counts completed calls."""

    def __init__(self, model: str, impl: Callable[..., str] | None = None):
        self.model = model
        self.impl = impl
        self.calls = 0
        self.failures = 0

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        impl = self.impl
        if impl is None:
            from benchmarking.swebench_lite.swe_local_heal import nexus_local_generate as impl  # noqa: N813
        if len(args) >= 4:
            args = (*args[:3], self.model, *args[4:])
        else:
            kwargs["model"] = self.model
        try:
            output = impl(*args, **kwargs)
        except Exception:
            self.failures += 1
            raise
        self.calls += 1
        return output


def run_pipeline(ctx: Any, generate_fn: Callable[..., str]) -> Any:
    """The real local-heal pipeline. Tests monkeypatch this function."""
    from nexus.services.local_heal.pipeline import HealPipeline

    return HealPipeline(ollama_generate_fn=generate_fn).run(ctx)


def build_ctx(task: dict[str, Any], work_dir: Path, arm: str, attempt_id: str, run_root: Path, python: str) -> Any:
    from nexus.services.local_heal.pipeline import HealContext

    nexus_arm, memory_enabled, _ = ARMS[arm]
    target = work_dir / task["target_file"]
    ctx = HealContext(
        instance_id=task["id"],
        repo_dir=work_dir,
        problem_statement=task["problem_statement"],
    )
    ctx.auto_heal_enabled = True
    ctx.python_executable = python
    ctx.repro_script = (work_dir / task["repro_file"]).read_text(encoding="utf-8")
    ctx.localized_files = [(task["target_file"], target.read_text(encoding="utf-8"))]
    # The legacy HealContext does not carry memory flags into OperationalContext
    # (to_v2 drops them). route_context.semantic_retry_seed is the supported path
    # that to_v2() applies onto the operational context.
    ctx.route_context = {
        "semantic_retry_seed": {
            "memory_enabled": memory_enabled,
            "memory_arm": nexus_arm,
            "artifact_output_root": str(run_root / "orchestrator_artifacts" / arm),
            "attempt_id": attempt_id,
            "action_id": f"{attempt_id}:action",
            "idempotency_key": f"{attempt_id}:idem",
        }
    }
    return ctx


def run_repro(work_dir: Path, repro_file: str, python: str) -> tuple[int, float, str]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [python, repro_file],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=REPRO_TIMEOUT_SECONDS,
        )
        returncode, output = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        returncode, output = 124, f"TIMEOUT after {REPRO_TIMEOUT_SECONDS}s: {exc}"
    return returncode, time.monotonic() - started, output


def read_episode(state_root: Path, task_id: str, attempt_id: str) -> dict[str, Any] | None:
    from nexus_learning.closure_effectiveness import canonical_learning_episode_path

    path = canonical_learning_episode_path(state_root)
    if not path.exists():
        return None
    match = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("task_id") == task_id and entry.get("attempt_id") == attempt_id:
            match = entry
    return match


def _unique_ids(values: Any) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return sorted(out)


def run_attempt(
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
) -> dict[str, Any]:
    nexus_arm, memory_enabled, row_arm = ARMS[arm]
    task_id = task["id"]
    work_dir = run_root / "work" / arm / task_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(task["dir"], work_dir, ignore=shutil.ignore_patterns("__pycache__"))
    attempt_id = f"{run_id}:{nexus_arm}:{task_id}"

    ctx = build_ctx(task, work_dir, arm, attempt_id, run_root, python)
    counter = ModelCallCounter(model)
    pipeline_status = "ok"
    failure_reason = ""
    ineligible: list[str] = []

    use_alarm = threading.current_thread() is threading.main_thread()

    def _on_alarm(signum: int, frame: Any) -> None:
        raise AttemptTimeout(f"attempt exceeded {patch_timeout}s")

    old_handler = signal.signal(signal.SIGALRM, _on_alarm) if use_alarm else None
    started = time.monotonic()
    try:
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, float(patch_timeout))
        run_pipeline(ctx, counter)
    except AttemptTimeout as exc:
        pipeline_status = "timeout"
        failure_reason = str(exc)
        ineligible.append("pipeline_timeout")
    except Exception as exc:
        pipeline_status = "exception"
        failure_reason = f"{type(exc).__name__}: {exc}"[:300]
        ineligible.append("pipeline_exception")
    finally:
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
    pipeline_elapsed = time.monotonic() - started

    # ctx is only synced from the operational context when the pipeline returns,
    # so the flag check is meaningful only for completed runs.
    observed_enabled = getattr(ctx, "memory_enabled", None)
    observed_arm = getattr(ctx, "memory_arm", None)
    memory_flag_applied = (
        observed_enabled is not None
        and bool(observed_enabled) == memory_enabled
        and observed_arm == nexus_arm
    )
    if pipeline_status == "ok" and not memory_flag_applied:
        ineligible.append("memory_flag_not_applied")

    # Independent verdict: re-run repro.py in the work dir.
    repro_rc, repro_elapsed, repro_output = run_repro(work_dir, task["repro_file"], python)
    output_path = work_dir / "repro_output.txt"
    output_path.write_text(repro_output, encoding="utf-8")
    terminal = "SUCCEEDED" if repro_rc == 0 else "FAILED"
    verifier_status = "pass" if repro_rc == 0 else "fail"
    receipt_path = work_dir / "verifier_receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "decided_by": "independent_repro_rerun",
                "repro_file": task["repro_file"],
                "returncode": repro_rc,
                "pipeline_status": pipeline_status,
                "pipeline_receipt_path": str(getattr(ctx, "receipt_path", "") or ""),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    episode = read_episode(state_root, task_id, attempt_id)
    retrieved = _unique_ids(episode.get("retrieved_lesson_ids") if episode else [])
    applied = _unique_ids(episode.get("applied_lesson_ids") if episode else [])
    applied = [lesson for lesson in applied if lesson in retrieved]

    # Retrieval receipt: explicit disabled receipt for the off arm, trace-backed for the on arm.
    trace = getattr(ctx, "_memory_influence_trace", None)
    trace_dict = trace.to_dict() if hasattr(trace, "to_dict") else (trace if isinstance(trace, dict) else None)
    retrieval_path = work_dir / "retrieval_receipt.json"
    retrieval_path.write_text(
        json.dumps(
            {
                "schema": "memory_ab_v1.retrieval_receipt.v1",
                "status": "retrieval_enabled" if memory_enabled else "disabled",
                "memory_arm": nexus_arm,
                "memory_enabled": memory_enabled,
                "retrieved_lesson_ids": retrieved,
                "applied_lesson_ids": applied,
                "episode_found": episode is not None,
                "memory_trace": trace_dict,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    consumption_path = work_dir / "ollama_consumption.json"
    consumption_path.write_text(
        json.dumps(
            {
                "schema": "memory_ab_v1.ollama_consumption.v1",
                "model": model,
                "model_calls": counter.calls,
                "model_call_failures": counter.failures,
                "pipeline_status": pipeline_status,
                "pipeline_wall_sec": round(pipeline_elapsed, 3),
                "repro_wall_sec": round(repro_elapsed, 3),
                "model_decisions": getattr(ctx, "model_decisions", []) or [],
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    prompt = str(getattr(ctx, "user_prompt", "") or "")
    elapsed = round(pipeline_elapsed + repro_elapsed, 3)
    row = {
        "task_fingerprint": task["fingerprint"],
        "task_id": task_id,
        "attempt_id": attempt_id,
        "attempt_index": 0,
        "action_id": f"{attempt_id}:action",
        "source_revision": git_rev,
        "source_tree": git_tree,
        "verifier_status": verifier_status,
        "verifier_artifact": str(output_path),
        "verifier_artifact_hash": sha256_file(output_path),
        "verifier_receipt": str(receipt_path),
        "memory_arm": row_arm,
        "retrieved_lesson_ids": retrieved,
        "applied_attributed_lesson_ids": applied,
        "applied_lesson_ids": applied,
        "evidence_origin": "physical",
        "evidence_refs": [f"retrieval_receipt:{retrieval_path}", f"ollama_consumption:{consumption_path}"],
        "terminal_outcome": terminal,
        "measured_elapsed_seconds": elapsed,
        "intervention_events": [],
        "intervention_count": 0,
        "forbidden_strategy_identity": FORBIDDEN_STRATEGY_IDENTITY,
        "forbidden_strategy_violation_event": False,
        "missingness_reasons": [],
        "ineligibility_reasons": sorted(set(ineligible)),
        # Extra (not required by the contract) columns for the A/B report.
        "workflow": nexus_arm,
        "workflow_revision": model,
        "nexus_memory_arm": nexus_arm,
        "memory_enabled": bool(observed_enabled),
        "memory_flag_applied": memory_flag_applied,
        "model": model,
        "run_id": run_id,
        "solve_eligible": bool(getattr(ctx, "solve_eligible", False)),
        "receipt_path": str(getattr(ctx, "receipt_path", "") or ""),
        "pipeline_status": pipeline_status,
        "failure_reason": failure_reason or ("" if repro_rc == 0 else "independent_repro_failed"),
        "repro_returncode": repro_rc,
        "wall_duration_sec": elapsed,
        "model_calls": counter.calls,
        "model_call_failures": counter.failures,
        "episode_found": episode is not None,
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")) if prompt else "",
        "work_dir": str(work_dir),
    }
    normalize_attempt_row(row)  # fail loudly if the row is not contract-valid
    return row


def build_workflow_rows(rows: list[dict[str, Any]], model: str) -> list[dict[str, Any]]:
    """One quality-workflow row per attempt for compare_workflows_at_required_quality."""
    out = []
    for row in rows:
        passed = row["terminal_outcome"] == "SUCCEEDED" and not row["ineligibility_reasons"]
        out.append(
            {
                "workflow_identity": row["workflow"],
                "workflow_revision": model,
                "task_fingerprint": row["task_fingerprint"],
                "attempt_count": 1,
                "qualified_success_count": 1 if passed else 0,
                "critical_failure_count": 0 if row["terminal_outcome"] == "SUCCEEDED" else 1,
                "semantic_failure_count": None,
                "provider_failure_count": None,
                "false_allow_count": None,
                "model_invocation_count": row["model_calls"],
                "provider_invocation_count": None,
                "fallback_count": 0,
                "token_usage": None,
                "human_intervention_count": 0,
                "wall_time_seconds": row["measured_elapsed_seconds"],
                "monetary_cost_usd": None,
                "missingness_reasons": [
                    "semantic_failure_count",
                    "provider_failure_count",
                    "false_allow_count",
                    "provider_invocation_count",
                    "token_usage",
                    "monetary_cost_usd",
                ],
                "ineligibility_reasons": list(row["ineligibility_reasons"]),
            }
        )
    return out


def build_scorecard(rows: list[dict[str, Any]], task_count: int, model: str) -> dict[str, Any]:
    scorecard = replay_scorecard(rows)
    scorecard["quality_gate"] = compare_workflows_at_required_quality(
        build_workflow_rows(rows, model),
        required_quality_floor=0.0,
        critical_failure_ceiling=task_count,
        baseline_workflow=ARMS["off"][0],
    )
    return scorecard


def build_validation(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    tasks: list[str],
    arms: list[str],
    model: str,
    state_root: Path,
    reflect_judge: str,
    leaks: list[str],
) -> dict[str, Any]:
    model_calls = sum(int(r["model_calls"]) for r in rows)
    prompts: dict[str, dict[str, str]] = {}
    for r in rows:
        prompts.setdefault(r["task_id"], {})[r["workflow"]] = r["prompt_sha256"]
    prompt_delta = any(
        v.get(ARMS["off"][0]) and v.get(ARMS["on"][0]) and v[ARMS["off"][0]] != v[ARMS["on"][0]]
        for v in prompts.values()
    )
    return {
        "eval_id": EVAL_ID,
        "run_id": run_id,
        "tasks": tasks,
        "arms": arms,
        "model": model,
        "rows": len(rows),
        "real_model_call_executed": model_calls > 0,
        "model_calls_total": model_calls,
        "synthetic_delta_measured": False,
        "public_claim_allowed": False,
        "training_export_allowed": False,
        "production_ready": False,
        "internal_only": True,
        "prompt_delta_observed": prompt_delta,
        "memory_flags_verified": all(r["memory_flag_applied"] for r in rows) if rows else False,
        "retrieved_lesson_count": sum(len(r["retrieved_lesson_ids"]) for r in rows),
        "applied_lesson_count": sum(len(r["applied_attributed_lesson_ids"]) for r in rows),
        "reflect_judge": reflect_judge,
        "state_root": str(state_root),
        "state_leaks": leaks,
        "claim_ceiling": "internal observational A/B on synthetic fixtures; no public, training or production claim",
    }


def append_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


# --------------------------------------------------------------- driver

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks-dir", type=Path, default=DEFAULT_TASKS_DIR)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--arms", default="off,on", help="comma-separated, run in this order (default off,on)")
    parser.add_argument("--limit", type=int, default=None, help="use only the first N tasks")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--patch-timeout", type=int, default=300, help="wall-clock seconds per pipeline attempt")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--reflect-judge", choices=["none", "ollama"], default="none")
    args = parser.parse_args(argv)
    args.arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if not args.arms or any(a not in ARMS for a in args.arms):
        parser.error(f"--arms must be a subset of {sorted(ARMS)}")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.patch_timeout < 1:
        parser.error("--patch-timeout must be >= 1")
    args.run_id = args.run_id or utc_run_id()
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tasks = load_tasks(args.tasks_dir, args.limit)

    try:
        preflight_model(args.model)
    except ModelUnavailable as exc:
        print(f"PREFLIGHT_FAILED: {exc}", file=sys.stderr)
        return EXIT_PREFLIGHT

    run_root = args.artifact_root / args.run_id
    if (run_root / "rows.jsonl").exists():
        print(f"run already has rows.jsonl: {run_root}; choose a new --run-id", file=sys.stderr)
        return EXIT_PREFLIGHT
    run_root.mkdir(parents=True, exist_ok=True)
    state_root = run_root / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    redirect_learning_state(state_root, run_root / "reports" / "local_heal")
    os.environ["NEXUS_OLLAMA_MODEL"] = args.model
    os.environ["NEXUS_PATCH_TIMEOUT_SECONDS"] = str(args.patch_timeout)
    os.environ["NEXUS_LEARNING_REFLECT_JUDGE"] = args.reflect_judge
    from nexus.engine.local_model_policy import LocalModelPolicy

    LocalModelPolicy.PATCH_TIMEOUT_SECONDS = args.patch_timeout

    git_rev = git_head(REPO_ROOT)
    git_tree = git_tree_head(REPO_ROOT)
    python = sys.executable
    guard = StateGuard(STATE_WATCH_ROOTS)
    rows_path = run_root / "rows.jsonl"
    rows_path.touch()

    rows: list[dict[str, Any]] = []
    for arm in args.arms:
        for task in tasks:
            row = run_attempt(
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
            )
            append_row(rows_path, row)
            rows.append(row)
            print(
                f"[{arm}] {task['id']:32} {row['terminal_outcome']:9} "
                f"pipeline={row['pipeline_status']} t={row['wall_duration_sec']}s "
                f"calls={row['model_calls']} retrieved={row['retrieved_lesson_ids']} "
                f"applied={row['applied_attributed_lesson_ids']}",
                flush=True,
            )

    leaks = guard.leaks()
    scorecard = build_scorecard(rows, len(tasks), args.model)
    (run_root / "scorecard.json").write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validation = build_validation(
        rows,
        run_id=args.run_id,
        tasks=[t["id"] for t in tasks],
        arms=args.arms,
        model=args.model,
        state_root=state_root,
        reflect_judge=args.reflect_judge,
        leaks=leaks,
    )
    (run_root / "validation.json").write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Advisory adoption decision. No state_root is passed, so nothing is persisted to a learning state.
    decision = adoption.build_adoption_from_scorecard(
        scorecard,
        source_revision=git_rev,
        runtime_identity="local_heal:" + args.model,
        required_quality_floor=0.0,
        critical_failure_ceiling=len(tasks),
        validator_identity=ADOPTION_VALIDATOR,
        owner_authority_reference=ADOPTION_OWNER_REFERENCE,
    )
    (run_root / "adoption_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print(f"adoption_decision: {decision['decision']} reasons={decision['reason_codes']} (source={NEXUS_LEARNING_SOURCE})")

    print(f"run_root: {run_root}")
    print(f"rows: {len(rows)} real_model_call_executed={validation['real_model_call_executed']}")
    if leaks:
        for path in leaks:
            print(f"STATE_LEAK: {path}")
        return EXIT_STATE_LEAK
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
