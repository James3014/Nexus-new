"""Online A/B wiring PR-2: post-candidate seam for sandbox / ultra_review / file_lock.

The escalate gate keeps skipping these in the preflight seam (no candidate yet); the seam runs
them after a model candidate exists, on a scratch copy that never holds the hidden test.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import nexus.engine.sandboxed_lane as lane
from nexus.engine import confined_test_runner
from nexus.engine.sandboxed_lane import SandboxError, confinement
from nexus.engine.ultra_review_service import UltraReviewService
from nexus.services import post_candidate_seam as seam
from nexus.services.capability_registry import (
    SKIP_POLICY_NOT_TRIGGERED,
    build_escalate_gated_invoker,
    build_real_executor_invoker,
)

REAL_BARRIER = lane.os_sandbox_available()
# The confined lane runs ``python -I``: pytest must be importable without PYTHONPATH. Trusted CI
# executors put dependencies on PYTHONPATH only, so there the confined run is a real execution
# that fails with "No module named pytest" (still never simulated, never the hidden test).
PYTEST_UNDER_ISOLATION = (
    subprocess.run(
        [sys.executable, "-I", "-c", "import pytest"], capture_output=True, check=False
    ).returncode
    == 0
)
HIDDEN_MARKER = "HIDDEN_TEST_EXECUTED"
ORIGINAL = "def add(a, b):\n    return a - b\n"
CANDIDATE = "def add(a, b):\n    return a + b\n"


def _case(tmp_path: Path) -> Path:
    case = tmp_path / "workspace" / ".nexus" / "bench_cases" / "nexus-value-demo-001"
    case.mkdir(parents=True)
    (case / "target.py").write_text(ORIGINAL, encoding="utf-8")
    (case / "test_visible.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent))\n"
        "from target import add\n\n"
        "def test_add():\n"
        "    assert not (Path(__file__).parent / 'test_hidden.py').exists()\n"
        "    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    # Executing (or importing) the hidden test leaves a marker next to it.
    (case / "test_hidden.py").write_text(
        "from pathlib import Path\n"
        f"Path(__file__).with_name('{HIDDEN_MARKER}').write_text('x')\n"
        "def test_hidden():\n"
        "    assert False\n",
        encoding="utf-8",
    )
    return case


def _runtime_receipt(*names: str) -> dict[str, Any]:
    return {
        "task_id": "sprint-abc-s0-a1",
        "capabilities": [
            {
                "name": name,
                "status": "SKIPPED",
                "invoked": False,
                "skip_reason": SKIP_POLICY_NOT_TRIGGERED,
            }
            for name in names
        ],
    }


@pytest.fixture
def barrier(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every subprocess argv, recorded. Without a real OS barrier (Linux CI) the sandbox-exec
    prefix is stripped so the confined command still runs; with one it runs for real."""

    calls: list[list[str]] = []
    original_run = subprocess.run

    def recording_run(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        argv = [str(part) for part in cmd] if isinstance(cmd, (list, tuple)) else [str(cmd)]
        calls.append(argv)
        if argv and os.path.basename(argv[0]) == "sandbox-exec" and not REAL_BARRIER:
            cmd = list(cmd)[3:]
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    monkeypatch.setattr("nexus.engine.ultra_review_service.os_sandbox_available", lambda: True)
    return calls


def _no_hidden_in(calls: list[list[str]]) -> None:
    for argv in calls:
        assert not any(part.endswith("test_hidden.py") for part in argv), argv


def test_runtime_selected_untriggered_picks_only_policy_skipped_stages() -> None:
    receipt = {
        "capabilities": [
            {"name": "sandbox", "status": "SKIPPED", "skip_reason": SKIP_POLICY_NOT_TRIGGERED},
            {"name": "ultra_review", "status": "INVOKED", "invoked": True, "skip_reason": ""},
            {"name": "file_lock", "status": "SKIPPED", "skip_reason": "NOT_EXECUTABLE:x"},
            {"name": "hyper", "status": "SKIPPED", "skip_reason": SKIP_POLICY_NOT_TRIGGERED},
        ]
    }

    assert seam.runtime_selected_untriggered(receipt) == ["sandbox"]
    assert seam.runtime_selected_untriggered(None) == []
    assert seam.runtime_selected_untriggered(_runtime_receipt("file_lock", "sandbox")) == [
        "sandbox",
        "file_lock",
    ]


def test_preflight_gate_still_skips_candidate_dependent_capabilities() -> None:
    """The seam is the only place they run: the escalate gate is unchanged."""

    for name in seam.SEAM_CAPABILITIES:
        out = build_escalate_gated_invoker(name, real_invoker=lambda ctx: {"invoked": True})({
            "task_id": "t",
            "route": {"recommended_flow": "direct"},
        })
        assert out["invoked"] is False
        assert SKIP_POLICY_NOT_TRIGGERED in str(out.get("skip_reason") or out.get("reason"))


def test_scratch_copy_holds_candidate_and_visible_test_never_hidden(tmp_path: Path) -> None:
    case = _case(tmp_path)
    scratch = seam.prepare_candidate_scratch(
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        forbidden_paths=seam.hidden_test_paths(case / "test_visible.py"),
    )
    try:
        files = sorted(
            p.relative_to(scratch.root).as_posix()
            for p in scratch.root.rglob("*")
            if ".git" not in p.parts and p.name != seam.SCRATCH_PYTEST_CONFIG
        )
        assert files == ["target.py", "test_visible.py"]
        assert (scratch.root / "target.py").read_text(encoding="utf-8") == CANDIDATE
        committed = subprocess.run(
            ["git", "show", "HEAD:target.py"],
            cwd=scratch.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert committed == ORIGINAL
        assert scratch.candidate_sha256 == hashlib.sha256(CANDIDATE.encode()).hexdigest()
        assert scratch.forbidden_paths == ((case / "test_hidden.py").resolve(),)
        assert not scratch.root.resolve().is_relative_to(case.resolve())
    finally:
        scratch.cleanup()
    assert not scratch.root.exists()


def test_scratch_refuses_a_hidden_test_as_input(tmp_path: Path) -> None:
    case = _case(tmp_path)
    with pytest.raises(seam.PostCandidateSeamError):
        seam.prepare_candidate_scratch(
            target_path=case / "target.py",
            visible_test_path=case / "test_hidden.py",
            original_code=ORIGINAL,
            candidate_code=CANDIDATE,
        )


def test_sandbox_runs_visible_test_confined_with_real_receipt(
    tmp_path: Path, barrier: list[list[str]]
) -> None:
    case = _case(tmp_path)

    receipt = seam.run_seam_for_candidate(
        task_id="auto-flow:demo",
        unified_receipt=_runtime_receipt("sandbox"),
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
    )

    assert receipt is not None and receipt["receipt_kind"] == seam.POST_CANDIDATE_RECEIPT_KIND
    (stage,) = receipt["capabilities"]
    assert stage["name"] == "sandbox" and stage["status"] == "INVOKED" and stage["invoked"] is True
    assert stage["gate_passed"] is PYTEST_UNDER_ISOLATION, stage["outcome"]
    assert stage["simulated"] is False and stage["claim_boundary"]["simulated"] is False
    assert stage["trigger_source"] == "post_candidate_seam:post_candidate"
    outcome = stage["outcome"]
    if PYTEST_UNDER_ISOLATION:
        assert outcome["exit_code"] == 0
    else:
        assert outcome["exit_code"] != 0 and "pytest" in outcome["output_tail"]
    assert outcome["simulated"] is False and outcome["sandbox_executed"] is True
    assert outcome["network_allowed"] is False and outcome["confined"] is True
    assert outcome["forbidden_paths_count"] == 2  # hidden test + bench staging parent
    assert len(outcome["stdout_sha256"]) == 64
    pytest_argv = [argv for argv in barrier if "pytest" in argv]
    assert pytest_argv and all(argv[-1] == "test_visible.py" for argv in pytest_argv)
    _no_hidden_in(barrier)
    assert not (case / HIDDEN_MARKER).exists()
    assert (case / "test_hidden.py").is_file()


def test_sandbox_failing_candidate_is_a_real_failed_execution(
    tmp_path: Path, barrier: list[list[str]]
) -> None:
    case = _case(tmp_path)

    receipt = seam.run_seam_for_candidate(
        task_id="auto-flow:demo",
        unified_receipt=_runtime_receipt("sandbox"),
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code="def add(a, b):\n    return a * b\n",
    )

    (stage,) = receipt["capabilities"]
    assert stage["invoked"] is True and stage["gate_passed"] is False
    assert stage["simulated"] is False
    assert stage["outcome"]["exit_code"] not in (0, None)
    assert not (case / HIDDEN_MARKER).exists()


def test_confinement_forbidden_root_error_when_sandbox_would_hold_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """checked_read_roots refuses a readable root that contains the hidden test path."""

    case = _case(tmp_path)
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)

    with pytest.raises(SandboxError, match="sandbox_read_root_overbroad"):
        confinement(sandbox=case, extra_forbidden=[case / "test_hidden.py"])


def test_confined_runner_fails_closed_if_a_copy_leaks_the_hidden_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path)
    ran: list[Any] = []
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    monkeypatch.setattr(lane.Confinement, "run", lambda self, *a, **k: ran.append(a))

    def leaky_copy(source: Path, dest: Path, *, ignore_names: Any = ()) -> None:
        import shutil

        shutil.copytree(source, dest)  # simulated copy bug: ignores the hidden-test exclusion

    monkeypatch.setattr(confined_test_runner, "copy_tree_no_symlinks", leaky_copy)

    result = confined_test_runner.run_confined_test(
        case,
        command=["python", "-m", "pytest", "-q", "test_visible.py"],
        forbidden_paths=[case / "test_hidden.py"],
    )

    assert result["executed"] is False
    assert "sandbox_read_root_overbroad" in result["error"]
    assert ran == []
    assert not (case / HIDDEN_MARKER).exists()


def test_confined_runner_refuses_argv_naming_the_hidden_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path)
    ran: list[Any] = []
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    monkeypatch.setattr(lane.Confinement, "run", lambda self, *a, **k: ran.append(a))

    result = confined_test_runner.run_confined_test(
        case,
        command=["python", "-m", "pytest", "-q", "test_hidden.py"],
        forbidden_paths=[case / "test_hidden.py"],
    )

    assert result["executed"] is False
    assert "sandbox_argv_names_forbidden_path" in result["error"]
    assert ran == []


def test_without_os_barrier_sandbox_is_reported_not_executed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(tmp_path)
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: False)

    receipt = seam.run_seam_for_candidate(
        task_id="auto-flow:demo",
        unified_receipt=_runtime_receipt("sandbox"),
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
    )

    (stage,) = receipt["capabilities"]
    assert stage["gate_passed"] is False
    # No barrier -> nothing ran: a skip with the refusal reason, never INVOKED or real.
    assert stage["invoked"] is False and stage["status"] == "SKIPPED"
    assert stage["skip_reason"].startswith(seam.SKIPPED_SANDBOX_REFUSED)
    assert "no_os_barrier" in stage["skip_reason"]
    assert stage["simulated"] is True
    assert stage["outcome"]["sandbox_executed"] is False
    assert "no_os_barrier" in stage["outcome"]["error"]


def test_confinement_refusal_receipt_is_not_invoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MEDIUM: a refused confinement is reported by the executor as not invoked."""
    case = _case(tmp_path)
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    out = build_real_executor_invoker("sandbox")({
        "task_id": "t",
        "workspace_root": str(case),
        "sandbox_command": ["python", "-m", "pytest", "-q", "test_hidden.py"],
        "sandbox_forbidden_paths": [str(case / "test_hidden.py")],
    })

    assert out["invoked"] is False and out["gate_passed"] is False
    stage = seam.stage_from_invocation("sandbox", out, phase="post_candidate")
    assert stage["status"] == "SKIPPED" and stage["simulated"] is True
    assert "sandbox_argv_names_forbidden_path" in stage["skip_reason"]
    assert not (case / HIDDEN_MARKER).exists()


def test_real_barrier_or_refusal_on_this_host(tmp_path: Path) -> None:
    """Unpatched: a real sandbox-exec run on macOS, an honest refusal elsewhere."""

    case = _case(tmp_path)
    invoker = build_real_executor_invoker("sandbox")
    scratch = seam.prepare_candidate_scratch(
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        forbidden_paths=seam.hidden_test_paths(case / "test_visible.py"),
    )
    try:
        stage = seam.stage_from_invocation(
            "sandbox",
            invoker(seam.sandbox_context("auto-flow:demo", scratch)),
            phase="post_candidate",
        )
    finally:
        scratch.cleanup()
    if REAL_BARRIER:
        assert stage["simulated"] is False
        assert stage["gate_passed"] is PYTEST_UNDER_ISOLATION, stage["outcome"]
        assert (stage["outcome"]["exit_code"] == 0) is PYTEST_UNDER_ISOLATION
    else:
        assert stage["gate_passed"] is False and stage["simulated"] is True
    assert not (case / HIDDEN_MARKER).exists()


def test_ultra_review_post_candidate_reviews_scratch_and_excludes_hidden(
    tmp_path: Path, barrier: list[list[str]]
) -> None:
    case = _case(tmp_path)

    receipt = seam.run_seam_for_candidate(
        task_id="auto-flow:demo",
        unified_receipt=_runtime_receipt("ultra_review"),
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
    )

    (stage,) = receipt["capabilities"]
    assert stage["name"] == "ultra_review" and stage["invoked"] is True
    assert stage["simulated"] is False and stage["claim_boundary"]["simulated"] is False
    outcome = stage["outcome"]
    assert "test_hidden.py" not in outcome.get("regression_tests", [])
    assert "findings" in outcome
    _no_hidden_in(barrier)
    assert not (case / HIDDEN_MARKER).exists()


def test_ultra_review_mapped_tests_drop_excluded_hidden_test(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    for rel in ("pkg/test_hidden.py", "pkg/test_visible.py", "test_target.py"):
        (tmp_path / rel).write_text("def test_x():\n    pass\n", encoding="utf-8")
    service = UltraReviewService(tmp_path)

    kept, dropped = service._apply_explicit_regression_tests(
        ["pkg/test_hidden.py", "test_target.py"],
        regression_tests=["pkg/test_visible.py", "pkg/missing.py", "../escape.py"],
        excluded_tests=["test_hidden.py"],
    )

    assert kept == ["test_target.py", "pkg/test_visible.py"]
    assert dropped == ["pkg/test_hidden.py"]
    assert service._apply_explicit_regression_tests(["a.py"]) == (["a.py"], [])


def test_ultra_review_executor_forwards_seam_constraints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}

    class FakeService:
        def __init__(self, project_root: Path) -> None:
            seen["root"] = str(project_root)

        def run(self, **kwargs: Any) -> dict[str, Any]:
            seen.update(kwargs)
            return {"status": "PASS", "gate_passed": True, "fleet": [], "findings": []}

    monkeypatch.setattr("nexus.engine.ultra_review_service.UltraReviewService", FakeService)
    invoker = build_real_executor_invoker("ultra_review")
    invoker({
        "task_id": "t",
        "workspace_root": str(tmp_path),
        "ultra_review_regression_tests": ["test_visible.py"],
        "ultra_review_excluded_tests": ["test_hidden.py"],
    })

    assert seen["root"] == str(tmp_path)
    assert seen["regression_tests"] == ["test_visible.py"]
    assert seen["excluded_tests"] == ["test_hidden.py"]
    assert seen["dry_run"] is False


def test_file_lock_acquire_is_real_idempotent_and_released(tmp_path: Path) -> None:
    receipt = _runtime_receipt("file_lock")
    workspace = tmp_path / "ws"
    workspace.mkdir()

    task, stages = seam.lock_target_if_selected(
        unified_receipt=receipt,
        task_id="auto-flow:a",
        workspace_root=workspace,
        target_file="pkg/target.py",
    )
    try:
        assert task == "auto-flow:a"
        (stage,) = stages
        assert stage["invoked"] is True and stage["gate_passed"] is True
        assert (
            stage["simulated"] is False
            and stage["trigger_source"] == "post_candidate_seam:pre_attempt"
        )
        assert stage["outcome"]["access_granted"] is True

        # Same task re-acquires idempotently.
        again = seam.acquire_target_lock(
            task_id="auto-flow:a", workspace_root=workspace, target_file="pkg/target.py"
        )
        assert again["gate_passed"] is True
        # Another task is refused while held.
        other = seam.acquire_target_lock(
            task_id="auto-flow:b", workspace_root=workspace, target_file="pkg/target.py"
        )
        assert other["gate_passed"] is False
    finally:
        released = seam.release_target_lock("auto-flow:a")
    assert list(released.values()) == [["pkg/target.py"]]
    assert seam.release_target_lock("auto-flow:a") == {}
    after = seam.acquire_target_lock(
        task_id="auto-flow:b", workspace_root=workspace, target_file="pkg/target.py"
    )
    assert after["gate_passed"] is True
    seam.release_target_lock("auto-flow:b")


def test_file_lock_not_selected_acquires_nothing(tmp_path: Path) -> None:
    task, stages = seam.lock_target_if_selected(
        unified_receipt=_runtime_receipt("sandbox"),
        task_id="auto-flow:a",
        workspace_root=tmp_path,
        target_file="t.py",
    )
    assert (task, stages) == ("", [])
    assert not (tmp_path / ".nexus").exists()


def test_seam_disabled_by_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = _case(tmp_path)
    monkeypatch.setenv(seam.SEAM_DISABLE_ENV, "0")

    assert (
        seam.run_seam_for_candidate(
            task_id="t",
            unified_receipt=_runtime_receipt("sandbox", "ultra_review"),
            target_path=case / "target.py",
            visible_test_path=case / "test_visible.py",
            original_code=ORIGINAL,
            candidate_code=CANDIDATE,
        )
        is None
    )
    assert seam.lock_target_if_selected(
        unified_receipt=_runtime_receipt("file_lock"),
        task_id="t",
        workspace_root=tmp_path,
        target_file="t.py",
    ) == ("", [])


def test_no_candidate_or_nothing_selected_runs_nothing(tmp_path: Path) -> None:
    case = _case(tmp_path)
    common = {
        "task_id": "t",
        "target_path": case / "target.py",
        "visible_test_path": case / "test_visible.py",
        "original_code": ORIGINAL,
    }
    assert (
        seam.run_seam_for_candidate(
            unified_receipt=_runtime_receipt("sandbox"), candidate_code=ORIGINAL, **common
        )
        is None
    )
    assert (
        seam.run_seam_for_candidate(
            unified_receipt=_runtime_receipt("hyper"), candidate_code=CANDIDATE, **common
        )
        is None
    )


# --- strict/counted lane: the visible test itself runs confined -------------------------------

PROBING_VISIBLE_TEST = (
    "import os, sys\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, str(Path(__file__).parent))\n"
    "from target import add\n\n"
    "def test_add_and_probe():\n"
    "    assert add(1, 2) == 3\n"
    "    secret = Path(os.environ.get('PROBE_PARENT', '{parent}')) / 'run-x' / 'test_hidden.py'\n"
    "    assert secret.read_text() == 'never readable'\n"
)


def _probing_case(tmp_path: Path) -> tuple[Path, Path]:
    case = _case(tmp_path)
    parent = tmp_path / "cache" / "nexus-bench-hidden"
    (parent / "run-x").mkdir(parents=True)
    (parent / "run-x" / "test_hidden.py").write_text(
        "never readable", encoding="utf-8"
    )  # 0644 on purpose
    (case / "test_visible.py").write_text(
        PROBING_VISIBLE_TEST.replace("{parent}", str(parent)), encoding="utf-8"
    )
    return case, parent


def _probe_test(secret: Path) -> str:
    return (
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent))\n"
        "from target import add\n\n"
        "def test_add_and_probe():\n"
        "    assert add(1, 2) == 3\n"
        f"    assert Path({str(secret)!r}).read_text() == 'never readable'\n"
    )


@pytest.mark.parametrize("where", ["staging_parent", "artifacts", "other_task_fixture"])
def test_confined_visible_test_cannot_read_bench_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """Even world-readable files in the staging parent, the bench output tree or another task's
    fixture dir are out of reach of the visible test (default-deny + explicit forbidden roots)."""
    workspace = tmp_path / "ws"
    case = workspace / "bench_fixtures" / "online_ab_hard_v1" / "this-task"
    case.mkdir(parents=True)
    (case / "target.py").write_text(ORIGINAL, encoding="utf-8")
    parent = tmp_path / "cache" / "nexus-bench-hidden"
    secret = {
        "staging_parent": parent / "run-x" / "test_hidden.py",
        "artifacts": workspace
        / "artifacts"
        / "runtime"
        / "online_ab_v1"
        / "run"
        / "run_manifest.json",
        "other_task_fixture": workspace
        / "bench_fixtures"
        / "online_ab_hard_v1"
        / "other-task"
        / "test_hidden.py",
    }[where]
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("never readable", encoding="utf-8")  # 0644 on purpose
    (case / "test_visible.py").write_text(_probe_test(secret), encoding="utf-8")
    monkeypatch.setattr(seam, "BENCH_HIDDEN_STAGING_PARENT", parent)
    assert {
        workspace / ".nexus",
        workspace / "bench_fixtures",
        workspace / "artifacts",
        parent,
    } <= set(seam.bench_forbidden_roots(workspace))

    completed, executed = seam.run_visible_test_confined(
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        timeout_sec=60,
        workspace_root=workspace,
    )

    if REAL_BARRIER and PYTEST_UNDER_ISOLATION:
        assert executed is True
        assert completed.returncode != 0  # read denied -> the probe assertion fails
    elif not REAL_BARRIER:
        # No OS barrier (Linux CI): nothing runs, reported as not executed.
        assert executed is False and completed.returncode == 1
        assert completed.stderr.startswith(seam.CONFINEMENT_UNAVAILABLE)
    else:
        assert completed.returncode != 0
    # Control: the same probe unconfined does read the file (the check is meaningful).
    (case / "target.py").write_text(CANDIDATE, encoding="utf-8")
    control = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_visible.py"],
        cwd=case,
        capture_output=True,
        text=True,
        check=False,
    )
    assert control.returncode == 0, control.stdout[-400:]


def test_unconfined_run_of_the_same_probe_would_read_it(tmp_path: Path) -> None:
    """Control: outside the confinement the same probe does read the file (the test is meaningful)."""
    case, parent = _probing_case(tmp_path)
    (case / "target.py").write_text(CANDIDATE, encoding="utf-8")
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "test_visible.py",
            "-k",
            "probe",
        ],
        cwd=case,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stdout[-500:]


def test_rfs_visible_pytest_is_confined_under_the_counted_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.app import research_flow_service as rfs

    calls: list[dict[str, Any]] = []
    monkeypatch.setenv(seam.CONFINE_VISIBLE_TEST_ENV, "1")
    monkeypatch.setattr(
        seam,
        "run_visible_test_confined",
        lambda **kw: (
            calls.append(kw)
            or (
                subprocess.CompletedProcess([], 1, "", "confinement_unavailable:no_os_barrier"),
                False,
            )
        ),
    )
    monkeypatch.setattr(
        rfs.subprocess, "run", lambda *a, **k: pytest.fail("visible test ran unconfined")
    )
    res = rfs._run_visible_pytest(
        ["python", "-m", "pytest", "t.py"],
        repo_root=tmp_path,
        target_path=tmp_path / "target.py",
        test_path=tmp_path / "t.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        timeout_sec=5,
    )
    assert calls and calls[0]["candidate_code"] == CANDIDATE
    assert rfs._visible_error(res, "pytest_failed") == seam.CONFINEMENT_UNAVAILABLE


def test_sprint_inplace_executor_is_confined_under_the_counted_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research.sprint_service import InPlaceSprintExecutor

    case = _case(tmp_path)
    monkeypatch.setenv(seam.CONFINE_VISIBLE_TEST_ENV, "1")
    monkeypatch.setattr(
        seam,
        "run_visible_test_confined",
        lambda **kw: (
            subprocess.CompletedProcess([], 1, "", "confinement_unavailable:no_os_barrier"),
            False,
        ),
    )
    executor = InPlaceSprintExecutor(
        case, "target.py", [sys.executable, "-m", "pytest", "-q", "test_visible.py"], 30, task="t"
    )
    ev = executor.evaluate_candidate(seed=0, hint="h", code=CANDIDATE, source="llm")

    assert ev.score == 0.0 and ev.error.startswith(seam.CONFINEMENT_UNAVAILABLE)
    assert (case / "target.py").read_text(
        encoding="utf-8"
    ) == ORIGINAL  # never written in the workspace


def test_dead_process_seam_locks_are_swept_live_ones_kept(tmp_path: Path) -> None:
    """LOW-7: one holder id per task; a killed CLI's lock is swept, a live holder's is not."""
    import os as _os

    from nexus.orchestrator.file_lock_registry import FileLockRegistry

    lock_file = tmp_path / ".nexus" / "multi_agent" / "locks" / "file_locks.json"
    lock_file.parent.mkdir(parents=True)
    registry = FileLockRegistry(lock_file=str(lock_file))
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    registry.acquire(f"{seam.SEAM_LOCK_HOLDER_PREFIX}aaaa:{dead.pid}", ["a.py"])
    registry.acquire(f"{seam.SEAM_LOCK_HOLDER_PREFIX}bbbb:{_os.getppid()}", ["b.py"])
    registry.acquire("someone-else", ["c.py"])

    swept = seam.sweep_dead_seam_locks(tmp_path)

    assert swept == [f"{seam.SEAM_LOCK_HOLDER_PREFIX}aaaa:{dead.pid}"]
    after = FileLockRegistry(lock_file=str(lock_file)).locks
    assert set(after) == {"b.py", "c.py"}
    assert seam.seam_holder_id(tmp_path, "t.py") == seam.seam_holder_id(tmp_path, "t.py")
    assert seam.seam_holder_id(tmp_path, "t.py").endswith(f":{_os.getpid()}")


def test_counted_lane_hidden_verifier_is_confined_for_both_arms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MEDIUM-5: the runner's hidden verifier (bare and with-Nexus alike) runs on a confined
    copy under the counted lane; outside it the plain subprocess path is unchanged."""
    import scripts.bench.capability_ab_runner as runner

    case = _case(tmp_path)
    hidden = case / "test_hidden.py"
    confined: list[str] = []
    plain: list[list[str]] = []
    monkeypatch.setattr(
        runner,
        "_confined_test_run",
        lambda test, **kw: (
            confined.append(str(test)) or (subprocess.CompletedProcess([], 0, "", ""), True)
        ),
    )
    monkeypatch.setattr(
        runner,
        "_run_process_group_unstaged",
        lambda cmd, **kw: plain.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "1")
    runner._run_process_group(
        runner._pytest_verifier_cmd(str(hidden)), cwd=tmp_path, env={}, timeout_sec=5
    )
    runner._run_process_group(["nexus", "research:auto-flow"], cwd=tmp_path, env={}, timeout_sec=5)
    monkeypatch.setenv("NEXUS_CONFINE_VISIBLE_TEST", "0")
    runner._run_process_group(
        runner._pytest_verifier_cmd(str(hidden)), cwd=tmp_path, env={}, timeout_sec=5
    )

    assert confined == [str(hidden)]
    assert [cmd[-1] for cmd in plain] == ["research:auto-flow", str(hidden)]


def test_confined_hidden_verifier_cannot_read_outside_its_copy(tmp_path: Path) -> None:
    import scripts.bench.capability_ab_runner as runner

    case = _case(tmp_path)
    secret = tmp_path / "ws_secret.txt"
    secret.write_text("never readable", encoding="utf-8")
    (case / "target.py").write_text(CANDIDATE, encoding="utf-8")
    (case / "test_hidden.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent))\n"
        "from target import add\n\ndef test_h():\n    assert add(1, 2) == 3\n"
        f"    assert Path({str(secret)!r}).read_text() == 'never readable'\n",
        encoding="utf-8",
    )
    completed, executed = runner._confined_test_run(
        case / "test_hidden.py", workspace_root=tmp_path, timeout_sec=60
    )
    if REAL_BARRIER:
        assert executed is True and completed.returncode != 0
    else:
        assert executed is False and completed.stderr.startswith(seam.CONFINEMENT_UNAVAILABLE)
    assert (case / "test_hidden.py").is_file()  # the workspace copy is never touched


def test_scratch_copy_includes_sibling_helper_modules_never_hidden(tmp_path: Path) -> None:
    """LOW-6: sibling modules the visible test imports are in the confined copy."""
    case = _case(tmp_path)
    (case / "helpers.py").write_text("BASE = 1\n", encoding="utf-8")
    (case / ".secret").write_text("x", encoding="utf-8")
    scratch = seam.prepare_candidate_scratch(
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        forbidden_paths=seam.hidden_test_paths(case / "test_visible.py"),
    )
    try:
        assert scratch.files == ("helpers.py", "target.py", "test_visible.py")
        assert (scratch.root / "helpers.py").read_text(encoding="utf-8") == "BASE = 1\n"
        assert not (scratch.root / "test_hidden.py").exists()
        assert not (scratch.root / ".secret").exists()
    finally:
        scratch.cleanup()


def test_rfs_confined_visible_pytest_refuses_companion_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LOW-6: companion edits cannot be reproduced in the confined copy -> refused as
    ``confinement_unavailable:multi_file`` (not executed), never a spurious visible failure."""
    from nexus.app import research_flow_service as rfs

    monkeypatch.setenv(seam.CONFINE_VISIBLE_TEST_ENV, "1")
    monkeypatch.setattr(
        seam, "run_visible_test_confined", lambda **kw: pytest.fail("ran with companions")
    )
    monkeypatch.setattr(rfs.subprocess, "run", lambda *a, **k: pytest.fail("ran unconfined"))
    res = rfs._run_visible_pytest(
        ["python", "-m", "pytest", "t.py"],
        repo_root=tmp_path,
        target_path=tmp_path / "target.py",
        test_path=tmp_path / "t.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        timeout_sec=5,
        companion_files={tmp_path / "other.py": "x", tmp_path / "target.py": CANDIDATE},
    )
    assert res.returncode != 0
    assert rfs._visible_error(res, "pytest_failed") == "confinement_unavailable:multi_file"


def test_sprint_confined_executor_refuses_companion_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research import sprint_service
    from nexus.research.sprint_service import InPlaceSprintExecutor

    case = _case(tmp_path)
    monkeypatch.setenv(seam.CONFINE_VISIBLE_TEST_ENV, "1")
    monkeypatch.setattr(
        sprint_service,
        "generate_local_companion_edits",
        lambda *a, **k: {case / "other.py": "X = 1\n"},
    )
    monkeypatch.setattr(
        seam, "run_visible_test_confined", lambda **kw: pytest.fail("ran with companions")
    )
    executor = InPlaceSprintExecutor(
        case, "target.py", [sys.executable, "-m", "pytest", "-q", "test_visible.py"], 30, task="t"
    )
    ev = executor.evaluate_candidate(seed=0, hint="h", code=CANDIDATE, source="llm")

    assert ev.score == 0.0 and ev.error.startswith("confinement_unavailable:multi_file")
    assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL
    assert not (case / "other.py").exists()
