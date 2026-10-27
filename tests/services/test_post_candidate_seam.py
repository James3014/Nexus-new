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


def _assert_confining_profile(argv: list[str]) -> None:
    """Gemini G11: off macOS nothing can be confined for real, so the confinement claim is
    checked on the generated argv/SBPL profile instead (never "ran unconfined, passed"):
    the absolute barrier binary, default-deny, no network, $HOME read-denied, and no read
    allow for a hidden test, the bench staging parent, $HOME or an ancestor of it."""
    import re

    from nexus.services.post_candidate_seam import BENCH_HIDDEN_STAGING_PARENT

    assert argv[0] == lane.SANDBOX_EXEC and argv[1] == "-p", argv[:2]
    profile = argv[2]
    home = lane.sbpl_path(Path(os.path.expanduser("~")).resolve())
    assert "(deny default)" in profile and "(deny network*)" in profile
    assert f'(deny file-read* (subpath "{home}"))' in profile
    allows = " ".join(
        line for line in profile.splitlines() if line.startswith("(allow file-read* ")
    )
    staging = Path(lane.sbpl_path(BENCH_HIDDEN_STAGING_PARENT.resolve()))
    for root in re.findall(r'\(subpath "([^"]+)"\)', allows):
        assert "test_hidden" not in root, root
        assert root != home and not home.startswith(root.rstrip("/") + "/"), root
        assert Path(root) != staging and staging not in Path(root).parents, root


@pytest.fixture
def barrier(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every subprocess argv, recorded. With a real OS barrier the command runs confined.
    Without one (Linux CI) each sandbox-exec argv must carry a confining profile
    (``_assert_confining_profile``); only then is the prefix stripped so the wiring runs."""

    calls: list[list[str]] = []
    original_run = subprocess.run

    def recording_run(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        argv = [str(part) for part in cmd] if isinstance(cmd, (list, tuple)) else [str(cmd)]
        calls.append(argv)
        if argv and os.path.basename(argv[0]) == "sandbox-exec" and not REAL_BARRIER:
            # No barrier on this host: the confinement is asserted on the profile, then the
            # command runs only to exercise the wiring (never counted as confined).
            _assert_confining_profile(argv)
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
        command=["python", "-m", "pytest", "-q", "--", "test_visible.py"],
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


def test_seam_seals_real_invoked_evidence_for_the_stages_it_ran(
    tmp_path: Path, barrier: list[list[str]]
) -> None:
    """#2212 attestation: the seam ran the confined test itself, so each physically executed
    stage carries ``receipt_present`` plus a seam-sealed ``REAL_INVOKED`` bundle entry and a
    matching ``capability_results`` executor record (ids = the stage's evidence refs)."""
    case = _case(tmp_path)

    receipt = seam.run_seam_for_candidate(
        task_id="auto-flow:demo",
        unified_receipt=_runtime_receipt("sandbox", "ultra_review"),
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
    )

    assert receipt is not None
    stages = {stage["name"]: stage for stage in receipt["capabilities"]}
    entries = {e["name"]: e for e in receipt["capability_evidence_bundle"]["entries"]}
    assert set(entries) == set(stages) == {"sandbox", "ultra_review"}
    for name, stage in stages.items():
        assert stage["claim_boundary"]["receipt_present"] is True
        entry = entries[name]
        assert entry["status"] == "REAL_INVOKED" and entry["invoked_real"] is True
        assert entry["physical_callable"] == stage["physical_callable"] != ""
        assert entry["evidence_ids"] == stage["evidence_refs"] != []
        assert entry["sealed_by"] == seam.SEAM_EVIDENCE_SEALER
        record = receipt["capability_results"][name]
        assert record["evidence_refs"] == stage["evidence_refs"]
        assert record["response"]["outcome"] == stage["outcome"]
        assert record["response"]["outcome"]["semantic_status"]
    # The merged row receipt (file_lock + post-candidate) recomputes the seal from its stages.
    merged = seam.merge_seam_receipts(
        task_id="auto-flow:demo", pre_stages=[], post_receipt=receipt, released={}
    )
    assert merged["capability_evidence_bundle"] == receipt["capability_evidence_bundle"]


def test_seam_never_seals_unexecuted_stages_or_copied_in_bundles(
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
    assert stage["invoked"] is False and stage["claim_boundary"].get("receipt_present") is not True
    assert "capability_evidence_bundle" not in receipt and "capability_results" not in receipt

    forged = {"entries": [{"name": "sandbox", "status": "REAL_INVOKED", "evidence_ids": ["x"]}]}
    merged = seam.merge_seam_receipts(
        task_id="auto-flow:demo",
        pre_stages=[],
        post_receipt={**receipt, "capability_evidence_bundle": forged},
        released={},
    )
    assert "capability_evidence_bundle" not in merged  # never copied in, only recomputed
    direct = seam.post_candidate_receipt(
        task_id="t",
        stages=list(receipt["capabilities"]),
        extra={"capability_evidence_bundle": forged, "capability_results": {"sandbox": {}}},
    )
    assert "capability_evidence_bundle" not in direct and "capability_results" not in direct


def test_target_held_by_other_guards_in_place_writes_before_the_lock(tmp_path: Path) -> None:
    """Coordinator #3: a path that writes the candidate before the seam's own lock is taken
    (the runtime verifier) can ask whether another live holder has the target."""
    from nexus.orchestrator.file_lock_registry import FileLockRegistry

    workspace = tmp_path / "ws"
    workspace.mkdir()
    mine = seam.seam_holder_id(workspace, "pkg/target.py")
    assert seam.target_held_by_other(workspace, "pkg/target.py", mine) is False  # no registry
    other = seam.acquire_target_lock(
        task_id="other-task", workspace_root=workspace, target_file="pkg/target.py"
    )
    assert other["gate_passed"] is True
    try:
        assert seam.target_held_by_other(workspace, "pkg/target.py", mine) is True
        assert seam.target_held_by_other(workspace, "pkg/./target.py", mine) is True
        assert seam.target_held_by_other(workspace, "pkg/other.py", mine) is False
        assert seam.target_held_by_other(workspace, "pkg/target.py", "other-task") is False
    finally:
        seam.release_target_lock("other-task")
    assert seam.target_held_by_other(workspace, "pkg/target.py", mine) is False
    # A stale lock (older than the executor TTL) does not block, exactly like acquire.
    lock_file = workspace / ".nexus" / "multi_agent" / "locks" / "file_locks.json"
    registry = FileLockRegistry(lock_file=str(lock_file))
    registry.acquire("old-task", ["pkg/target.py"])
    data = __import__("json").loads(lock_file.read_text(encoding="utf-8"))
    data["acquired_at"]["pkg/target.py"] = 0.0
    lock_file.write_text(__import__("json").dumps(data), encoding="utf-8")
    assert seam.target_held_by_other(workspace, "pkg/target.py", mine) is False
    # An unreadable registry fails closed (treated as held).
    lock_file.chmod(0o000)
    try:
        if not os.access(lock_file, os.R_OK):
            assert seam.target_held_by_other(workspace, "pkg/target.py", mine) is True
    finally:
        lock_file.chmod(0o600)


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
    """#2339 follow-up: the fixture-keyed companion edits were deleted with the local answer
    table, so a confined evaluation only ever carries the target and is never refused as
    multi-file; nothing outside the target is written."""
    from nexus.research import sprint_service
    from nexus.research.sprint_service import InPlaceSprintExecutor

    assert not hasattr(sprint_service, "generate_local_companion_edits")
    case = _case(tmp_path)
    monkeypatch.setenv(seam.CONFINE_VISIBLE_TEST_ENV, "1")
    calls: list[dict] = []

    def fake_confined(**kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(["pytest"], 0, "", ""), True

    monkeypatch.setattr(seam, "run_visible_test_confined", fake_confined)
    executor = InPlaceSprintExecutor(
        case, "target.py", [sys.executable, "-m", "pytest", "-q", "test_visible.py"], 30, task="t"
    )
    ev = executor.evaluate_candidate(seed=0, hint="h", code=CANDIDATE, source="llm")

    assert not (ev.error or "").startswith("confinement_unavailable:multi_file")
    assert len(calls) == 1 and calls[0]["candidate_code"] == CANDIDATE
    assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL
    assert not (case / "other.py").exists()


def test_non_python_sandbox_command_is_confined_too(
    tmp_path: Path, barrier: list[list[str]]
) -> None:
    """Coordinator #6: any ``sandbox_command`` routed by ``sandbox_forbidden_paths`` (here a
    non-python argv[0]) runs under the OS confinement and cannot read outside its copy."""
    case = _case(tmp_path)
    secret = tmp_path / "outside_secret.txt"
    secret.write_text("SECRET_OUTSIDE_7c1", encoding="utf-8")
    cat = "/bin/cat" if os.path.exists("/bin/cat") else "/usr/bin/cat"
    out = build_real_executor_invoker("sandbox")({
        "task_id": "t",
        "workspace_root": str(case),
        "sandbox_command": [cat, str(secret)],
        "sandbox_forbidden_paths": [str(case / "test_hidden.py")],
    })

    cat_runs = [argv for argv in barrier if cat in argv]
    assert cat_runs, barrier
    assert all(os.path.basename(argv[0]) == "sandbox-exec" for argv in cat_runs), cat_runs
    outcome = out["response"]["outcome"]
    assert outcome["confined"] is True
    if REAL_BARRIER:
        assert outcome["exit_code"] != 0
        assert "SECRET_OUTSIDE_7c1" not in str(outcome.get("output_tail") or "")


def test_read_root_inside_a_forbidden_root_is_refused_both_directions(tmp_path: Path) -> None:
    """Gemini G1: a read root equal to, containing, or INSIDE an explicitly forbidden root is
    refused (a later SBPL allow rule would otherwise re-open the forbidden subtree)."""
    forbidden = tmp_path / "forbidden"
    (forbidden / "sub").mkdir(parents=True)
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    staging = seam.BENCH_HIDDEN_STAGING_PARENT
    for root, bad in (
        (forbidden, forbidden),
        (tmp_path, forbidden),  # ancestor of the forbidden root
        (forbidden / "sub", forbidden),  # descendant of the forbidden root
        (staging / "run-x", staging),  # inside the bench hidden-test staging parent
    ):
        with pytest.raises(SandboxError):
            lane.checked_read_roots([str(root)], forbidden_subtrees=[bad])
    assert lane.sbpl_path(sibling) in lane.checked_read_roots(
        [str(sibling)], forbidden_subtrees=[forbidden]
    )
    # A repository-root style ``extra_forbidden`` still allows roots below it (venv/worktree).
    assert lane.sbpl_path(forbidden / "sub") in lane.checked_read_roots(
        [str(forbidden / "sub")], extra_forbidden=[forbidden]
    )
    # The profile denies forbidden subtrees last (after every allow rule).
    profile = lane.build_sandbox_profile(
        writable=[str(sibling)], read_roots=[str(sibling)], deny_subtrees=[staging]
    )
    assert profile.splitlines()[-1] == (
        f'(deny file-read* (subpath "{lane.sbpl_path(staging.resolve())}"))'
    )


def test_inplace_executor_refuses_while_another_task_holds_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gemini G7: the unconfined in-place evaluation never writes a target another task holds."""
    from nexus.research.sprint_service import InPlaceSprintExecutor

    case = _case(tmp_path)
    monkeypatch.delenv(seam.CONFINE_VISIBLE_TEST_ENV, raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("test ran"))
    executor = InPlaceSprintExecutor(
        case, "target.py", [sys.executable, "-m", "pytest", "-q", "test_visible.py"], 30, task="t"
    )
    seam.acquire_target_lock(task_id="other-task", workspace_root=case, target_file="target.py")
    try:
        ev = executor.evaluate_candidate(seed=0, hint="h", code=CANDIDATE, source="llm")
        assert ev.score == 0.0 and ev.error == "file_lock_denied"
        # Reviewer L5: the confined path (the #2212 verifier, which memoises results) never
        # returns a cacheable denial; it stops the sprint attempt.
        from nexus.research.sprint_service import _SprintLockDenied

        with pytest.raises(_SprintLockDenied):
            executor.evaluate_candidate_confined(seed=0, hint="h", code=CANDIDATE, source="llm")
    finally:
        seam.release_target_lock("other-task")
    assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL


def test_evaluate_candidate_confined_always_confined_never_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2212 contract: evaluate_candidate_confined routes to the confined runner even when the
    counted-lane env is off, and refuses (never in place) when confinement is unavailable."""
    from nexus.research.sprint_service import InPlaceSprintExecutor

    case = _case(tmp_path)
    monkeypatch.delenv(seam.CONFINE_VISIBLE_TEST_ENV, raising=False)
    calls: list[dict[str, Any]] = []

    def confined(**kw: Any):
        calls.append(kw)
        assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL
        return subprocess.CompletedProcess(
            [], 1, "", "confinement_unavailable:no_os_barrier"
        ), False

    monkeypatch.setattr(seam, "run_visible_test_confined", confined)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("ran in place"))
    executor = InPlaceSprintExecutor(
        case, "target.py", [sys.executable, "-m", "pytest", "-q", "test_visible.py"], 30, task="t"
    )
    ev = executor.evaluate_candidate_confined(seed=3, hint="h", code=CANDIDATE, source="llm")

    assert calls and calls[0]["candidate_code"] == CANDIDATE
    assert ev.score == 0.0 and ev.error.startswith(seam.CONFINEMENT_UNAVAILABLE)
    assert ev.seed == 3 and ev.source == "llm"
    assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL


@pytest.mark.parametrize(
    "extra",
    [
        ["-o", "python_files=test_hidden.py"],
        ["-opython_files=test_hidden.py"],  # attached short value
        ["-k", "test_hidden"],
        ["-xk", "test_hidden"],  # combined short flags
        ["--override-ini=python_files=*.py"],
        ["--over=python_files=*.py"],  # argparse abbreviation
        ["--maxf=1"],  # abbreviation of an allowed option
        ["--maxfail", "1"],  # space form of an allowed "=" option
        ["--rootdir", "."],
        ["--rootdir=/"],
        ["--rootdir=-x"],  # value starting with "-"
        ["-p", "evil_plugin"],
        ["-pevil_plugin"],
        ["-p", "no:cacheprovider"],  # space form of an allowed attached option
        ["-c", "/etc/pytest.ini"],
        ["--config-file=/etc/pytest.ini"],
        ["--pyargs"],
        ["--", "-k"],  # a second token after "--"
        ["--", "other.py"],
    ],
)
def test_confined_runner_refuses_unlisted_pytest_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: list[str]
) -> None:
    """Gemini G8 (+ parser-differential addendum): the confined command has one exact grammar
    (python -I -m pytest <exact allowed tokens> -- <one path>), so no token shape pytest's
    argparse would read differently gets through. Refused before any sandbox is built, so
    this holds on every platform."""
    case = _case(tmp_path)
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    monkeypatch.setattr(
        confined_test_runner, "confinement", lambda **kw: pytest.fail("reached the sandbox")
    )
    base = [sys.executable, "-I", "-m", "pytest", "-q", *seam.PINNED_PYTEST_ARGS]
    assert confined_test_runner._refused_option_parts([*base, "--", "test_visible.py"]) == []
    result = confined_test_runner.run_confined_test(
        case,
        command=[*base, *extra, "--", "test_visible.py"],
        forbidden_paths=[case / "test_hidden.py"],
    )
    assert result["executed"] is False
    assert "sandbox_argv_option_refused" in result["error"]


@pytest.mark.parametrize(
    "argv_tail",
    [
        ["-q", "test_visible.py"],  # no "--"
        ["-q", "--", "-test_visible.py"],  # path starting with "-"
        ["-q", "--"],  # no path
    ],
)
def test_confined_runner_requires_one_double_dash_path(argv_tail: list[str]) -> None:
    argv = [sys.executable, "-I", "-m", "pytest", *argv_tail]
    assert confined_test_runner._refused_option_parts(argv) != []
    # Non-python programs carry no option tokens at all.
    assert confined_test_runner._refused_option_parts(["/bin/cat", "-n", "x"]) == ["-n"]
    assert confined_test_runner._refused_option_parts(["/bin/cat", "x"]) == []
    assert (
        confined_test_runner._refused_option_parts([sys.executable, "-I", "-c", "print(1)"]) != []
    )


def test_every_seam_and_bench_test_command_separates_the_path_with_double_dash(
    tmp_path: Path,
) -> None:
    """Gemini G8: the test path is always after "--" (never parsed as a pytest option) and the
    pinned commands pass the option allowlist."""
    import scripts.bench.capability_ab_runner as runner

    case = _case(tmp_path)
    scratch = seam.prepare_candidate_scratch(
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
    )
    try:
        sandbox_argv = seam.sandbox_context("t", scratch)["sandbox_command"]
    finally:
        scratch.cleanup()
    verifier = runner._pytest_verifier_cmd(str(case / "test_hidden.py"))
    for argv in (sandbox_argv, verifier):
        assert argv[-2] == "--"
        trusted = confined_test_runner._trusted_argv(argv)  # what the runner would execute
        assert confined_test_runner._refused_option_parts(trusted) == []
    assert runner._is_hidden_verifier_cmd(verifier)


def test_relative_and_absolute_spellings_lock_the_same_file(tmp_path: Path) -> None:
    """Gemini G12: one canonical registry key per file (workspace-relative inside it)."""
    workspace = tmp_path / "ws"
    (workspace / "pkg").mkdir(parents=True)
    first = seam.acquire_target_lock(
        task_id="task-a", workspace_root=workspace, target_file="pkg/target.py"
    )
    try:
        assert first["gate_passed"] is True
        for spelling in (
            str(workspace / "pkg" / "target.py"),
            "./pkg/target.py",
            "pkg/../pkg/target.py",
        ):
            other = seam.acquire_target_lock(
                task_id="task-b", workspace_root=workspace, target_file=spelling
            )
            assert other["gate_passed"] is False, spelling
            assert seam.target_held_by_other(workspace, spelling, "task-b") is True
    finally:
        released = seam.release_target_lock("task-a")
    assert list(released.values()) == [["pkg/target.py"]]
    seam.release_target_lock("task-b")


def test_seam_holder_id_is_the_same_for_every_spelling_of_the_target(tmp_path: Path) -> None:
    """Reviewer L3: the holder id uses the canonical lock key, so a sprint and a baseline
    path that spell the target differently are one holder, not two."""
    workspace = tmp_path / "ws"
    (workspace / "pkg").mkdir(parents=True)
    ids = {
        seam.seam_holder_id(workspace, spelling)
        for spelling in (
            "pkg/target.py",
            "./pkg/target.py",
            "pkg/../pkg/target.py",
            str(workspace / "pkg" / "target.py"),
        )
    }
    assert len(ids) == 1
    assert seam.seam_holder_id(workspace, "pkg/other.py") not in ids


@pytest.mark.parametrize(
    ("value", "enabled"),
    [
        ("1", True),
        (" 1 ", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("", False),
    ],
)
def test_confine_visible_test_env_accepts_only_1(
    monkeypatch: pytest.MonkeyPatch, value: str, enabled: bool
) -> None:
    """Reviewer L6 + Gemini N2: ONE parse everywhere. "1" confines; "" / "0" is off; any other
    spelling routes to the confined path (never unconfined) and the confined runner refuses
    it, so a spelling can never make one side confined and the other unconfined."""
    import scripts.bench.capability_ab_runner as runner

    monkeypatch.setenv(seam.CONFINE_VISIBLE_TEST_ENV, value)
    assert seam.confine_visible_test_enabled() is enabled
    assert runner._counted_confinement_enabled() is enabled
    assert seam.confine_visible_test_env_valid() is (value.strip() in {"", "0", "1"})


def test_run_under_target_lock_holds_the_lock_across_the_write(tmp_path: Path) -> None:
    """Reviewer L1: check-then-write is replaced by acquire -> write -> release."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    seen: list[bool] = []

    def write() -> None:
        # While writing, nobody else can take the target.
        other = seam.acquire_target_lock(
            task_id="other-task", workspace_root=workspace, target_file="t.py"
        )
        seen.append(other["gate_passed"])

    assert seam.run_under_target_lock(workspace, "t.py", write) is True
    assert seen == [False]
    assert seam.target_held_by_other(workspace, "t.py", "other-task") is False  # released
    seam.acquire_target_lock(task_id="other-task", workspace_root=workspace, target_file="t.py")
    try:
        assert seam.run_under_target_lock(workspace, "./t.py", lambda: seen.append(True)) is False
        assert seen == [False]  # the write never ran
    finally:
        seam.release_target_lock("other-task")


@pytest.mark.parametrize("spelling", ["true", "yes", "on"])
def test_ambiguous_confine_env_never_runs_the_hidden_verifier_unconfined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    """Gemini N2: NEXUS_CONFINE_VISIBLE_TEST=true no longer sends the runner's hidden verifier
    to the unconfined subprocess; the confined runner refuses the spelling (fail closed)."""
    import scripts.bench.capability_ab_runner as runner

    case = _case(tmp_path)
    monkeypatch.setenv(seam.CONFINE_VISIBLE_TEST_ENV, spelling)
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    monkeypatch.setattr(
        runner, "_run_process_group_unstaged", lambda *a, **k: pytest.fail("ran unconfined")
    )
    completed = runner._run_process_group(
        runner._pytest_verifier_cmd(str(case / "test_hidden.py")),
        cwd=tmp_path,
        env={},
        timeout_sec=5,
    )
    assert completed.returncode != 0
    assert "confinement_unavailable" in completed.stderr and "ambiguous_env" in completed.stderr
    assert not (case / HIDDEN_MARKER).exists()


def test_companion_file_held_by_another_task_refuses_the_whole_write(tmp_path: Path) -> None:
    """Gemini N3: the lock covers every companion file too (all or nothing); the release only
    drops what this call took, so the seam's own file_lock on the target stays held."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    holder = seam.seam_holder_id(workspace, "t.py")
    seam.acquire_target_lock(task_id=holder, workspace_root=workspace, target_file="t.py")
    seam.acquire_target_lock(task_id="other-task", workspace_root=workspace, target_file="c.py")
    try:
        assert seam.hold_target_lock(workspace, "t.py", [workspace / "c.py"]) is None
        release = seam.hold_target_lock(workspace, "t.py", [workspace / "d.py"])
        assert release is not None
        assert seam.target_held_by_other(workspace, "d.py", "x") is True
        release()
        assert seam.target_held_by_other(workspace, "d.py", "x") is False  # released
        assert seam.target_held_by_other(workspace, "t.py", "x") is True  # seam lock kept
    finally:
        seam.release_target_lock(holder)
        seam.release_target_lock("other-task")


def test_sprint_inplace_executor_refuses_when_a_companion_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2339 follow-up: no companion edits exist any more, so a lock another task holds on an
    unrelated file neither blocks the target-only evaluation nor gets that file written."""
    from nexus.research import sprint_service
    from nexus.research.sprint_service import InPlaceSprintExecutor

    assert not hasattr(sprint_service, "generate_local_companion_edits")
    case = _case(tmp_path)
    monkeypatch.delenv(seam.CONFINE_VISIBLE_TEST_ENV, raising=False)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", "")
    )
    seam.acquire_target_lock(task_id="other-task", workspace_root=case, target_file="helper.py")
    try:
        executor = InPlaceSprintExecutor(
            case, "target.py", [sys.executable, "-m", "pytest", "-q", "test_visible.py"], 30
        )
        ev = executor.evaluate_candidate(seed=0, hint="h", code=CANDIDATE, source="llm")
    finally:
        seam.release_target_lock("other-task")
    assert ev.error != "file_lock_denied" and ev.score == 1.0
    assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL
    assert not (case / "helper.py").exists()


def test_sprint_inplace_evaluation_holds_the_lock_from_write_to_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scanner TOCTOU (sprint): no separate pre-check; our lock is held while the candidate
    sits in the workspace and the test runs, and released after the restore."""
    from nexus.research.sprint_service import InPlaceSprintExecutor

    case = _case(tmp_path)
    monkeypatch.delenv(seam.CONFINE_VISIBLE_TEST_ENV, raising=False)
    during: list[bool] = []

    def fake_run(*a: Any, **k: Any) -> subprocess.CompletedProcess:
        other = seam.acquire_target_lock(
            task_id="other-task", workspace_root=case, target_file="target.py"
        )
        during.append(other["gate_passed"])
        return subprocess.CompletedProcess(a[0], 0, "1 passed", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    executor = InPlaceSprintExecutor(
        case, "target.py", [sys.executable, "-m", "pytest", "-q", "test_visible.py"], 30
    )
    ev = executor.evaluate_candidate(seed=0, hint="h", code=CANDIDATE, source="llm")
    assert ev.score == 1.0 and during == [False]
    assert seam.target_held_by_other(case, "target.py", "other-task") is False  # released
    assert (case / "target.py").read_text(encoding="utf-8") == ORIGINAL  # restored


def test_every_confinement_call_site_is_known_and_protects_the_bench_subtrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gemini N1, proven: (a) the confinement() call sites are exactly the known ones; the
    seam/bench one (run_confined_test) passes the hidden tests, the staging parent, .nexus,
    bench_fixtures, artifacts and .git as forbidden SUBTREES; the staging parent is also denied
    by the last rule of EVERY profile (committee/swarm/ultra_review included); (b) its read
    roots are the sandbox, the interpreter prefixes and the TOOLCHAIN constant, never input."""
    import re as _re

    repo = Path(__file__).resolve().parents[2]
    sites = sorted(
        str(path.relative_to(repo))
        for top in ("nexus", "scripts")
        for path in (repo / top).rglob("*.py")
        if _re.search(r"(?<![\w.])(?:lane\.)?confinement\(", path.read_text(encoding="utf-8"))
        and "def confinement(" not in path.read_text(encoding="utf-8")
    )
    assert sites == [
        "nexus/committee/execution_verifier.py",
        "nexus/engine/confined_test_runner.py",
        # #2936: local-model output (drone BASH, local_heal verifiers). Its profile denies the
        # staging parent through the shared SANDBOX_DENIED_HOME_PATHS rule; every rule after
        # that one is a deny (test_model_output_sandbox_2936 proves it live).
        "nexus/engine/model_output_sandbox.py",
        "nexus/engine/swarm_run.py",
    ], sites

    case = _case(tmp_path)
    workspace = tmp_path / "workspace"
    captured: dict[str, Any] = {}

    def capture(**kwargs: Any):
        captured.update(kwargs)
        raise SandboxError("captured")

    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    monkeypatch.setattr(confined_test_runner, "confinement", capture)
    seam.run_visible_test_confined(
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        timeout_sec=5,
        workspace_root=workspace,
    )
    subtrees = {Path(p).resolve() for p in captured["forbidden_subtrees"]}
    for required in (
        case / "test_hidden.py",
        seam.BENCH_HIDDEN_STAGING_PARENT,
        workspace / ".nexus",
        workspace / "bench_fixtures",
        workspace / "artifacts",
        workspace / ".git",
    ):
        assert Path(required).resolve() in subtrees, required
    assert captured["extra_readable"] is confined_test_runner.TOOLCHAIN_READ_ROOTS

    profile = lane.build_sandbox_profile(writable=[str(tmp_path)], read_roots=[str(tmp_path)])
    staging = lane.sbpl_path(Path.home().resolve() / ".cache" / "nexus-bench-hidden")
    assert f'(subpath "{staging}")' in profile.splitlines()[-1]  # last rule: denied for all


def test_sprint_evaluation_releases_the_lock_when_reading_the_target_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reviewer L-b: the target read happens inside the try, so a failure there still releases
    the lock (no leak until the TTL)."""
    from nexus.research.sprint_service import InPlaceSprintExecutor

    case = _case(tmp_path)
    monkeypatch.delenv(seam.CONFINE_VISIBLE_TEST_ENV, raising=False)
    real_read = Path.read_text

    def failing_read(self: Path, *a: Any, **k: Any) -> str:
        if self.name == "target.py":
            raise OSError(5, "I/O error")
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", failing_read)
    executor = InPlaceSprintExecutor(
        case, "target.py", [sys.executable, "-m", "pytest", "-q", "test_visible.py"], 30
    )
    ev = executor.evaluate_candidate(seed=0, hint="h", code=CANDIDATE, source="llm")
    monkeypatch.setattr(Path, "read_text", real_read)
    assert ev.score == 0.0 and "I/O error" in ev.error
    other = seam.acquire_target_lock(
        task_id="other-task", workspace_root=case, target_file="target.py"
    )
    try:
        assert other["gate_passed"] is True  # our lock was released
    finally:
        seam.release_target_lock("other-task")


def test_lock_denial_from_the_executor_reports_the_counts_spent_so_far(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reviewer L-c: a denial raised deep inside the sprint (evaluate_candidate_confined)
    carries the model calls / tokens metered so far into the denied result."""
    import nexus.research.sprint_service as sprint

    def core(*, repo_root: Path, config: Any):
        sprint._SPRINT_METER.set(
            lambda: {"model_calls": 3, "total_tokens": 1234, "model_name": "m"}
        )
        raise sprint._SprintLockDenied(lock_denied_in="runtime_verifier")

    monkeypatch.setattr(sprint, "_run_hyper_sprint_core", core)
    (tmp_path / "t.py").write_text("x = 1\n", encoding="utf-8")
    result = sprint.run_hyper_sprint(
        repo_root=tmp_path, config=sprint.SprintConfig(task="t", target_file="t.py")
    )
    assert result.reason == "file_lock_denied"
    assert result.model_calls == 3 and result.total_tokens == 1234 and result.model_name == "m"
    assert sprint._SPRINT_METER.get() is None  # reset after the sprint


def test_seam_stage_with_a_succeeded_physical_outcome_attests_real(tmp_path: Path) -> None:
    """Reviewer L-d (environment independent): a seam stage whose executor returns a
    SUCCEEDED physical outcome is attested "real" by #2212's merged projection, so Linux CI
    proves the seam CAN produce a real claim, not only that it never claims one falsely."""
    from nexus.research.flow.unified_capability_projection import (
        overlay_unified_capability_receipts,
        project_unified_capability_stages,
    )

    case = _case(tmp_path)

    def factory(name: str):
        def invoke(context: Any) -> dict[str, Any]:
            return {
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": [f"ev_{name}_fake_run_001"],
                "physical_callable": f"tests.fake.{name}",
                "response": {
                    "status": "SUCCEEDED",
                    "outcome": {
                        "semantic_status": "SUCCEEDED",
                        "exit_code": 0,
                        "stdout_sha256": "ab" * 32,
                        "output_tail": "1 passed",
                        "simulated": False,
                        "sandbox_executed": True,
                        "confined": True,
                        "executed_checks": ["visible_test"],
                        "result": "PASS",
                    },
                },
            }

        return invoke

    receipt = seam.run_seam_for_candidate(
        task_id="auto-flow:demo",
        unified_receipt=_runtime_receipt("sandbox", "ultra_review"),
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=ORIGINAL,
        candidate_code=CANDIDATE,
        invoker_factory=factory,
    )
    assert receipt is not None
    stages = project_unified_capability_stages([receipt])
    flow = overlay_unified_capability_receipts(
        [{"name": n, "selected": True, "invoked": False} for n in ("sandbox", "ultra_review")],
        stages,
    )
    for row in flow:
        assert row["invoked"] is True
        assert row.get("attestation") == "real", row
        assert row["claim_boundary"]["simulated"] is False
