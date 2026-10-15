"""PR-2 parity: every counted-lane visible test behaves the same confined and unconfined.

The with-Nexus arm runs the visible test inside ``sandboxed_lane.confinement`` under the counted
lane; the bare arm never runs it. A fixture whose visible test passes unconfined but errors
confined (e.g. it shells out to ``git``) would give the with-Nexus arm a bogus failure, so every
P16 and hard_v1 visible test must reach the same verdict both ways. Without an OS barrier the
confined run never executes, and the runner then excludes every task symmetrically.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import nexus.engine.sandboxed_lane as lane
from nexus.services import post_candidate_seam as seam
from scripts.bench.capability_ab_runner import _materialize_fixture, load_tasks

REPO = Path(__file__).resolve().parents[2]
REAL_BARRIER = lane.os_sandbox_available()


def _p16_cases(root: Path) -> list[tuple[str, Path, Path]]:
    cases = []
    for task in load_tasks(REPO / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json"):
        if not task.fixture_kind:
            continue
        try:
            target, visible = _materialize_fixture(root, task)
        except (ValueError, NotImplementedError):
            continue
        cases.append((task.id, Path(target), Path(visible)))
    return cases


def _hard_cases(root: Path) -> list[tuple[str, Path, Path]]:
    data = json.loads(
        (REPO / "tests" / "benchmark" / "data" / "online_ab_hard_v1_prompt_data.json").read_text()
    )
    cases = []
    for task in data["tasks"]:
        case = root / "bench_fixtures" / "online_ab_hard_v1" / task["id"]
        case.mkdir(parents=True)
        (case / "target.py").write_text(task["source"], encoding="utf-8")
        (case / "test_visible.py").write_text(task["visible_test"], encoding="utf-8")
        cases.append((task["id"], case / "target.py", case / "test_visible.py"))
    return cases


def _unconfined(root: Path, visible: Path) -> bool:
    # Exactly how the product runs the visible test outside the counted lane.
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--maxfail=1",
            "-p",
            "no:cacheprovider",
            str(visible),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    return out.returncode == 0


def test_every_counted_visible_test_has_the_same_verdict_confined_and_unconfined(
    tmp_path: Path,
) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    cases = _p16_cases(root) + _hard_cases(root)
    assert len(cases) >= 20

    mismatches = []
    not_executed = []
    for task_id, target, visible in cases:
        original = target.read_text(encoding="utf-8")

        def confined() -> tuple[bool, bool, str]:
            completed, executed = seam.run_visible_test_confined(
                target_path=target,
                visible_test_path=visible,
                original_code=original,
                candidate_code=original,
                timeout_sec=300,
                workspace_root=root,
            )
            return (
                completed.returncode == 0,
                executed,
                completed.stdout[-400:] + completed.stderr[-300:],
            )

        ok, executed, tail = confined()
        if not executed:
            not_executed.append(task_id)
            continue
        if ok != _unconfined(root, visible):
            # Re-run both once: timing-bound tests (e.g. a 1.5 s budget) can flake either way.
            ok, executed, tail = confined()
            if ok != _unconfined(root, visible):
                mismatches.append((task_id, tail))

    if REAL_BARRIER:
        assert not_executed == []
        assert mismatches == [], mismatches
    else:
        # No barrier (Linux CI): nothing runs confined; the runner excludes all tasks symmetrically.
        assert set(not_executed) == {task_id for task_id, _t, _v in cases}


@pytest.mark.parametrize("where", ["tmpdir_ancestor"])
def test_planted_pytest_ini_outside_the_scratch_copy_is_never_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """--rootdir/-c pin: a pytest.ini planted in a $TMPDIR ancestor neither crashes nor alters it."""
    tmp_root = tmp_path / "tmproot"
    (tmp_root / "inner").mkdir(parents=True)
    (tmp_root / "pytest.ini").write_text(
        "[pytest]\naddopts = --definitely-not-an-option\n", encoding="utf-8"
    )
    monkeypatch.setenv("TMPDIR", str(tmp_root / "inner"))
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", None)
    case = tmp_path / "case"
    case.mkdir()
    (case / "target.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (case / "test_visible.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent))\n"
        "from target import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    original = (case / "target.py").read_text(encoding="utf-8")

    completed, executed = seam.run_visible_test_confined(
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code=original,
        candidate_code=original,
        timeout_sec=60,
    )

    assert "--definitely-not-an-option" not in completed.stderr
    if executed:
        assert completed.returncode == 0, completed.stdout[-400:] + completed.stderr[-400:]


def _parity_task(root: Path, visible: str) -> object:
    from scripts.bench.capability_ab_runner import CapabilityTask

    case = root / "bench_fixtures" / "demo"
    case.mkdir(parents=True)
    (case / "target.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (case / "test_visible.py").write_text(visible, encoding="utf-8")
    return CapabilityTask(
        id="parity-demo",
        difficulty="easy",
        task_type="public_bugfix",
        category="bugfix",
        repo_kind="neutral_fixture",
        task_desc="d",
        target_file="bench_fixtures/demo/target.py",
        test_file="bench_fixtures/demo/test_visible.py",
        success_criteria="s",
    )


VISIBLE_OK = (
    "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent))\n"
    "from target import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
)


@pytest.mark.parametrize(
    ("confined_rc", "executed", "expected"),
    [
        (1, True, "visible_verdict_differs"),
        (1, False, "visible:confinement_unavailable"),
        (0, True, None),
    ],
)
def test_parity_preflight_excludes_a_task_whose_confined_verdict_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    confined_rc: int,
    executed: bool,
    expected: str | None,
) -> None:
    """HIGH-1: a visible test that passes unconfined but not confined (e.g. needs a tool the
    confinement denies), or that cannot run confined, is excluded for BOTH arms."""
    from scripts.bench import capability_ab_runner as runner

    root = tmp_path / "ws"
    task = _parity_task(root, VISIBLE_OK)
    calls: list[int] = []

    def fake_confined(**kw: object) -> tuple[subprocess.CompletedProcess[str], bool]:
        calls.append(1)
        return subprocess.CompletedProcess(
            [], confined_rc, "", "confinement_unavailable:x"
        ), executed

    monkeypatch.setattr(seam, "run_visible_test_confined", fake_confined)
    failures = runner._confinement_parity_failures([task], root, materialize_missing=False)

    if expected is None:
        assert failures == {}
        return
    assert failures == {"parity-demo": expected}
    assert len(calls) == (2 if executed else 1)  # a differing verdict is re-run once (flakes)
    rows = [
        runner._confinement_parity_row(mode, task, failures[task.id])
        for mode in ("with_nexus", "without_nexus")
    ]
    for row in rows:
        assert row["not_run"] is True and row["run_eligible"] is False
        assert row["not_run_reason"] == runner.CONFINEMENT_PARITY_FAILED
        assert row["model_calls"] == 0
    assert {row["mode"] for row in rows} == {"with_nexus", "without_nexus"}


def test_confined_visible_test_can_run_git_from_the_toolchain(tmp_path: Path) -> None:
    """HIGH-1: the confinement grants read/exec of the system toolchain (oabh-drift's visible
    test shells out to git); without a barrier nothing runs (symmetric exclusion instead)."""
    case = tmp_path / "case"
    case.mkdir()
    (case / "target.py").write_text("X = 1\n", encoding="utf-8")
    (case / "test_visible.py").write_text(
        "import subprocess\n\ndef test_git():\n"
        "    out = subprocess.run(['git', '--version'], capture_output=True, text=True)\n"
        "    assert out.returncode == 0, out.stderr\n",
        encoding="utf-8",
    )
    completed, executed = seam.run_visible_test_confined(
        target_path=case / "target.py",
        visible_test_path=case / "test_visible.py",
        original_code="X = 1\n",
        candidate_code="X = 2\n",
        timeout_sec=120,
    )
    if REAL_BARRIER:
        assert executed is True
        assert completed.returncode == 0, completed.stdout[-600:] + completed.stderr[-300:]
    else:
        assert executed is False


def test_parity_report_cannot_emit_workflow_commands(capsys: pytest.CaptureFixture[str]) -> None:
    """Gemini G10: task ids from a fixture manifest are printed as one defused line."""
    from scripts.bench import capability_ab_runner as runner

    runner._report_confinement_parity({
        "task_1\n::set-output name=pwned::true": "visible_verdict_differs",
        "##[error]boom": "hidden_timeout",
        "::warning::x": "visible:confinement_unavailable",
    })
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1
    assert not lines[0].lstrip().startswith("::")
    assert "##[" not in err and "\n::" not in err
