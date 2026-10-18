"""#2634: agent- or model-controlled text is never executed through a shell.

Covers the evidence verifier's test-command replay, the autonomous repair loop's
handling of model output, and the inline-code forms of interpreters in the shared
exec policy (worker spawns, candidate verifiers, CLI pre-gate).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from nexus.delivery import evidence_verifier as ev
from nexus.delivery.evidence_verifier import EvidenceVerifier, parse_allowlisted_test_command
from nexus.executors.exec_policy import inline_code_form, validate_exec

# Each injection appends a side effect that would create PWNED in the cwd.
INJECTIONS = {
    "semicolon_rm": "pytest -q; rm -rf x; touch PWNED",
    "command_substitution": "pytest -q $(touch PWNED)",
    "backticks": "pytest -q `touch PWNED`",
    "and_and": "pytest -q && touch PWNED",
    "pipe_sh": "echo touch PWNED | sh",
    "pipe_after_pytest": "pytest -q | sh",
    "newline": "pytest -q\ntouch PWNED",
    "redirect": "pytest -q > PWNED",
    "background_amp": "pytest -q & touch PWNED",
}


def _project(tmp_path: Path) -> Path:
    """A tiny project with one passing test and a .venv/bin/python launcher for this interpreter."""
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "keep.txt").write_text("keep", encoding="utf-8")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    # A launcher, not a symlink: a symlinked venv python loses its site-packages.
    launcher = venv_bin / "python"
    launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    return tmp_path


def _assert_no_side_effect(root: Path) -> None:
    assert not (root / "PWNED").exists()
    assert (root / "x" / "keep.txt").exists()


# --- evidence verifier -----------------------------------------------------------


@pytest.mark.parametrize("form", sorted(INJECTIONS))
def test_evidence_verifier_injection_is_uncovered_and_not_executed(tmp_path, form):
    root = _project(tmp_path)
    report = EvidenceVerifier(root)._verify_test_commands([{"command": INJECTIONS[form]}])
    _assert_no_side_effect(root)
    assert report["executed"] == []
    assert report["not_executed"] == []
    assert report["status"] == "UNCOVERED"
    assert report["advisory"] is True
    assert report["all_executed"] is False
    assert report["uncovered"][0]["executed"] is False


@pytest.mark.parametrize("form", sorted(INJECTIONS))
def test_parse_allowlisted_test_command_rejects_injection(form):
    with pytest.raises(ValueError):
        parse_allowlisted_test_command(INJECTIONS[form])


@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf x",
        "touch PWNED",
        "sh -c 'touch PWNED'",
        'python3 -c \'open("PWNED","w")\'',
        "python -m pip install evil",
        "uv run python -c pass",
        "node -e 1",
        "make test",
        "claims_count=7",
        "pytest -p evil_plugin",
        "pytest -pevil_plugin",
        "pytest -c other.ini",
        "pytest --rootdir=/",
        "pytest ../outside",
        "/tmp/.venv/bin/python -m pytest",
    ],
)
def test_evidence_verifier_non_allowlisted_command_is_uncovered(tmp_path, cmd):
    root = _project(tmp_path)
    report = EvidenceVerifier(root)._verify_test_commands([cmd])
    _assert_no_side_effect(root)
    assert report["executed"] == []
    assert report["status"] == "UNCOVERED"
    assert report["uncovered"][0]["status"] == "UNCOVERED"


@pytest.mark.parametrize(
    "cmd, argv",
    [
        ("pytest -q tests/a.py", ["pytest", "-q", "tests/a.py"]),
        ("python -m pytest -q", ["python", "-m", "pytest", "-q"]),
        ("python3 -m pytest tests/a.py::t", ["python3", "-m", "pytest", "tests/a.py::t"]),
        ("uv run pytest -q", ["uv", "run", "pytest", "-q"]),
        (".venv/bin/python -m pytest -q", [".venv/bin/python", "-m", "pytest", "-q"]),
    ],
)
def test_allowlisted_runner_is_run_argv_only_without_shell(tmp_path, monkeypatch, cmd, argv):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(ev.subprocess, "run", fake_run)
    report = EvidenceVerifier(tmp_path)._verify_test_commands([{"command": cmd}])
    assert report["all_executed"] is True
    assert len(calls) == 1
    (call_args, call_kwargs) = calls[0]
    assert call_args[0] == argv
    assert not call_kwargs.get("shell")


def test_allowlisted_pytest_command_really_runs(tmp_path):
    root = _project(tmp_path)
    report = EvidenceVerifier(root)._verify_test_commands([
        {"command": ".venv/bin/python -m pytest -q test_ok.py"}
    ])
    assert report["all_executed"] is True
    assert report["executed"][0]["exit_code"] == 0
    assert report["executed"][0]["passed"] is True
    assert report["uncovered"] == []


def test_mixed_commands_run_only_the_allowlisted_one(tmp_path):
    root = _project(tmp_path)
    report = EvidenceVerifier(root)._verify_test_commands([
        {"command": ".venv/bin/python -m pytest -q test_ok.py"},
        {"command": INJECTIONS["semicolon_rm"]},
    ])
    _assert_no_side_effect(root)
    assert [item["passed"] for item in report["executed"]] == [True]
    assert len(report["uncovered"]) == 1
    assert report["all_executed"] is True
    assert "status" not in report


def test_evidence_verifier_module_never_uses_shell_true():
    source = Path(ev.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in source


# --- autonomous repair loop --------------------------------------------------------


@pytest.fixture()
def repair_loop():
    from scripts.ops import autonomous_repair_loop

    return autonomous_repair_loop


@pytest.mark.parametrize("form", sorted(INJECTIONS))
def test_repair_loop_model_output_injection_not_executed(tmp_path, repair_loop, form):
    root = _project(tmp_path)
    lines = INJECTIONS[form].splitlines()
    outcomes = repair_loop.execute_repair_proposals(lines, root)
    _assert_no_side_effect(root)
    # Every line that carries the injected side effect is refused; a newline only
    # separates proposals, so a bare allowlisted "pytest -q" line may still run.
    side_effect_lines = [
        item for item in outcomes if any(mark in item["command"] for mark in ("PWNED", "rm ", "sh"))
    ]
    assert side_effect_lines
    assert all(item["status"] == "NOT_EXECUTED" for item in side_effect_lines)
    assert all(item["status"] != "EXECUTED" or item["command"] == "pytest -q" for item in outcomes)


def test_repair_loop_runs_allowlisted_pytest_argv_only(tmp_path, repair_loop):
    root = _project(tmp_path)
    lines = [
        "# comment",
        "sed -i s/a/b/ test_ok.py",
        ".venv/bin/python -m pytest -q test_ok.py",
    ]
    outcomes = repair_loop.execute_repair_proposals(lines, root)
    assert [item["status"] for item in outcomes] == ["NOT_EXECUTED", "EXECUTED"]
    assert outcomes[1]["exit_code"] == 0
    assert "assert True" in (root / "test_ok.py").read_text(encoding="utf-8")


def test_repair_loop_source_never_uses_shell_true(repair_loop):
    assert "shell=True" not in Path(repair_loop.__file__).read_text(encoding="utf-8")


# --- exec policy: inline program text ------------------------------------------------


@pytest.mark.parametrize(
    "executable, argv",
    [
        ("perl", ("-e", "system('id')")),
        ("perl", ("-ne", "print")),
        ("perl", ("-I", "lib", "-E", "say 1")),
        ("/usr/bin/perl5.34", ("-e", "1")),
        ("ruby", ("-e", "system('id')")),
        ("ruby", ("-E", "utf-8", "-e", "1")),
        ("node", ("-e", "require('child_process').execSync('id')")),
        ("node", ("--eval=1",)),
        ("node", ("--print", "1")),
        ("node", ("-pe", "1")),
        ("node", ("--require", "m", "-e", "1")),
        ("nodejs", ("-e", "1")),
        ("bun", ("-e", "1")),
        ("deno", ("eval", "1")),
        ("php", ("-r", "system('id');")),
        ("lua", ("-e", "os.execute('id')")),
    ],
)
def test_inline_code_interpreters_rejected_for_workers(executable, argv):
    with pytest.raises(ValueError, match="inline"):
        validate_exec(executable, argv)


@pytest.mark.parametrize("name", ["awk", "gawk", "mawk", "nawk", "make", "gmake", "bmake"])
def test_awk_and_make_are_forwarders(name):
    with pytest.raises(ValueError, match="forwarder"):
        validate_exec(f"/usr/bin/{name}", ("x",))


@pytest.mark.parametrize(
    "executable, argv",
    [
        ("perl", ("script.pl",)),
        ("ruby", ("-E", "utf-8", "script.rb")),
        ("node", ("script.js",)),
        ("python3", ("-m", "pytest", "-c", "pytest.ini")),
        ("python3", ("-X", "dev", "-m", "pytest")),
        ("python3", ("script.py", "-c", "x")),
    ],
)
def test_non_inline_interpreter_forms_allowed(executable, argv):
    assert inline_code_form(executable, argv, include_python=True) is None
    validate_exec(executable, argv)


@pytest.mark.parametrize(
    "argv",
    [
        ("-c", "import os; os.system('id')"),
        ("-Ic", "pass"),
        ("-cpass",),
        ("-W", "ignore", "-c", "pass"),
        ("-X", "dev", "-c", "pass"),
        ("--check-hash-based-pycs", "always", "-c", "pass"),
    ],
)
def test_python_inline_code_forms_are_detected_but_stay_allowed(argv):
    assert inline_code_form("python3", argv, include_python=True) == "python"
    # python -c remains the documented Task Card verifier and fake-worker form.
    assert inline_code_form("python3", argv, include_python=False) is None
    validate_exec("python3", argv)


@pytest.mark.parametrize(
    "command",
    [
        "perl -e 'print 1'",
        "ruby -e 'puts 1'",
        "node -e 1",
        "make test",
        "awk 'BEGIN{print 1}'",
    ],
)
def test_candidate_verifier_rejects_inline_code_commands(tmp_path, command):
    from nexus.orchestrator.candidate_verifier import CandidateVerifier

    with pytest.raises(ValueError):
        CandidateVerifier._build_verifier_request(command, str(tmp_path))


def test_candidate_verifier_still_accepts_pytest(tmp_path):
    from nexus.orchestrator.candidate_verifier import CandidateVerifier

    request = CandidateVerifier._build_verifier_request(
        f"{sys.executable} -m pytest -q", str(tmp_path)
    )
    assert request.argv[:2] == ("-m", "pytest")


@pytest.mark.parametrize(
    "command",
    [
        "perl -e 'open(F,\">PWNED\")'",
        "node -e \"require('fs').writeFileSync('PWNED','')\"",
        "make",
    ],
)
def test_pregate_rejects_inline_code_commands(tmp_path, command):
    from nexus.engine.cli_pregate import run_cli_pregate

    (tmp_path / "Makefile").write_text("all:\n\ttouch PWNED\n", encoding="utf-8")
    ok, results = run_cli_pregate(tmp_path, [command], timeout_per_cmd=10)
    assert ok is False
    assert results[0]["passed"] is False
    assert not (tmp_path / "PWNED").exists()
