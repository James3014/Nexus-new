"""The committee patch-execution verifier runs untrusted candidates only inside the shared sandbox.

Every test passes on every platform: where no OS barrier exists (Linux CI) the tests assert the
fail-closed contract (nothing executed, candidate unverified) instead of being skipped.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from nexus.committee import execution_verifier as ev
from nexus.engine import sandboxed_lane as lane

CALC = "def add(a, b):\n    return a - b\n"
GOOD_PATCH = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
REPRO = "from calc import add\n\nassert add(2, 3) == 5\n"


def _workspace(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "calc.py").write_text(CALC, encoding="utf-8")
    (ws / "repro.py").write_text(REPRO, encoding="utf-8")
    for name, text in (files or {}).items():
        (ws / name).write_text(text, encoding="utf-8")
    return ws


def _codes(verdict) -> list[str]:
    return [tag.code for tag in verdict.failure_tags]


def _spy_runs(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    seen: list[list[str]] = []
    real = subprocess.run

    def spy(argv, *args, **kwargs):
        seen.append(list(argv))
        return real(argv, *args, **kwargs)

    real_reaping = lane.run_reaping_process_group

    def reaping_spy(argv, *args, **kwargs):
        # Confinement.run runs model code through the process-group reaping runner (#3052).
        seen.append(list(argv))
        return real_reaping(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    monkeypatch.setattr(lane, "run_reaping_process_group", reaping_spy)
    return seen


def test_patch_creating_a_symlink_is_rejected_before_apply(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    patch = (
        "diff --git a/leak b/leak\nnew file mode 120000\nindex 0000000..1111111\n"
        "--- /dev/null\n+++ b/leak\n@@ -0,0 +1 @@\n+/Users/someone/.ssh/id_ed25519\n"
        "\\ No newline at end of file\n"
    )
    verifier = ev.PatchExecutionVerifier(ws, ["python3 repro.py"], "symlink")
    verdict = verifier.evaluate("c0", patch)
    record = verifier.results[0]
    assert verdict.passed is False
    assert _codes(verdict) == ["PATCH_REJECTED"]
    assert record["apply_status"] == "rejected"
    assert record["verify_result"] == "not_executed:patch_rejected"
    assert record["exit_codes"] == []
    assert not (Path(record["workspace"]) / "leak").exists()


def test_patch_touching_git_dir_or_renaming_is_rejected(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    git_patch = "--- a/.git/config\n+++ b/.git/config\n@@ -0,0 +1 @@\n+[core]\n"
    rename_patch = "diff --git a/calc.py b/other.py\nsimilarity index 100%\nrename from calc.py\nrename to other.py\n"
    verifier = ev.PatchExecutionVerifier(ws, ["python3 repro.py"], "gitdir")
    assert _codes(verifier.evaluate("c0", git_patch)) == ["PATCH_REJECTED"]
    assert _codes(verifier.evaluate("c1", rename_patch)) == ["PATCH_REJECTED"]
    assert [r["apply_status"] for r in verifier.results] == ["rejected", "rejected"]
    assert (ws / "calc.py").read_text(encoding="utf-8") == CALC


def test_post_apply_walk_flags_any_symlink(tmp_path: Path) -> None:
    root = tmp_path / "mirror"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    os.symlink("/etc/hosts", root / "pkg" / "link")
    assert lane.lstat_walk_violations(root) == ["pkg/link"]


@pytest.mark.parametrize(
    "command",
    [
        "curl http://example.invalid",
        "bash -c true",
        "python3 repro.py; cat ~/.ssh/id_ed25519",
        "python3 repro.py && true",
        "python3 -c 'print(1)'",
        "python3 -m pip install x",
        "ruff check --fix .",
        ["sh", "-c", "true"],
        # allowlist bypass shapes
        "FOO=bar python3 repro.py",
        "/usr/bin/python3 repro.py",
        "./python3 repro.py",
        "python3 -- repro.py",
        "python3 -I -X dev repro.py",
        "python3 repro.py --flag",
        "python3 ../outside.py",
        "python3 /etc/outside.py",
        "python -m pytest -p evil",
        "python -m pytest --rootdir=/",
        "python -m pytest -c conftest.py",
        "python -m pytest --import-mode=append",
        "python -m pytest -k -pevil",
        "python -m pytest -o addopts=-pevil",
        "python -m pytest -- tests",
        "python -m pytest ../tests",
        "ruff check --config ruff.toml .",
        "ruff check --config=/tmp/ruff.toml .",
        "ruff check /etc",
        "",
    ],
)
def test_command_outside_allowlist_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command
) -> None:
    ws = _workspace(tmp_path)
    seen = _spy_runs(monkeypatch)
    verifier = ev.PatchExecutionVerifier(ws, [command], "allowlist")
    verdict = verifier.evaluate("c0", GOOD_PATCH)
    assert verdict.passed is False
    assert _codes(verdict) in (["COMMAND_NOT_ALLOWED"], ["NO_OS_BARRIER"], ["NO_VERIFY_COMMANDS"])
    assert verifier.results[0]["exit_codes"] == []
    assert not any(os.path.basename(argv[0]) != "git" for argv in seen)


def test_command_paths_must_resolve_inside_the_sandbox(tmp_path: Path) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "repro.py").write_text(REPRO, encoding="utf-8")
    (tmp_path / "outside.py").write_text("print(1)\n", encoding="utf-8")
    build = lambda cmd: ev.build_argv(ev.parse_command(cmd), mirror=mirror, interpreter="py")  # noqa: E731
    argv = build("python3 repro.py")
    assert argv[:3] == ["py", "-I", "-c"] and argv[4] == str((mirror / "repro.py").resolve())
    assert build("python -I -m pytest -q tests/test_a.py::test_x")[:4] == [
        "py",
        "-I",
        "-m",
        "pytest",
    ]
    for bad in (
        "python3 ../outside.py",
        f"python3 {tmp_path / 'outside.py'}",
        "python -m pytest ../elsewhere",
        "python -m pytest --rootdir=/",
        "python -m pytest -p evil",
        "ruff check /etc",
    ):
        with pytest.raises(ev.CommandNotAllowed):
            build(bad)


def test_no_os_barrier_executes_nothing_and_candidate_stays_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_DISABLE_OS_SANDBOX", "1")
    ws = _workspace(tmp_path)
    seen = _spy_runs(monkeypatch)
    verifier = ev.PatchExecutionVerifier(ws, ["python3 repro.py"], "nobarrier")
    verdict = verifier.evaluate("c0", GOOD_PATCH)
    record = verifier.results[0]
    assert verdict.passed is False
    assert _codes(verdict) == ["NO_OS_BARRIER"]
    assert record["apply_status"] == "applied"
    assert record["verify_result"] == ev.NOT_EXECUTED_NO_BARRIER
    assert record["exit_codes"] == []
    # Only git (safe env) ran; no interpreter ever saw candidate code.
    assert seen and all(os.path.basename(argv[0]) == "git" for argv in seen)
    with pytest.raises(lane.SandboxError, match="no_os_barrier"):
        lane.run_confined(
            ["true"],
            cwd=ws,
            confine_roots=(ws,),
            profile=lambda: "",
            env={},
            timeout=5,
            require_barrier=True,
        )


def test_candidate_cannot_read_credentials_or_open_a_socket(tmp_path: Path) -> None:
    ssh = Path(os.path.expanduser("~")).resolve() / ".ssh"
    # Only the public key is ever named; the private key is never touched.
    target = ssh / "nexus-owner-deletion.pub"
    probe_read = (
        "import os, sys\n"
        f"target = {str(target)!r}\n"
        f"ssh = {str(ssh)!r}\n"
        "try:\n"
        "    if os.path.exists(target):\n"
        "        open(target, 'rb').read(1)\n"
        "    else:\n"
        "        os.listdir(ssh)\n"
        "except PermissionError:\n"
        "    sys.exit(3)\n"
        "except OSError:\n"
        "    sys.exit(4)\n"
        "sys.exit(0)\n"
    )
    probe_net = (
        "import socket, sys\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', 9), timeout=2)\n"
        "except PermissionError:\n"
        "    sys.exit(3)\n"
        "except OSError:\n"
        "    sys.exit(4)\n"
        "sys.exit(0)\n"
    )
    ws = _workspace(tmp_path, {"probe_read.py": probe_read, "probe_net.py": probe_net})
    verifier = ev.PatchExecutionVerifier(
        ws, ["python3 probe_read.py", "python3 probe_net.py"], "exfil"
    )
    verdict = verifier.evaluate("c0", GOOD_PATCH)
    record = verifier.results[0]
    assert verdict.passed is False
    if not lane.os_sandbox_available():
        assert record["verify_result"] == ev.NOT_EXECUTED_NO_BARRIER
        assert record["exit_codes"] == []
        return
    assert record["isolation"]["barrier"] == "macos_sandbox_exec"
    # 3 = PermissionError from the barrier, for both the credential read and the socket.
    assert record["exit_codes"] == [3, 3]
    assert record["verify_result"] == "fail"


def test_benign_candidate_passes_only_with_a_barrier(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    verifier = ev.PatchExecutionVerifier(ws, ["python3 repro.py"], "benign")
    verdict = verifier.evaluate("c0", GOOD_PATCH)
    record = verifier.results[0]
    if lane.os_sandbox_available():
        assert verdict.passed is True and record["verify_result"] == "pass"
        assert record["exit_codes"] == [0]
    else:
        assert verdict.passed is False and record["verify_result"] == ev.NOT_EXECUTED_NO_BARRIER
    assert (ws / "calc.py").read_text(encoding="utf-8") == CALC


HELPER = "x = 1\n"
PYPROJECT = '[tool.pytest.ini_options]\naddopts = "-q"\n'
HARNESS_PATCHES = {
    "nested_upper_case_conftest": (
        "--- /dev/null\n+++ b/tests/sub/CONFTEST.py\n@@ -0,0 +1 @@\n+import os\n",
        ["test_harness:tests/sub/CONFTEST.py"],
    ),
    "two_hunk_rename_onto_conftest": (
        "--- a/helper.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x = 1\n"
        "--- /dev/null\n+++ b/conftest.py\n@@ -0,0 +1 @@\n+x = 1\n",
        ["test_harness:conftest.py"],
    ),
    "pyproject_pytest_options": (
        "--- a/pyproject.toml\n+++ b/pyproject.toml\n@@ -1,2 +1,2 @@\n"
        ' [tool.pytest.ini_options]\n-addopts = "-q"\n+addopts = "-p evil"\n',
        ["test_harness:pyproject.toml"],
    ),
    "pth_file": (
        "--- /dev/null\n+++ b/pkg/evil.pth\n@@ -0,0 +1 @@\n+import os\n",
        ["test_harness:pkg/evil.pth"],
    ),
    "env_file": (
        "--- /dev/null\n+++ b/.env\n@@ -0,0 +1 @@\n+PYTHONPATH=/x\n",
        ["test_harness:.env"],
    ),
    "requirements": (
        "--- /dev/null\n+++ b/requirements-dev.txt\n@@ -0,0 +1 @@\n+evil\n",
        ["test_harness:requirements-dev.txt"],
    ),
}


@pytest.mark.parametrize("case", sorted(HARNESS_PATCHES))
def test_patch_touching_the_test_harness_is_rejected(tmp_path: Path, case: str) -> None:
    patch, reasons = HARNESS_PATCHES[case]
    ws = _workspace(tmp_path, {"helper.py": HELPER, "pyproject.toml": PYPROJECT})
    verifier = ev.PatchExecutionVerifier(ws, ["python -m pytest -q"], "harness")
    verdict = verifier.evaluate("c0", patch)
    record = verifier.results[0]
    assert _codes(verdict) == ["PATCH_REJECTED"], record
    assert record["reject_reasons"] == reasons
    assert record["exit_codes"] == []


def test_pytest_runs_with_candidate_config_neutralised(tmp_path: Path) -> None:
    # A pre-existing (workspace) conftest that would fail every run is not loaded either:
    # --noconftest -c /dev/null -o addopts= leaves only the named test module.
    ws = _workspace(
        tmp_path,
        {
            "conftest.py": "raise SystemExit(9)\n",
            "pytest.ini": "[pytest]\naddopts = -p no_such_plugin\n",
            "test_calc.py": "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        },
    )
    verifier = ev.PatchExecutionVerifier(ws, ["python -m pytest -q test_calc.py"], "neutral")
    verdict = verifier.evaluate("c0", GOOD_PATCH)
    record = verifier.results[0]
    if not lane.os_sandbox_available():
        assert record["verify_result"] == ev.NOT_EXECUTED_NO_BARRIER
        return
    assert verdict.passed is True, record
    assert record["exit_codes"] == [0]


def test_confined_argv_uses_the_pinned_interpreter_and_neutralises_addopts(tmp_path: Path) -> None:
    import sys

    mirror = tmp_path / "mirror"
    mirror.mkdir()
    argv = ev.build_argv(
        ev.parse_command(["python3", "-m", "pytest", "-q"]),
        mirror=mirror,
        interpreter=sys.executable,
    )
    assert argv[:4] == [sys.executable, "-I", "-m", "pytest"]
    assert ["-o", "addopts="] == argv[argv.index("addopts=") - 1 : argv.index("addopts=") + 1]
    ini = str((tmp_path / ev.VERIFIER_INI).resolve())
    assert ["-p", "no:cacheprovider", "--noconftest", "-c", ini] == argv[4:9]
    with pytest.raises(lane.SandboxError, match="python_lane_not_isolated"):
        lane.run_confined(
            [sys.executable, "x.py"],
            cwd=mirror,
            confine_roots=(mirror,),
            profile=lambda: "",
            env={},
            timeout=5,
        )
