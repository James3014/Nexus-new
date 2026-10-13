#!/usr/bin/env python3
"""Memory-on vs memory-off local-heal A/B runner (issue #1639).

Each memory_ab_tasks_v1 fixture is repaired by the real local-heal pipeline
(Ollama) twice: first with memory off, then with memory on. Both arms share one
learning state root under <artifact_root>/<run_id>/state/, so the on arm can
retrieve lessons reflected by the off arm. Every attempt is decided by an
independent re-run of repro.py in the attempt's work dir, not by the pipeline.

Outputs under <artifact_root>/<run_id>/: rows.jsonl (one canonical row per
attempt, appended as each completes), scorecard.json, validation.json.

Armor axis (#1821): --armor off (default) runs the bare HealPipeline exactly as before.
--armor on plans the task with CapabilityPlanner and runs it through run_mainchain
(with_nexus_armor=True, local-only route, LocalAssistService -> LocalModelExecutor) at the
requested --armor-profile (default FULL). Every row and the scorecard record which capabilities
were selected and which have real invocation evidence in the receipt.

Exit codes: 0 ok, 2 preflight failed (model/Ollama/learning-writeback), 3 state leak.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

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
        for name in [
            m for m in sys.modules if m == "nexus_learning" or m.startswith("nexus_learning.")
        ]:
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

ARMOR_MODES = ("off", "on")
ARMOR_PROFILES = ("LITE", "STANDARD", "FULL")
DEFAULT_ARMOR_PROFILE = "FULL"
ARMOR_CANONICAL_CONTEXT = {"execution_world": "local_armor", "transport_ingress": "bench"}
ARMOR_PROFILE_NONE = "none"
# Capabilities whose local-path executors report invoked=True with an empty candidate pool
# (advisory stubs in the localheal_pipeline topology); they count only with candidate evidence.
STUB_PRONE_CAPABILITIES = frozenset({"ddtree", "autoreason"})
# Physical callables that are explicit skips or stubs, never real invocation evidence.
STUB_CALLABLE_MARKERS = ("explicit_skip", "stub")
ARMOR_ROW_KEYS = (
    "armor",
    "armor_profile",
    "capabilities_selected",
    "capabilities_invoked",
    "committee_invoked",
    "with_nexus_armor",
)
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


def load_tasks(
    tasks_dir: Path, limit: int | None, task_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    task_dirs = sorted(p for p in tasks_dir.iterdir() if (p / "task.json").is_file())
    if task_ids is not None:
        unknown = sorted(set(task_ids) - {p.name for p in task_dirs})
        if unknown:
            raise RuntimeError(f"unknown task ids {unknown} under {tasks_dir}")
        task_dirs = [p for p in task_dirs if p.name in set(task_ids)]
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
        raise ModelUnavailable(
            f"model {model!r} not installed in Ollama; available: {sorted(names)}"
        )
    if os.environ.get(LESSON_WRITEBACK_ENV, "1").strip().lower() in DISABLED_VALUES:
        raise ModelUnavailable(
            f"{LESSON_WRITEBACK_ENV} disables learning writeback; the on arm needs it"
        )


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
    _ACTIVE_REPORTS_ROOT = Path(
        reports_root or state_root.parent / "reports" / "local_heal"
    ).resolve()
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

    def bridge_init_redirected(
        self, path=None, *, findings_store=None, project_root=None, enable_findings=True
    ):
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

    for store_cls in (
        mra.FindingsMemoryLessonStore,
        mra.MemoryRepositoryLessonStore,
        mra.CanonicalEpisodicMemoryLessonStore,
    ):
        original = store_cls.__init__

        def store_init(self, project_root=None, *args, _orig=original, **kwargs):
            _orig(self, project_root or active_root(), *args, **kwargs)

        store_cls.__init__ = store_init

    canonical_lesson_cls = getattr(mra, "CanonicalLessonStore", None)
    if canonical_lesson_cls is not None:
        canonical_lesson_init = canonical_lesson_cls.__init__

        def canonical_lesson_init_redirected(self, *, project_root=None, path=None):
            if project_root is None and path is None:
                project_root = active_root()
            canonical_lesson_init(self, project_root=project_root, path=path)

        canonical_lesson_cls.__init__ = canonical_lesson_init_redirected
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
            from benchmarking.swebench_lite.swe_local_heal import (
                nexus_local_generate as impl,  # noqa: N813
            )
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


def build_ctx(
    task: dict[str, Any], work_dir: Path, arm: str, attempt_id: str, run_root: Path, python: str
) -> Any:
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


# ------------------------------------------------------------ armor axis


def derive_target_symbol(task: dict[str, Any], source_text: str) -> str:
    """Task-declared symbol, else the top-level function the problem statement names."""
    explicit = str(task.get("target_symbol") or "").strip()
    if explicit:
        return explicit
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return ""
    names = [
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    statement = str(task.get("problem_statement") or "")
    for name in names:
        if re.search(rf"\b{re.escape(name)}\b", statement):
            return name
    return names[0] if names else ""


@contextlib.contextmanager
def armor_environment(model: str, profile: str, armor_root: Path) -> Iterator[None]:
    """Supported authorization/placement switches for a local-model armor attempt.

    FULL uses NEXUS_FORCE_FULL_ARMOR. LITE sets NEXUS_FAST_MODE (the resolver's LITE precondition);
    STANDARD sets nothing. For LITE and STANDARD the planner's own signals still decide, so the
    observed profile is checked against the request after the attempt.
    The model endpoint is whatever NEXUS_OLLAMA_URL / 127.0.0.1:11434 resolves to (the M5 tunnel).
    """
    updates: dict[str, str | None] = {
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR": "1",
        "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY": "localheal_pipeline",
        "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL": model,
        "NEXUS_LOCAL_MODEL_NAME": model,
        "NEXUS_ARMOR_ARTIFACT_ROOT": str(armor_root),
        "NEXUS_FORCE_FULL_ARMOR": "1" if profile == "FULL" else None,
        "NEXUS_FAST_MODE": "1" if profile == "LITE" else None,
    }
    saved = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def build_armor_service(
    apply_parent: Path,
    executor_sink: dict[str, Any],
    executor_runner: Callable[..., Any] | None = None,
) -> Any:
    """LocalAssistService whose candidate isolation lives under apply_parent.

    LocalAssistService strips the executor's raw_model_metadata from its response, so the executor
    call is wrapped and the metadata (armor profile, committee, ddtree/autoreason results) is kept in
    executor_sink. executor_runner defaults to LocalModelExecutor.run; tests inject a fake.
    """
    from nexus.services.local_assist_service import LocalAssistService
    from nexus.services.local_heal.isolated_workspace_apply import run_isolated_workspace_apply
    from nexus.services.local_heal.local_model_executor import LocalModelExecutor

    apply_parent.mkdir(parents=True, exist_ok=True)
    inner = executor_runner or LocalModelExecutor.run

    def apply(request: Any) -> Any:
        return run_isolated_workspace_apply(replace(request, work_dir=str(apply_parent)))

    def recording_executor(request: Any, **kwargs: Any) -> Any:
        response = inner(request, **kwargs)
        meta = getattr(response, "raw_model_metadata", None)
        executor_sink["meta"] = dict(meta) if isinstance(meta, dict) else {}
        executor_sink["selected_capabilities"] = [str(c) for c in request.selected_capabilities]
        return response

    return LocalAssistService(executor_runner=recording_executor, apply_runner=apply)


def build_armor_snapshot(task: dict[str, Any], model: str) -> dict[str, Any]:
    """CapabilityPlanner snapshot for the local request.

    UnifiedRuntime re-plans and keeps only topology, protocol_mode and model_call_allowed from this
    snapshot, so capability selection and the armor profile signals stay planner-owned.
    """
    from nexus.services.local_assist_service import build_planner_snapshot

    snapshot = build_planner_snapshot(
        task_statement=task["problem_statement"], model=model, topology="localheal_pipeline"
    )
    snapshot.update({
        "model_call_allowed": True,
        "mutation_allowed": True,
        "verifier_allowed": True,
    })
    return snapshot


def resolve_armor_worker(model: str, experiment_authorization: bool = False) -> dict[str, Any]:
    """Workforce-admitted local worker for model, or ModelUnavailable.

    Armor-on runs through Workforce Admission, which pins the local model per worker. A model with
    no admitted bounded_code_candidate worker cannot run on the armor path; nothing is substituted.
    An EXPERIMENT_ONLY worker is bound only with the operator's explicit experiment authorization
    (--experiment-authorization), which Workforce Admission then evaluates; the state is unchanged.
    """
    from nexus.services.model_workforce_policy import NON_ADMISSIBLE_STATES, WorkforcePolicyLoader

    workers = WorkforcePolicyLoader().load().workers
    admitted = {
        w.model: w
        for w in workers.values()
        if w.provider == "ollama"
        and "bounded_code_candidate" in w.roles
        and w.availability == "AVAILABLE"
        and w.state not in NON_ADMISSIBLE_STATES
    }
    if model not in admitted:
        raise ModelUnavailable(
            f"--armor on needs a workforce-admitted local worker for model {model!r}; "
            f"admitted bounded_code_candidate models: {sorted(admitted)}"
        )
    worker = admitted[model]
    binding: dict[str, Any] = {"worker_id": worker.worker_id, "controls": list(worker.requires)}
    if worker.state == "EXPERIMENT_ONLY":
        if not experiment_authorization:
            raise ModelUnavailable(
                f"worker {worker.worker_id!r} for model {model!r} is EXPERIMENT_ONLY; "
                "pass --experiment-authorization to run it as an explicitly authorized experiment"
            )
        binding["explicit_experiment_authorization"] = True
    return binding


def armor_worker_identity(model: str, experiment_authorization: bool = False) -> dict[str, Any]:
    """Workforce identity recorded in validation.json for an armor-on run."""
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader

    binding = resolve_armor_worker(model, experiment_authorization)
    worker = WorkforcePolicyLoader().load().workers[binding["worker_id"]]
    return {
        "worker_id": worker.worker_id,
        "state": worker.state,
        "autonomy": worker.autonomy,
        "explicit_experiment_authorization": bool(
            binding.get("explicit_experiment_authorization", False)
        ),
    }


def probe_memory_hits(task: dict[str, Any], symbol: str, enabled: bool) -> tuple[int, str]:
    """Real lesson count the planner sees as its memory signal. The off arm never queries memory."""
    if not enabled:
        return 0, "memory_arm_off"
    try:
        from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter

        lessons = MemoryRetrievalAdapter(enabled=True).retrieve_reranked(
            query_text=task["problem_statement"],
            anchor_symbol=symbol,
            anchor_file=task["target_file"],
            limit=3,
            max_chars=800,
            task_id=task["id"],
            current_state={"runtime_identity": "memory_ab_armor"},
        )
    except Exception as exc:  # noqa: BLE001 - a failed probe is recorded, not fatal
        return 0, f"memory_probe_failed:{type(exc).__name__}"
    return len(lessons or []), "ok"


def run_armor_mainchain(
    *,
    task: dict[str, Any],
    work_dir: Path,
    run_root: Path,
    arm: str,
    attempt_id: str,
    model: str,
    profile: str,
    git_rev: str,
    python: str,
    patch_timeout: int,
    experiment_authorization: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """One armor-on attempt: CapabilityPlanner -> run_mainchain(with_nexus_armor=True) -> local heal.

    Local-only route: the planner-selected capabilities run through the mainchain executor registry,
    the local model runs through LocalAssistService -> LocalModelExecutor at the armor profile.
    Returns (UnifiedRuntime receipt, executor metadata sink). Tests monkeypatch build_armor_service.
    """
    from nexus.services.local_assist_service import REQUEST_SCHEMA, LocalAssistRequest
    from nexus.services.mainchain_entry import build_mainchain_capability_invokers, run_mainchain
    from nexus.services.runtime_compat import UnifiedRuntimeRequest

    _, memory_enabled, _ = ARMS[arm]
    task_id = task["id"]
    target_file = task["target_file"]
    symbol = derive_target_symbol(task, (work_dir / target_file).read_text(encoding="utf-8"))
    evidence = (f"memory_ab:{attempt_id}:request",)
    receipt_path = run_root / "armor_receipts" / f"{arm}__{task_id}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    armor_root = run_root / "armor_artifacts"
    worker = resolve_armor_worker(model, experiment_authorization)
    memory_hits, memory_probe = probe_memory_hits(task, symbol, memory_enabled)
    executor_sink: dict[str, Any] = {"memory_hits": memory_hits, "memory_probe": memory_probe}

    with armor_environment(model, profile, armor_root):
        snapshot = build_armor_snapshot(task, model)
        local_request = LocalAssistRequest(
            schema=REQUEST_SCHEMA,
            task_id=task_id,
            parent_task_id=task_id,
            workspace_root=str(work_dir),
            workspace_revision=git_rev,
            task_statement=task["problem_statement"],
            action="verified-subtask",
            allowed_files=(target_file,),
            target_file=target_file,
            target_symbol=symbol,
            evidence_refs=evidence,
            verifier_command=(python, task["repro_file"]),
            time_budget=float(patch_timeout),
            requested_role="candidate",
            planner_snapshot=snapshot,
        )
        codeintel = {
            "workspace_root": str(work_dir),
            "target_file": target_file,
            "target_symbol": symbol,
        }
        request = UnifiedRuntimeRequest(
            task_id=task_id,
            workspace_revision=git_rev,
            task_statement=task["problem_statement"],
            task_type="repair",
            route={
                "recommended_flow": "local_only",
                "workforce_admission_enabled": True,
                "workforce_bindings": {"local": worker},
                "route_features": {
                    "memory_hits": memory_hits,
                    "findings_hits": 0,
                    # repro.py is a deterministic verifier; the planner picks localheal_pipeline from it
                    "deterministic_verifier_available": True,
                },
                "target_file": target_file,
                "workspace_root": str(work_dir),
            },
            online_enabled=False,
            local_enabled=True,
            online_prompt=task["problem_statement"],
            evidence_refs=evidence,
            local_request=local_request,
            codeintel=codeintel,
            # A local-only armored attempt runs in World C (local_armor), entered from a bench
            # runner, as in scripts/bench/n30r_v1_full_armor_trace.py. Without this the planner
            # defaults to product_runtime and the World C receipt is rejected with
            # canonical_execution_world_mismatch, so no verified candidate is ever delivered.
            canonical_context=dict(ARMOR_CANONICAL_CONTEXT),
        )

        def online_disabled(_context: Any) -> dict[str, Any]:
            raise RuntimeError("online channel is disabled for the armor A/B")

        receipt = run_mainchain(
            request,
            online_invoker=online_disabled,
            local_service=build_armor_service(armor_root / "isolated", executor_sink),
            capability_invokers=build_mainchain_capability_invokers(codeintel=codeintel),
            verifier=None,
            learning=None,
            receipt_path=receipt_path,
            with_nexus_armor=True,
        )
    return receipt, executor_sink


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _ledger_profile(receipt: dict[str, Any]) -> str:
    """Execution profile the provider ledger recorded for the last model call."""
    ledger = _local_exec_receipt(receipt).get("provider_call_ledger") or []
    for record in reversed(ledger):
        profile = _as_dict(record).get("execution_profile")
        if profile:
            return str(profile)
    return ""


def empty_armor_evidence(source: str = "no_receipt") -> dict[str, Any]:
    """Armor evidence for an attempt that produced no unified receipt (exception or timeout)."""
    return {
        "capabilities_selected": [],
        "capabilities_invoked": [],
        "advisory_stub_capabilities": [],
        "committee_invoked": False,
        "with_nexus_armor": False,
        "armor_profile_observed": "",
        "executor_pipeline_failure": "",
        "executor_failure_class": "",
        "executor_world_c_failure": "",
        "semantic_retry_invoked": False,
        "patch_attempt_count": 0,
        "local_selected_capabilities": [],
        "memory_selected_ids": [],
        "memory_signal_hits": 0,
        "memory_probe": "",
        "memory_prompt_included": False,
        "capability_status": {},
        "local_stage_status": "",
        "model_calls": 0,
        "candidate_isolation_status": "",
        "local_verifier_status": "",
        "planner_decision_id": "",
        "unified_receipt_terminal_status": "",
        "evidence_source": source,
    }


def extract_armor_evidence(
    receipt: dict[str, Any], executor_sink: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Receipt-backed capability evidence for an armor-on attempt (no advisory stubs)."""
    local_stage = _as_dict(receipt.get("local"))
    response = _as_dict(local_stage.get("response"))
    outputs = _as_dict(response.get("local_outputs"))
    meta = _as_dict(_as_dict(executor_sink).get("meta"))
    model_calls = int(response.get("model_call_count") or response.get("provider_call_count") or 0)

    selected = [str(c) for c in receipt.get("selected_capabilities") or []]
    invoked: list[str] = []
    stubs: list[str] = []
    per_capability: dict[str, dict[str, Any]] = {}
    for entry in receipt.get("capabilities") or []:
        entry = _as_dict(entry)
        name = str(entry.get("name") or "")
        if not name:
            continue
        callable_name = str(entry.get("physical_callable") or "")
        per_capability[name] = {
            "status": entry.get("status"),
            "invoked": bool(entry.get("invoked")),
            "skipped": bool(entry.get("skipped")),
            "gate_passed": bool(entry.get("gate_passed")),
            "physical_callable": callable_name,
        }
        is_stub = any(marker in callable_name for marker in STUB_CALLABLE_MARKERS)
        real = (
            entry.get("invoked") is True
            and not entry.get("skipped")
            and entry.get("evidence_present") is True
            and str(entry.get("status") or "") in {"INVOKED", "SUCCEEDED"}
            and not is_stub
        )
        if real:
            invoked.append(name)
        elif is_stub and entry.get("invoked"):
            stubs.append(name)

    # The local stage runs the executor itself; its own causal usage map is evidence too.
    executor_ran = bool(response.get("executor_invoked")) and model_calls > 0
    usage = _as_dict(outputs.get("capability_usage_status"))
    if executor_ran:
        invoked.append("local_model_executor")
        if meta.get("localheal_pipeline_run_called") is True:
            invoked.append("repair_loop")
    for name, status in usage.items():
        if status != "used" or not executor_ran:
            continue
        if name in STUB_PRONE_CAPABILITIES:
            continue
        invoked.append(str(name))
    ddtree = _as_dict(meta.get("ddtree_result"))
    if ddtree.get("invoked"):
        count = int(_as_dict(ddtree.get("telemetries")).get("candidate_count") or 0)
        (invoked if count > 0 else stubs).append("ddtree")
    autoreason = _as_dict(meta.get("autoreason_result"))
    if autoreason.get("invoked"):
        judged = int(_as_dict(autoreason.get("telemetries")).get("judge_count") or 0)
        (invoked if judged > 0 else stubs).append("autoreason")
    committee = bool(meta.get("p4_committee_invoked") is True)
    if committee:
        invoked.append("committee")

    ordered = [c for c in selected if c in invoked]
    ordered += sorted({c for c in invoked if c not in selected})
    candidate = _as_dict(response.get("candidate_summary"))
    verifier = _as_dict(response.get("verifier_summary"))
    receipt_base = _as_dict(receipt.get("receipt_base"))
    return {
        "capabilities_selected": selected,
        "capabilities_invoked": ordered,
        "advisory_stub_capabilities": sorted(set(stubs)),
        "committee_invoked": committee,
        "with_nexus_armor": receipt_base.get("with_nexus_armor") is True,
        "armor_profile_observed": str(
            meta.get("final_execution_profile")
            or meta.get("initial_execution_profile")
            or _ledger_profile(receipt)
        ),
        "executor_pipeline_failure": str(meta.get("pipeline_failure_reason") or "")[:200],
        "executor_failure_class": str(meta.get("failure_class") or "")[:100],
        "executor_world_c_failure": str(meta.get("path_a_failure_reason") or "")[:300],
        "semantic_retry_invoked": bool(meta.get("semantic_retry_invoked")),
        "patch_attempt_count": int(meta.get("patch_attempt_count") or 0),
        "local_selected_capabilities": [
            str(c)
            for c in _as_dict(executor_sink).get("selected_capabilities")
            or outputs.get("selected_capabilities")
            or []
        ],
        "memory_selected_ids": [str(c) for c in meta.get("memory_selected_ids") or []],
        "memory_signal_hits": int(_as_dict(executor_sink).get("memory_hits") or 0),
        "memory_probe": str(_as_dict(executor_sink).get("memory_probe") or ""),
        "memory_prompt_included": bool(meta.get("memory_prompt_included")),
        "capability_status": per_capability,
        "local_stage_status": str(local_stage.get("status") or ""),
        "model_calls": model_calls,
        "candidate_isolation_status": str(candidate.get("isolation_status") or ""),
        "local_verifier_status": str(verifier.get("verifier_status") or ""),
        "planner_decision_id": str(receipt.get("planner_decision_id") or ""),
        "unified_receipt_terminal_status": str(receipt.get("terminal_status") or ""),
        "evidence_source": "unified_runtime_receipt",
    }


def extract_heal_receipt_evidence(receipt_path: str) -> dict[str, Any]:
    """Receipt-backed evidence for an armor-off attempt, read from the HealPipeline receipt.json."""
    empty = {
        "capabilities_selected": [],
        "capabilities_invoked": [],
        "advisory_stub_capabilities": [],
        "committee_invoked": False,
        "with_nexus_armor": False,
        "evidence_source": "missing",
    }
    path = Path(str(receipt_path or ""))
    if not path.is_file():
        return empty
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    receipt_base = _as_dict(receipt.get("receipt_base"))
    chain = [_as_dict(item) for item in receipt_base.get("consumption_chain") or []]
    selected = [str(c["capability"]) for c in chain if c.get("capability") and c.get("selected")]
    invoked = [
        str(c["capability"])
        for c in chain
        if c.get("capability") and c.get("selected") and c.get("evidence_present")
    ]
    return {
        "capabilities_selected": selected,
        "capabilities_invoked": invoked,
        "advisory_stub_capabilities": [],
        "committee_invoked": receipt.get("p4_committee_invoked") is True,
        "with_nexus_armor": receipt_base.get("with_nexus_armor") is True,
        "evidence_source": "local_heal_receipt",
    }


def materialize_candidate(receipt: dict[str, Any], work_dir: Path, target_file: str) -> str:
    """Copy the isolated, hash-matched candidate result into work_dir so the repro rerun judges it.

    The executor never edits the real workspace; without this the independent verdict would always
    see the original bug. Returns a status string recorded in armor_evidence.
    """
    response = _as_dict(_as_dict(receipt.get("local")).get("response"))
    candidate = _as_dict(response.get("candidate_summary"))
    if not candidate.get("selected"):
        return "no_candidate"
    if candidate.get("isolation_status") != "isolated":
        return "candidate_not_isolated"
    if not candidate.get("selected_candidate_hash_matches_applied"):
        return "candidate_hash_not_proven"
    patched = Path(str(candidate.get("isolated_workspace") or "")) / target_file
    if not patched.is_file():
        return "isolated_target_missing"
    shutil.copyfile(patched, work_dir / target_file)
    return "applied"


def apply_armor_overrides(
    row: dict[str, Any], armor: str, armor_profile: str, evidence: dict[str, Any]
) -> None:
    """Flat armor columns on every row, plus the armor_evidence sibling with the detail."""
    row["armor"] = armor
    row["armor_profile"] = armor_profile
    row["capabilities_selected"] = list(evidence["capabilities_selected"])
    row["capabilities_invoked"] = list(evidence["capabilities_invoked"])
    row["committee_invoked"] = bool(evidence["committee_invoked"])
    row["with_nexus_armor"] = bool(evidence["with_nexus_armor"])
    row["armor_evidence"] = evidence


def build_armor_axis(rows: list[dict[str, Any]], armor: str, armor_profile: str) -> dict[str, Any]:
    """Scorecard block: per-attempt armor evidence and rollups."""
    attempts = [
        {
            "attempt_id": r["attempt_id"],
            "task_id": r["task_id"],
            "workflow": r["workflow"],
            "terminal_outcome": r["terminal_outcome"],
            **{key: r[key] for key in ARMOR_ROW_KEYS},
        }
        for r in rows
    ]
    invoked_union = sorted({c for r in rows for c in r["capabilities_invoked"]})
    return {
        "schema": "memory_ab_v1.armor_axis.v1",
        "armor": armor,
        "armor_profile": armor_profile,
        "attempts": attempts,
        "capabilities_invoked_union": invoked_union,
        "attempts_with_nexus_armor": sum(1 for r in rows if r["with_nexus_armor"]),
        "attempts_with_committee": sum(1 for r in rows if r["committee_invoked"]),
        "attempts_with_capability_evidence": sum(1 for r in rows if r["capabilities_invoked"]),
        "claim_ceiling": "which capabilities left receipt evidence; not an effectiveness claim",
    }


def _local_exec_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """LocalAssistService execution_receipt.json on disk ({} when absent)."""
    response = _as_dict(_as_dict(receipt.get("local")).get("response"))
    path = Path(str(response.get("receipt_path") or ""))
    try:
        return _as_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


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
    armor: str = "off",
    armor_profile: str = DEFAULT_ARMOR_PROFILE,
    experiment_authorization: bool = False,
) -> dict[str, Any]:
    nexus_arm, memory_enabled, row_arm = ARMS[arm]
    task_id = task["id"]
    work_dir = run_root / "work" / arm / task_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(task["dir"], work_dir, ignore=shutil.ignore_patterns("__pycache__"))
    attempt_id = f"{run_id}:{nexus_arm}:{task_id}"

    if armor == "on":
        # No legacy HealContext on the armor path; the same attributes are filled from the receipt.
        ctx: Any = SimpleNamespace(
            memory_enabled=None,
            memory_arm=None,
            receipt_path="",
            model_decisions=[],
            user_prompt="",
            solve_eligible=False,
            _memory_influence_trace=None,
        )
    else:
        ctx = build_ctx(task, work_dir, arm, attempt_id, run_root, python)
    armor_receipt: dict[str, Any] = {}
    executor_sink: dict[str, Any] = {}
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
        if armor == "on":
            armor_receipt, executor_sink = run_armor_mainchain(
                task=task,
                work_dir=work_dir,
                run_root=run_root,
                arm=arm,
                attempt_id=attempt_id,
                model=model,
                profile=armor_profile,
                git_rev=git_rev,
                python=python,
                patch_timeout=patch_timeout,
                experiment_authorization=experiment_authorization,
            )
        else:
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

    armor_materialized = ""
    if armor == "on":
        armor_evidence = (
            extract_armor_evidence(armor_receipt, executor_sink)
            if armor_receipt
            else empty_armor_evidence()
        )
        counter.calls = int(armor_evidence.get("model_calls") or 0)
        if armor_receipt:
            armor_materialized = materialize_candidate(armor_receipt, work_dir, task["target_file"])
            # The planner owns capability selection; the arm controls the memory signal it sees and
            # the off arm must never reach the executor with memory selected.
            flag_applied = (
                memory_enabled or "memory" not in armor_evidence["local_selected_capabilities"]
            )
            ctx.memory_enabled = memory_enabled if flag_applied else not memory_enabled
            ctx.memory_arm = nexus_arm if flag_applied else "unapplied"
            ctx.receipt_path = str(armor_receipt.get("receipt_path") or "")
            ctx.solve_eligible = armor_evidence["local_verifier_status"] == "pass"
            ctx.user_prompt = str(_local_exec_receipt(armor_receipt).get("prompt_hash") or "")
        armor_evidence["candidate_materialized"] = armor_materialized
        armor_evidence["armor_profile_requested"] = armor_profile
        if armor_receipt and not armor_evidence["with_nexus_armor"]:
            ineligible.append("armor_not_applied")
        observed_profile = armor_evidence.get("armor_profile_observed", "")
        if observed_profile and observed_profile != armor_profile:
            ineligible.append("armor_profile_not_applied")
        elif not observed_profile and armor_evidence["model_calls"] > 0:
            ineligible.append("armor_profile_unobserved")

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
    if armor == "on" and episode is None and armor_receipt:
        # The executor retrieves lessons itself; its receipt is the evidence on the armor path.
        retrieved = _unique_ids(armor_evidence["memory_selected_ids"])
        applied = list(retrieved) if armor_evidence["memory_prompt_included"] else []
    applied = [lesson for lesson in applied if lesson in retrieved]

    # Retrieval receipt: explicit disabled receipt for the off arm, trace-backed for the on arm.
    trace = getattr(ctx, "_memory_influence_trace", None)
    trace_dict = (
        trace.to_dict()
        if hasattr(trace, "to_dict")
        else (trace if isinstance(trace, dict) else None)
    )
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
        "evidence_refs": [
            f"retrieval_receipt:{retrieval_path}",
            f"ollama_consumption:{consumption_path}",
        ],
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
    if armor != "on":
        armor_evidence = extract_heal_receipt_evidence(str(getattr(ctx, "receipt_path", "") or ""))
    apply_armor_overrides(
        row, armor, armor_profile if armor == "on" else ARMOR_PROFILE_NONE, armor_evidence
    )
    normalize_attempt_row(row)  # fail loudly if the row is not contract-valid
    return row


def build_workflow_rows(rows: list[dict[str, Any]], model: str) -> list[dict[str, Any]]:
    """One quality-workflow row per attempt for compare_workflows_at_required_quality."""
    out = []
    for row in rows:
        passed = row["terminal_outcome"] == "SUCCEEDED" and not row["ineligibility_reasons"]
        out.append({
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
        })
    return out


def build_scorecard(
    rows: list[dict[str, Any]],
    task_count: int,
    model: str,
    armor: str = "off",
    armor_profile: str = ARMOR_PROFILE_NONE,
) -> dict[str, Any]:
    scorecard = replay_scorecard(rows)
    scorecard["armor_axis"] = build_armor_axis(rows, armor, armor_profile)
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
    armor: str = "off",
    armor_profile: str = ARMOR_PROFILE_NONE,
    workforce_worker: dict[str, Any] | None = None,
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
        "armor": armor,
        "armor_profile": armor_profile,
        "with_nexus_armor_verified": all(r["with_nexus_armor"] for r in rows)
        if rows and armor == "on"
        else False,
        "workforce_worker": workforce_worker,
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
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tasks-dir", type=Path, default=DEFAULT_TASKS_DIR)
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--arms", default="off,on", help="comma-separated, run in this order (default off,on)"
    )
    parser.add_argument("--limit", type=int, default=None, help="use only the first N tasks")
    parser.add_argument(
        "--task-ids", default="", help="comma-separated task ids to run (default: all)"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--patch-timeout", type=int, default=300, help="wall-clock seconds per pipeline attempt"
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--reflect-judge", choices=["none", "ollama"], default="none")
    parser.add_argument(
        "--armor",
        choices=list(ARMOR_MODES),
        default="off",
        help="off: bare HealPipeline (default, unchanged). on: CapabilityPlanner + run_mainchain "
        "with_nexus_armor + local heal at --armor-profile",
    )
    parser.add_argument(
        "--armor-profile",
        choices=list(ARMOR_PROFILES),
        default=None,
        help=f"local armor execution profile when --armor on (default {DEFAULT_ARMOR_PROFILE})",
    )
    parser.add_argument(
        "--experiment-authorization",
        action="store_true",
        help="explicitly authorize an EXPERIMENT_ONLY workforce worker for this --armor on run; "
        "passed to Workforce Admission, does not change the worker's state",
    )
    args = parser.parse_args(argv)
    if args.armor == "off" and args.armor_profile is not None:
        parser.error("--armor-profile requires --armor on")
    if args.armor == "off" and args.experiment_authorization:
        parser.error("--experiment-authorization requires --armor on")
    args.armor_profile = (
        (args.armor_profile or DEFAULT_ARMOR_PROFILE) if args.armor == "on" else ARMOR_PROFILE_NONE
    )
    args.arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    args.task_ids = [t.strip() for t in args.task_ids.split(",") if t.strip()] or None
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
    tasks = load_tasks(args.tasks_dir, args.limit, args.task_ids)

    workforce_worker: dict[str, Any] | None = None
    try:
        preflight_model(args.model)
        if args.armor == "on":
            workforce_worker = armor_worker_identity(args.model, args.experiment_authorization)
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
                armor=args.armor,
                armor_profile=args.armor_profile,
                experiment_authorization=args.experiment_authorization,
            )
            append_row(rows_path, row)
            rows.append(row)
            print(
                f"[{arm}] {task['id']:32} {row['terminal_outcome']:9} "
                f"pipeline={row['pipeline_status']} t={row['wall_duration_sec']}s "
                f"calls={row['model_calls']} retrieved={row['retrieved_lesson_ids']} "
                f"applied={row['applied_attributed_lesson_ids']} armor={row['armor']} "
                f"invoked={row['capabilities_invoked']}",
                flush=True,
            )

    leaks = guard.leaks()
    scorecard = build_scorecard(rows, len(tasks), args.model, args.armor, args.armor_profile)
    (run_root / "scorecard.json").write_text(
        json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    validation = build_validation(
        rows,
        run_id=args.run_id,
        tasks=[t["id"] for t in tasks],
        arms=args.arms,
        model=args.model,
        state_root=state_root,
        reflect_judge=args.reflect_judge,
        leaks=leaks,
        armor=args.armor,
        armor_profile=args.armor_profile,
        workforce_worker=workforce_worker,
    )
    (run_root / "validation.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
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
    print(
        f"adoption_decision: {decision['decision']} reasons={decision['reason_codes']} (source={NEXUS_LEARNING_SOURCE})"
    )

    print(f"run_root: {run_root}")
    print(f"rows: {len(rows)} real_model_call_executed={validation['real_model_call_executed']}")
    if leaks:
        for path in leaks:
            print(f"STATE_LEAK: {path}")
        return EXIT_STATE_LEAK
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
