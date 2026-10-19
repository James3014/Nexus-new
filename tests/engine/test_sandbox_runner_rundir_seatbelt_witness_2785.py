"""Issue #2785: macOS physical witness that the child cannot swap run_dir.

``SandboxRunner.run_task`` runs a real ``sandbox-exec`` child with the profile it
builds itself.  The project root (and so ``run_dir``) sits under /private/tmp, which
the profile lets the child write: the worst case from the #2781 review.  The child
tries to rename ``run_dir`` and its parent and to put a symlink in their place; every
attempt must be refused by Seatbelt, a Python grandchild must still load the parent's
network guard, and the parent must write ``sandbox_result.json`` into the real dir.

Collection rule (same as the DSH and agy dispatch witnesses, #1607): where Seatbelt
cannot run the witnesses are bound to ``None`` so pytest collects nothing, never a
skip that could be mistaken for evidence.  Only the macOS job ``dsh-seatbelt-physical-
witness`` collects them, and ``scripts/ci/verify_physical_witness_junit.py verify
--suite sandbox-runner-rundir`` fails closed unless exactly these two nodes PASSED.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from nexus.core import state_root
from nexus.engine.sandbox_runner import SandboxRunner

SEATBELT_AVAILABLE = sys.platform == "darwin" and shutil.which("sandbox-exec") is not None
PHYSICAL_WITNESSES = (
    "test_child_cannot_rename_or_replace_run_dir_under_real_sandbox_exec",
    "test_python_child_still_loads_the_parent_guard_after_a_swap_attempt",
)
DENIED = "Operation not permitted"

# The child finds run_dir from the guard, which is the first PYTHONPATH entry.
_SWAP_SCRIPT = r"""
G="${PYTHONPATH%%:*}"
R="$(dirname "$G")"
P="$(dirname "$R")"
A="$PWD/attacker"
mkdir -p "$A/python_network_guard"
printf 'import socket\nsocket.PLANTED = True\n' > "$A/python_network_guard/sitecustomize.py"
mv "$R" "$R.moved" 2>&1; echo "rename_run_dir=$?"
ln -s "$A" "$R" 2>&1; echo "symlink_run_dir=$?"
mv "$P" "$P.moved" 2>&1; echo "rename_parent=$?"
rm -rf "$R" 2>&1; echo "remove_run_dir=$?"
printf x > "$R/sandbox_result.json" 2>&1; echo "plant_report=$?"
printf x > "$G/sitecustomize.py" 2>&1; echo "rewrite_guard=$?"
printf ok > "$(dirname "$P")/sibling_2785.txt" 2>&1; echo "sibling_write=$?"
if [ -n "${ROOT_LINK_2785:-}" ]; then
  # The project root was given through a user symlink: repoint that symlink at a
  # tree with a planted guard under the same relative path (#2791 review).
  T="$PWD/linked-attacker"
  mkdir -p "$T/.nexus/sandbox/runs/$(basename "$R")/python_network_guard"
  printf 'import socket\nsocket.PLANTED = True\n' > "$T/.nexus/sandbox/runs/$(basename "$R")/python_network_guard/sitecustomize.py"
  mv "$ROOT_LINK_2785" "$ROOT_LINK_2785.old" 2>&1; echo "rename_root_link=$?"
  ln -s "$T" "$ROOT_LINK_2785" 2>&1; echo "repoint_root_link=$?"
fi
"""


def physical_seatbelt_witness(func, *, available: bool = SEATBELT_AVAILABLE):
    """Expose a physical witness as a test node only where Seatbelt can run."""
    return func if available else None


def test_witness_nodes_are_declared_and_darwin_ci_must_collect_them():
    """Always collected (Linux included), so the impact gate sees a passing node.

    The physical nodes themselves exist only where Seatbelt runs. This keeps the
    declaration pinned and fails, rather than skips, if a CI macOS host ends up
    without them.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    declared = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(d, ast.Name) and d.id == "physical_seatbelt_witness"
            for d in node.decorator_list
        )
    }
    assert declared == set(PHYSICAL_WITNESSES)
    for name in PHYSICAL_WITNESSES:
        assert (globals().get(name) is not None) is SEATBELT_AVAILABLE
    if os.environ.get("CI") and sys.platform == "darwin":
        assert SEATBELT_AVAILABLE, "macOS CI host has no sandbox-exec"


@pytest.fixture
def tmp_project(monkeypatch):
    """A project root under /private/tmp, which the default profile lets the child write."""
    for name in (
        state_root.STATE_ROOT_ENV,
        state_root.CANONICAL_SOURCE_ROOT_ENV,
        state_root.TARGET_ROOT_OVERRIDE_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    base = Path(tempfile.mkdtemp(prefix="nexus-rundir-witness-2785-", dir="/private/tmp"))
    root = base / "proj"
    root.mkdir()
    (root / "swap.sh").write_text(_SWAP_SCRIPT, encoding="utf-8")
    try:
        yield root
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _run_dir(result: dict) -> Path:
    return Path(result["report_path"]).parent


@physical_seatbelt_witness
def test_child_cannot_rename_or_replace_run_dir_under_real_sandbox_exec(tmp_project):
    runner = SandboxRunner(tmp_project)
    assert runner.has_sandbox_exec
    result = runner.run_task("swap", command=["/bin/sh", "swap.sh"], timeout_sec=60)

    assert result["network_barrier"]["mode"] == "os_level_sandbox_exec"
    out = result["stdout"]
    for step in (
        "rename_run_dir",
        "symlink_run_dir",
        "rename_parent",
        "remove_run_dir",
        "plant_report",
        "rewrite_guard",
    ):
        assert f"{step}=0" not in out, f"{step} was allowed: {out}"
        assert f"{step}=" in out, out
    assert DENIED in out, out
    # Control: the child can still create a file next to run_dir's parent, so the
    # denials are specific to run_dir and its parents, not a deny-all profile.
    assert "sibling_write=0" in out, out

    run_dir = _run_dir(result)
    assert result["success"] is True, result
    assert not run_dir.is_symlink() and run_dir.is_dir()
    assert not run_dir.with_name(run_dir.name + ".moved").exists()
    assert not run_dir.parent.with_name(run_dir.parent.name + ".moved").exists()
    assert (run_dir.parent.parent / "sibling_2785.txt").read_text(encoding="utf-8") == "ok"
    report = json.loads((run_dir / "sandbox_result.json").read_text(encoding="utf-8"))
    assert report["run_id"] == result["run_id"]
    guard = (run_dir / "python_network_guard" / "sitecustomize.py").read_text(encoding="utf-8")
    assert "_guarded_create_connection" in guard


@physical_seatbelt_witness
def test_python_child_still_loads_the_parent_guard_after_a_swap_attempt(tmp_project, monkeypatch):
    for linked in (False, True):
        root = tmp_project
        if linked:
            real_base = tmp_project.parent
            (real_base / "link").symlink_to(tmp_project, target_is_directory=True)
            root = Path("/tmp") / real_base.name / "link"
            assert root.is_symlink() and os.path.realpath(root) == str(tmp_project)
            monkeypatch.setenv("ROOT_LINK_2785", str(root))
        _assert_guard_survives_swap(root, linked=linked)


def _assert_guard_survives_swap(root: Path, *, linked: bool) -> None:
    runner = SandboxRunner(root)
    probe = (
        "import socket; "
        "print('guard=' + socket.create_connection.__name__); "
        "print('planted=' + str(getattr(socket, 'PLANTED', False)))"
    )
    result = runner.run_task(
        "swap-then-python",
        command=["/bin/sh", "-c", f'/bin/sh swap.sh; exec "$0" -c "{probe}"', sys.executable],
        timeout_sec=60,
    )
    assert result["success"] is True, result
    out = result["stdout"]
    assert "rename_run_dir=0" not in out and "rename_parent=0" not in out, out
    assert "guard=_guarded_create_connection" in out, out
    assert "planted=False" in out, out
    assert not _run_dir(result).is_symlink()
    # run_dir, and so the guard on PYTHONPATH and the report, is a real path.
    assert str(_run_dir(result)) == os.path.realpath(_run_dir(result))
    if linked:
        # The child really did repoint the user symlink; it just no longer matters.
        assert "rename_root_link=0" in out and "repoint_root_link=0" in out, out
        assert Path(os.path.realpath(root)).name == "linked-attacker"
        assert _run_dir(result).is_relative_to(Path(os.path.realpath(root.parent / "proj")))
