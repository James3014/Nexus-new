"""Post-candidate invocation seam (online A/B wiring plan, PR-2 / B1).

``build_escalate_gated_invoker`` runs ``sandbox`` / ``ultra_review`` / ``file_lock`` only on
escalate signals the online sprint never sets, and the planner-signal table excludes them on
purpose: the preflight seam has no candidate to run or review, and a lock without a release
would self-block.  So on every online row the executing runtime planner *selected* them and the
gate recorded ``SKIPPED_POLICY_NOT_TRIGGERED``.

This seam runs them where they make sense, modelled on
``online_nexus_context.build_plan_gated_postflight_invokers``:

* only for capabilities the executing runtime planner selected and the preflight gate skipped
  for want of an escalate trigger (``runtime_selected_untriggered``);
* ``sandbox`` / ``ultra_review`` run *after* a model candidate exists, on a scratch copy that
  holds the original target (committed) plus the candidate (working tree) and the visible test
  only; the hidden verifier test is never copied, is passed as a forbidden read root to the
  sandbox confinement, and is excluded from the review's mapped tests;
* ``file_lock`` is acquired on the target before the candidate is written and released after
  the row (re-acquire by the same task is idempotent).

The seam never changes the candidate, the prompt or the row outcome; it only produces
capability stages shaped like UnifiedRuntime stages (``capabilities`` rows) so the existing
projection (``project_unified_capability_stages``) reports them as invoked with their own
execution-derived ``claim_boundary``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess  # nosec B404 - fixed git argv, never a shell
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

POST_CANDIDATE_SEAM_SOURCE = "post_candidate_seam"
POST_CANDIDATE_RECEIPT_KIND = "post_candidate_seam"
# Run after a candidate exists, on the scratch copy.
POST_CANDIDATE_CAPABILITIES: tuple[str, ...] = ("sandbox", "ultra_review")
# Acquired before the candidate is written to the target, released after the row.
FILE_LOCK_CAPABILITY = "file_lock"
SEAM_CAPABILITIES: tuple[str, ...] = (*POST_CANDIDATE_CAPABILITIES, FILE_LOCK_CAPABILITY)
# "0"/"false"/"off" turns the seam off (the preflight skip receipts stay as they were).
SEAM_DISABLE_ENV = "NEXUS_POST_CANDIDATE_SEAM"
HIDDEN_TEST_BASENAMES: tuple[str, ...] = ("test_hidden.py",)
SANDBOX_REFUSED_STATUS = "NOT_EXECUTED_SANDBOX_REFUSED"
SKIPPED_SANDBOX_REFUSED = "SKIPPED_SANDBOX_REFUSED"
SANDBOX_TIMEOUT_SEC = 60
_SKIP_POLICY_NOT_TRIGGERED = "SKIPPED_POLICY_NOT_TRIGGERED"
_GIT_IDENTITY = ("-c", "user.name=nexus-post-candidate", "-c", "user.email=nexus@localhost")

InvokerFactory = Callable[[str], Callable[[Mapping[str, Any]], Mapping[str, Any]] | None]


class PostCandidateSeamError(RuntimeError):
    """The scratch copy could not be built safely (fail closed: nothing runs)."""


def seam_enabled() -> bool:
    value = os.environ.get(SEAM_DISABLE_ENV, "").strip().lower()
    return value not in {"0", "false", "no", "off"}


def runtime_selected_untriggered(
    unified_receipt: Mapping[str, Any] | None, names: Iterable[str] = SEAM_CAPABILITIES
) -> list[str]:
    """Names the executing runtime planner selected but the escalate gate skipped untriggered."""

    if not isinstance(unified_receipt, Mapping):
        return []
    wanted = set(names)
    stages = unified_receipt.get("capabilities")
    out: list[str] = []
    for stage in stages if isinstance(stages, list) else []:
        if not isinstance(stage, Mapping):
            continue
        name = str(stage.get("name") or "")
        if name not in wanted or name in out:
            continue
        if bool(stage.get("invoked")) and str(stage.get("status") or "") == "INVOKED":
            continue
        reason = str(stage.get("skip_reason") or stage.get("reason") or "")
        if _SKIP_POLICY_NOT_TRIGGERED in reason:
            out.append(name)
    return [name for name in SEAM_CAPABILITIES if name in out]


def hidden_test_paths(test_file: Path | str) -> list[Path]:
    """Hidden verifier tests next to the visible test (whether or not they currently exist)."""

    visible = Path(test_file)
    return [visible.with_name(name) for name in HIDDEN_TEST_BASENAMES]


@dataclass
class CandidateScratch:
    """A git repo holding the original target (committed) and the candidate (working tree)."""

    root: Path
    target_rel: str
    visible_rel: str
    candidate_sha256: str
    forbidden_paths: tuple[Path, ...] = ()
    cleanup_dir: Path | None = None
    files: tuple[str, ...] = field(default_factory=tuple)

    def cleanup(self) -> None:
        if self.cleanup_dir is not None:
            shutil.rmtree(self.cleanup_dir, ignore_errors=True)


def _git(root: Path, *args: str) -> None:
    from nexus.engine.sandboxed_lane import git_safe_env

    env = git_safe_env(home=root.parent, ceiling=root.parent)
    proc = subprocess.run(  # noqa: S603 - fixed argv
        ["git", *_GIT_IDENTITY, *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        raise PostCandidateSeamError(f"git_{args[0]}_failed:{(proc.stderr or proc.stdout)[-200:]}")


def prepare_candidate_scratch(
    *,
    target_path: Path | str,
    visible_test_path: Path | str,
    original_code: str,
    candidate_code: str,
    forbidden_paths: Iterable[Path | str] = (),
) -> CandidateScratch:
    """Build the scratch copy: target + visible test (+ sibling ``conftest.py``), never hidden.

    Paths keep their layout relative to the common parent of target and visible test.
    """

    target = Path(target_path).resolve()
    visible = Path(visible_test_path).resolve()
    forbidden = tuple(Path(path).resolve() for path in forbidden_paths if str(path).strip())
    names = set(HIDDEN_TEST_BASENAMES)
    if visible.name in names or target.name in names:
        raise PostCandidateSeamError("hidden_test_named_as_input")
    if visible in forbidden or target in forbidden:
        raise PostCandidateSeamError("forbidden_path_named_as_input")
    if not visible.is_file():
        raise PostCandidateSeamError("visible_test_missing")
    base = Path(os.path.commonpath([str(target.parent), str(visible.parent)]))
    sources: dict[str, str] = {
        target.relative_to(base).as_posix(): original_code,
        visible.relative_to(base).as_posix(): visible.read_text(encoding="utf-8"),
    }
    conftest = visible.parent / "conftest.py"
    if conftest.is_file() and not conftest.is_symlink():
        sources.setdefault(
            conftest.relative_to(base).as_posix(), conftest.read_text(encoding="utf-8")
        )
    for rel in sources:
        if Path(rel).name in names or (base / rel).resolve() in forbidden:
            raise PostCandidateSeamError(f"forbidden_file_in_scratch:{rel}")
    cleanup_dir = Path(tempfile.mkdtemp(prefix="nexus-post-candidate-")).resolve()
    root = cleanup_dir / "repo"
    try:
        for rel, text in sources.items():
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
        _git(root, "init", "-q")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "--no-verify", "-m", "original target + visible test")
        target_rel = target.relative_to(base).as_posix()
        (root / target_rel).write_text(candidate_code, encoding="utf-8")
        leaked = [path for path in root.rglob("*") if path.name in names]
        if leaked:
            raise PostCandidateSeamError("hidden_test_in_scratch")
    except Exception:
        shutil.rmtree(cleanup_dir, ignore_errors=True)
        raise
    return CandidateScratch(
        root=root,
        target_rel=target_rel,
        visible_rel=visible.relative_to(base).as_posix(),
        candidate_sha256=hashlib.sha256(candidate_code.encode("utf-8")).hexdigest(),
        forbidden_paths=forbidden,
        cleanup_dir=cleanup_dir,
        files=tuple(sorted(sources)),
    )


def sandbox_context(task_id: str, scratch: CandidateScratch) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "workspace_root": str(scratch.root),
        "sandbox_command": [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            scratch.visible_rel,
        ],
        "sandbox_timeout_sec": SANDBOX_TIMEOUT_SEC,
        "sandbox_forbidden_paths": [str(path) for path in scratch.forbidden_paths],
    }


def ultra_review_context(task_id: str, scratch: CandidateScratch) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "workspace_root": str(scratch.root),
        "ultra_review_regression_tests": [scratch.visible_rel],
        "ultra_review_excluded_tests": list(HIDDEN_TEST_BASENAMES),
    }


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _claim_boundary(out: Mapping[str, Any]) -> dict[str, Any]:
    """Execution-derived boundary (``simulated`` from evidence, never a constant)."""

    from nexus.evidence.claim_boundary import attested_claim_boundary

    response = _as_mapping(out.get("response"))
    outcome = _as_mapping(response.get("outcome"))
    boundary = attested_claim_boundary(
        invoked=bool(out.get("invoked")),
        evidence_refs=list(out.get("evidence_refs") or []),
        gate_passed=bool(out.get("gate_passed")),
        physical_callable=str(out.get("physical_callable") or ""),
        outcome={
            **{str(k): v for k, v in outcome.items()},
            "status": str(response.get("status") or ""),
        },
        skipped=bool(out.get("skipped")),
        stub=bool(out.get("stub")),
        failure_reason=str(out.get("reason") or ""),
    )
    data = boundary.to_dict()
    return {
        "simulated": bool(data.get("simulated", True)),
        "claim_eligible": bool(data.get("claim_eligible", False)),
        "evidence_complete": bool(data.get("evidence_complete", False)),
    }


def stage_from_invocation(name: str, out: Mapping[str, Any], *, phase: str) -> dict[str, Any]:
    """A UnifiedRuntime-shaped capability stage for one seam invocation."""

    invoked = bool(out.get("invoked"))
    boundary = (
        _claim_boundary(out)
        if invoked
        else {
            "simulated": True,
            "claim_eligible": False,
            "evidence_complete": False,
        }
    )
    response = _as_mapping(out.get("response"))
    outcome = _as_mapping(response.get("outcome"))
    skip_reason = "" if invoked else str(out.get("skip_reason") or out.get("reason") or "")
    if not invoked and str(outcome.get("semantic_status") or "") == SANDBOX_REFUSED_STATUS:
        # The confinement refused to run anything: a skip with its reason, never INVOKED.
        skip_reason = f"{SKIPPED_SANDBOX_REFUSED}:{outcome.get('error') or 'refused'}"[:300]
    return {
        "name": name,
        "status": "INVOKED" if invoked else "SKIPPED",
        "invoked": invoked,
        "gate_passed": bool(out.get("gate_passed")) if invoked else False,
        "skip_reason": skip_reason,
        "evidence_refs": [str(ref) for ref in (out.get("evidence_refs") or []) if str(ref).strip()],
        "simulated": boundary["simulated"],
        "claim_boundary": boundary,
        "trigger_source": f"{POST_CANDIDATE_SEAM_SOURCE}:{phase}",
        "physical_callable": str(out.get("physical_callable") or ""),
        "outcome": _bounded_outcome(name, outcome),
    }


def _bounded_outcome(name: str, outcome: Mapping[str, Any]) -> dict[str, Any]:
    keep = {
        "sandbox": (
            "semantic_status",
            "exit_code",
            "stdout_sha256",
            "output_tail",
            "simulated",
            "sandbox_executed",
            "workspace_isolated",
            "network_allowed",
            "confined",
            "forbidden_paths_count",
            "timed_out",
            "error",
        ),
        "ultra_review": (
            "semantic_status",
            "result",
            "executed_checks",
            "findings",
            "blocked_reason",
            "regression_tests",
            "excluded_regression_tests",
            "error",
        ),
        "file_lock": (
            "semantic_status",
            "lock_file",
            "access_granted",
            "task_files_match",
            "conflicts",
            "error",
        ),
    }.get(name, ("semantic_status", "error"))
    return {key: outcome[key] for key in keep if key in outcome}


def _invoke(
    name: str, context: Mapping[str, Any], factory: InvokerFactory | None
) -> dict[str, Any]:
    if factory is None:
        from nexus.services.capability_registry import build_real_executor_invoker as factory
    invoker = factory(name)
    if invoker is None:
        return {"invoked": False, "skip_reason": "BLOCKED_EXECUTOR_UNAVAILABLE"}
    try:
        return dict(invoker(context))
    except Exception as exc:  # noqa: BLE001 - seam boundary: report, never raise into the row
        return {
            "invoked": False,
            "skip_reason": f"post_candidate_invoker_error:{type(exc).__name__}",
        }


def run_post_candidate_capabilities(
    *,
    task_id: str,
    names: Iterable[str],
    scratch: CandidateScratch,
    invoker_factory: InvokerFactory | None = None,
) -> list[dict[str, Any]]:
    """Run ``sandbox`` / ``ultra_review`` (those in ``names``) on the scratch copy."""

    builders = {"sandbox": sandbox_context, "ultra_review": ultra_review_context}
    stages: list[dict[str, Any]] = []
    for name in POST_CANDIDATE_CAPABILITIES:
        if name not in set(names):
            continue
        out = _invoke(name, builders[name](task_id, scratch), invoker_factory)
        stages.append(stage_from_invocation(name, out, phase="post_candidate"))
    return stages


def acquire_target_lock(
    *,
    task_id: str,
    workspace_root: Path | str,
    target_file: str,
    invoker_factory: InvokerFactory | None = None,
) -> dict[str, Any]:
    """Acquire the ``file_lock`` capability on the target (before the candidate is written)."""

    out = _invoke(
        FILE_LOCK_CAPABILITY,
        {
            "task_id": task_id,
            "workspace_root": str(workspace_root),
            "target_files": [str(target_file)],
        },
        invoker_factory,
    )
    return stage_from_invocation(FILE_LOCK_CAPABILITY, out, phase="pre_attempt")


def release_target_lock(task_id: str) -> dict[str, list[str]]:
    """Release every lock ``task_id`` holds (idempotent; empty when none)."""

    from nexus.orchestrator.file_lock_registry import release_task_locks

    return release_task_locks(task_id)


def post_candidate_receipt(
    *,
    task_id: str,
    stages: list[dict[str, Any]],
    candidate_sha256: str = "",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """UnifiedRuntime-shaped receipt for ``project_unified_capability_stages``."""

    receipt = {
        "task_id": task_id,
        "receipt_kind": POST_CANDIDATE_RECEIPT_KIND,
        "capabilities": list(stages),
        "candidate_sha256": candidate_sha256,
    }
    if extra:
        receipt.update(dict(extra))
    return receipt


def run_seam_for_candidate(
    *,
    task_id: str,
    unified_receipt: Mapping[str, Any] | None,
    target_path: Path | str,
    visible_test_path: Path | str,
    original_code: str,
    candidate_code: str,
    invoker_factory: InvokerFactory | None = None,
    workspace_root: Path | str | None = None,
) -> dict[str, Any] | None:
    """Post-candidate half of the seam: build the scratch copy and run sandbox/ultra_review.

    Returns a UnifiedRuntime-shaped receipt, or None when nothing was selected / the seam is off.
    A scratch copy that cannot be built safely yields not-invoked stages naming the reason.
    """

    if not seam_enabled() or candidate_code == original_code:
        return None
    names = [
        name
        for name in runtime_selected_untriggered(unified_receipt, POST_CANDIDATE_CAPABILITIES)
        if name in POST_CANDIDATE_CAPABILITIES
    ]
    if not names:
        return None
    forbidden = [*hidden_test_paths(visible_test_path), *bench_forbidden_roots(workspace_root)]
    try:
        scratch = prepare_candidate_scratch(
            target_path=target_path,
            visible_test_path=visible_test_path,
            original_code=original_code,
            candidate_code=candidate_code,
            forbidden_paths=forbidden,
        )
    except (PostCandidateSeamError, OSError, subprocess.SubprocessError) as exc:
        reason = f"post_candidate_scratch_refused:{exc}"[:200]
        stages = [
            stage_from_invocation(
                name, {"invoked": False, "skip_reason": reason}, phase="post_candidate"
            )
            for name in names
        ]
        return post_candidate_receipt(task_id=task_id, stages=stages)
    try:
        stages = run_post_candidate_capabilities(
            task_id=task_id, names=names, scratch=scratch, invoker_factory=invoker_factory
        )
        return post_candidate_receipt(
            task_id=task_id,
            stages=stages,
            candidate_sha256=scratch.candidate_sha256,
            extra={
                "scratch_files": list(scratch.files),
                "hidden_paths_forbidden": len(scratch.forbidden_paths),
            },
        )
    finally:
        scratch.cleanup()


def lock_target_if_selected(
    *,
    unified_receipt: Mapping[str, Any] | None,
    task_id: str,
    workspace_root: Path | str,
    target_file: str,
    invoker_factory: InvokerFactory | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Pre-attempt half: acquire ``file_lock`` on the target when the runtime selected it.

    Returns ``(lock_task_id, stages)``; ``lock_task_id`` is "" when nothing was acquired, else
    the caller must ``release_target_lock(lock_task_id)`` after the row.
    """

    if not seam_enabled() or FILE_LOCK_CAPABILITY not in runtime_selected_untriggered(
        unified_receipt, (FILE_LOCK_CAPABILITY,)
    ):
        return "", []
    stage = acquire_target_lock(
        task_id=task_id,
        workspace_root=workspace_root,
        target_file=target_file,
        invoker_factory=invoker_factory,
    )
    return (task_id if stage["invoked"] else ""), [stage]


def lock_denied(pre_stages: list[dict[str, Any]]) -> bool:
    """True when the seam acquired-or-tried the target lock and it was not granted."""
    for stage in pre_stages:
        if stage.get("name") != FILE_LOCK_CAPABILITY:
            continue
        if (
            not stage.get("gate_passed")
            or stage.get("outcome", {}).get("access_granted") is not True
        ):
            return True
    return False


def merge_seam_receipts(
    *,
    task_id: str,
    pre_stages: list[dict[str, Any]],
    post_receipt: Mapping[str, Any] | None,
    released: Mapping[str, list[str]] | None = None,
) -> dict[str, Any] | None:
    """One receipt for the row: file_lock (pre-attempt) + sandbox/ultra_review (post-candidate)."""

    stages = [*pre_stages, *((post_receipt or {}).get("capabilities") or [])]
    if not stages:
        return None
    extra = {
        key: value
        for key, value in dict(post_receipt or {}).items()
        if key not in {"task_id", "receipt_kind", "capabilities", "candidate_sha256"}
    }
    if pre_stages:
        extra["file_lock_released"] = {str(k): list(v) for k, v in dict(released or {}).items()}
    return post_candidate_receipt(
        task_id=task_id,
        stages=stages,
        candidate_sha256=str((post_receipt or {}).get("candidate_sha256") or ""),
        extra=extra,
    )


# --- Confined visible test (strict/counted lane) ---------------------------------------------
#
# Same-user code defeats file permissions, so the real boundary for the bench is that the
# candidate and the visible test never run unconfined: under the strict/counted lane
# (``NEXUS_CONFINE_VISIBLE_TEST=1``, set by the bench runner) the product runs the visible test
# on a scratch copy inside ``sandboxed_lane.confinement`` (default-deny reads under ``$HOME``,
# no network, the hidden test and the bench staging parent as forbidden read roots). Without
# an OS barrier nothing runs: the result is ``confinement_unavailable`` (not executed).
CONFINE_VISIBLE_TEST_ENV = "NEXUS_CONFINE_VISIBLE_TEST"
CONFINEMENT_UNAVAILABLE = "confinement_unavailable"
BENCH_HIDDEN_STAGING_PARENT = Path.home() / ".cache" / "nexus-bench-hidden"


def bench_forbidden_roots(workspace_root: Path | str | None) -> list[Path]:
    """Explicitly forbidden read roots on top of the confinement's default-deny allowlist
    (scratch copy + interpreter prefixes + system paths): the hidden-test staging parent and,
    for the workspace, every task's fixtures (``bench_fixtures/``, ``.nexus/`` incl.
    ``bench_cases/``) and the bench output tree (``artifacts/``)."""
    roots = [BENCH_HIDDEN_STAGING_PARENT]
    if workspace_root:
        base = Path(workspace_root)
        roots += [base / ".nexus", base / "bench_fixtures", base / "artifacts"]
    return roots


def confine_visible_test_enabled() -> bool:
    return os.environ.get(CONFINE_VISIBLE_TEST_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def run_visible_test_confined(
    *,
    target_path: Path | str,
    visible_test_path: Path | str,
    original_code: str,
    candidate_code: str,
    timeout_sec: float,
    workspace_root: Path | str | None = None,
) -> tuple[subprocess.CompletedProcess, bool]:
    """Visible pytest on a scratch copy holding ``candidate_code``, inside the confinement.

    Returns ``(completed, executed)``; ``executed`` is False (returncode 1, stderr names
    ``confinement_unavailable``) when the scratch copy or the confinement refused. A timeout
    raises ``subprocess.TimeoutExpired`` like ``subprocess.run`` would."""
    from nexus.engine.confined_test_runner import run_confined_test

    forbidden = [*hidden_test_paths(visible_test_path), *bench_forbidden_roots(workspace_root)]
    argv = [sys.executable, "-I", "-m", "pytest", "-q", "--maxfail=1", "-p", "no:cacheprovider"]
    try:
        scratch = prepare_candidate_scratch(
            target_path=target_path,
            visible_test_path=visible_test_path,
            original_code=original_code,
            candidate_code=candidate_code,
            forbidden_paths=forbidden,
        )
    except (PostCandidateSeamError, OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(
            argv, 1, "", f"{CONFINEMENT_UNAVAILABLE}:scratch:{exc}"[:300]
        ), False
    try:
        result = run_confined_test(
            scratch.root,
            command=[*argv, scratch.visible_rel],
            forbidden_paths=forbidden,
            timeout_sec=timeout_sec,
        )
    finally:
        scratch.cleanup()
    if not result.get("executed"):
        return subprocess.CompletedProcess(
            argv, 1, "", f"{CONFINEMENT_UNAVAILABLE}:{result.get('error')}"[:300]
        ), False
    if result.get("timed_out"):
        raise subprocess.TimeoutExpired(argv, timeout_sec)
    return (
        subprocess.CompletedProcess(
            argv,
            int(result.get("exit_code") or 0),
            str(result.get("stdout_tail") or ""),
            str(result.get("stderr_tail") or ""),
        ),
        True,
    )
