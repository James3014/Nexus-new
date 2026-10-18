"""#2634: agent- or model-controlled text is never executed through a shell.

Covers the evidence verifier's test-command replay, the autonomous repair loop's
handling of model output, and the inline-code forms of interpreters in the shared
exec policy (worker spawns, candidate verifiers, CLI pre-gate).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.delivery import evidence_verifier as ev
from nexus.delivery.evidence_verifier import EvidenceVerifier, parse_allowlisted_test_command
from nexus.delivery.replay_runner import ReplayRunner, _parse_command
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


@pytest.fixture(autouse=True)
def _interpreter_on_path(monkeypatch):
    # Allowlisted bare names (python3, pytest) resolve to the interpreter running the tests.
    monkeypatch.setenv(
        "PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    )


def _project(tmp_path: Path) -> Path:
    """A tiny project with one passing test and an agent-replaceable .venv/bin/python.

    The launcher leaves a VENV_RAN marker, so a test can prove it was never run.
    """
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "keep.txt").write_text("keep", encoding="utf-8")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    # A launcher, not a symlink: a symlinked venv python loses its site-packages.
    launcher = venv_bin / "python"
    launcher.write_text(
        f'#!/bin/sh\ntouch VENV_RAN\nexec "{sys.executable}" "$@"\n', encoding="utf-8"
    )
    launcher.chmod(0o755)
    return tmp_path


def _assert_no_side_effect(root: Path) -> None:
    assert not (root / "PWNED").exists()
    assert not (root / "VENV_RAN").exists()
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
def test_parse_allowlisted_test_command_rejects_injection(tmp_path, form):
    with pytest.raises(ValueError):
        parse_allowlisted_test_command(INJECTIONS[form], tmp_path)


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
        ".venv/bin/python -m pytest -q test_ok.py",
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
        ("uv run python -m pytest -q", ["uv", "run", "python", "-m", "pytest", "-q"]),
        ("uv run python3 -m pytest", ["uv", "run", "python3", "-m", "pytest"]),
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
        {"command": "python3 -m pytest -q -p no:cacheprovider test_ok.py"}
    ])
    assert report["all_executed"] is True
    assert report["executed"][0]["exit_code"] == 0
    assert report["executed"][0]["passed"] is True
    assert report["uncovered"] == []


def test_mixed_commands_run_only_the_allowlisted_one(tmp_path):
    root = _project(tmp_path)
    report = EvidenceVerifier(root)._verify_test_commands([
        {"command": "python3 -m pytest -q test_ok.py"},
        {"command": INJECTIONS["semicolon_rm"]},
    ])
    _assert_no_side_effect(root)
    assert [item["passed"] for item in report["executed"]] == [True]
    assert len(report["uncovered"]) == 1
    # An UNCOVERED command was never replayed, so not everything claimed was executed.
    assert report["all_executed"] is False
    assert "status" not in report


def test_mixed_uncovered_command_caps_trust_below_high(tmp_path, monkeypatch):
    root = _project(tmp_path)
    verifier = EvidenceVerifier(root)
    monkeypatch.setattr(verifier.anti_drift, "verify_drift", lambda: (True, {}))
    monkeypatch.setattr(
        verifier.replay_runner, "run_replay", lambda bundle: {"passed": True, "replay_count": 1}
    )
    monkeypatch.setattr(verifier, "_verify_code_artifacts", lambda artifacts: {"all_exist": True})
    monkeypatch.setattr(verifier, "_check_git_diff_non_empty", lambda: True)
    monkeypatch.setattr(verifier, "_get_git_diff_stat", lambda: "1 file changed")
    result = verifier.verify({
        "version": "1.1.0",
        "code_artifacts": ["test_ok.py"],
        "test_artifacts": [
            {"command": "python3 -m pytest -q test_ok.py"},
            "touch PWNED",
        ],
    })
    _assert_no_side_effect(root)
    assert result["overall_trust"] == "MEDIUM"
    assert "test_commands_uncovered" in result["reject_reasons"]
    assert "test_execution_fraud_detected" not in result["reject_reasons"]


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
        "pytest -q --basetemp=x",
        "python3 -m pytest -q test_ok.py",
    ]
    outcomes = repair_loop.execute_repair_proposals(lines, root)
    _assert_no_side_effect(root)
    assert [item["status"] for item in outcomes] == [
        "NOT_EXECUTED",
        "NOT_EXECUTED",
        "NOT_EXECUTED",
        "EXECUTED",
    ]
    assert outcomes[3]["exit_code"] == 0
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
        # Reviewer repros (PR #2649 review, B2): all ran code or were allowed before.
        ("perl", ("-le", "print 1")),
        ("perl", ("-0e", "1")),
        ("perl", ("-Mstrict; system 1;",)),
        ("perl", ("-mPOSIX", "s.pl")),
        ("ruby", ("-We", "1")),
        ("ruby", ("-W0e", "1")),
        ("ruby", ("-E", "utf-8", "script.rb")),
        ("node", ("--import", "data:text/javascript,1", "x.js")),
        ("node", ("--import=data:text/javascript,1",)),
        ("node", ("--experimental-loader", "x.mjs", "a.js")),
        ("node", ("-r", "m", "a.js")),
        ("node", ("data:text/javascript,1",)),
        ("deno", ("-q", "eval", "1")),
        ("deno", ("run", "--eval", "1")),
        ("bun", ("eval", "1")),
        ("bun", ("--preload", "x.ts", "a.ts")),
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
        ("ruby", ("-W0", "script.rb")),
        ("node", ("script.js",)),
        ("node", ("-v",)),
        ("deno", ("run", "--allow-read", "main.ts")),
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


# --- shared pytest option allowlist (replay runner + evidence verifier, B1) ----------


def _evidence_parse(cmd, root):
    return parse_allowlisted_test_command(cmd, root)


def _replay_parse(cmd, root):
    return _parse_command(cmd, root)


PARSERS = pytest.mark.parametrize(
    "parse", [_evidence_parse, _replay_parse], ids=["evidence", "replay"]
)


@PARSERS
@pytest.mark.parametrize(
    "args",
    [
        "--basetemp=OUT",
        "--basetemp OUT",
        "--config-file=evil.ini",
        "--config-file evil.ini",
        "--inifile=evil.ini",
        "-c evil.ini",
        "-cevil.ini",
        "-vc evil.ini",
        "-qo addopts=-pevil",
        "-o addopts=-pevil",
        "--override-ini=addopts=-pevil",
        "-qp evil",
        "-p evil",
        "-pevil",
        "-p no:",
        "--rootdir=/",
        "--confcutdir=/",
        "--junitxml=/tmp/x.xml",
        "--junit-xml=/tmp/x.xml",
        "--log-file=/tmp/x.log",
        "--debug=/tmp/x.log",
        "--debug",
        "--report-log=/tmp/x",
        "--cov-report=xml:/tmp/x",
        "--pastebin=all",
        "-W error::evil.Mod",
        "-Wignore::evil.Mod",
        "--pythonwarnings=ignore",
        "--pyargs evil",
        "--import-mode=importlib",
        "--tb=../x",
        "--maxfail=1;",
        "-rZ",
        "-z",
        "--",
        "/etc",
        "/etc/passwd::x",
        "../outside",
        "--deselect=../outside",
        "sub/../../outside",
        # B4: pytest expands @file into options (fromfile_prefix_chars="@").
        "@args.txt",
        "@/tmp/args.txt",
        "--deselect=@args.txt",
        "--deselect @args.txt",
        "-k @args.txt",
        "-k@args.txt",
        "-m @args.txt",
        "--tb=@args.txt",
    ],
)
def test_pytest_option_allowlist_rejects(tmp_path, parse, args):
    with pytest.raises(ValueError):
        parse(f"pytest -q {args}", tmp_path)


@PARSERS
@pytest.mark.parametrize(
    "args",
    [
        "-q",
        "-v -x",
        "-qvx",
        "-k 'not slow and fast'",
        "-kfast",
        "-m smoke",
        "--tb=short",
        "--tb line",
        "--tb=no",
        "-ra",
        "-rN",
        "--maxfail=2",
        "--no-header",
        "-p no:cacheprovider",
        "-pno:cacheprovider",
        "--version",
        "tests",
        "test_ok.py::test_ok",
        "--deselect test_ok.py::test_other",
    ],
)
def test_pytest_option_allowlist_accepts_safe_options(tmp_path, parse, args):
    (tmp_path / "tests").mkdir()
    assert parse(f"pytest {args}", tmp_path)[0] == "pytest"


@PARSERS
def test_absolute_path_inside_root_is_allowed(tmp_path, parse):
    target = tmp_path / "test_ok.py"
    target.write_text("", encoding="utf-8")
    assert parse(f"pytest {target}", tmp_path)


@PARSERS
def test_symlink_escaping_the_root_is_rejected(tmp_path, parse):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(outside, root / "link")
    with pytest.raises(ValueError, match="outside the project root"):
        parse("pytest link", root)


def test_basetemp_deletion_repro_is_refused_and_nothing_is_deleted(tmp_path):
    """Reviewer repro: pytest --basetemp=<dir> empties <dir>."""
    (tmp_path / "proj").mkdir()
    root = _project(tmp_path / "proj")
    victim = tmp_path / "victim"
    (victim / "keep").mkdir(parents=True)
    (victim / "keep" / "precious.txt").write_text("keep", encoding="utf-8")
    cmd = f"python3 -m pytest -q test_ok.py --basetemp={victim}"
    report = EvidenceVerifier(root)._verify_test_commands([{"command": cmd}])
    assert report["executed"] == []
    assert report["status"] == "UNCOVERED"
    replay = ReplayRunner(root).run_replay({"test_artifacts": [{"command": cmd}]})
    assert replay["status"] == "REJECTED"
    assert replay["replay_count"] == 0
    assert (victim / "keep" / "precious.txt").exists()


@pytest.mark.parametrize(
    "flag", ["--config-file=evil.ini", "--inifile=evil.ini", "-vc evil.ini", "-c evil.ini"]
)
def test_config_file_plugin_load_repro_is_refused(tmp_path, flag):
    """Reviewer repro: an ini with addopts = -p evilplug loaded a plugin that wrote PWNED."""
    root = _project(tmp_path)
    (root / "evilplug.py").write_text("open('PWNED', 'w').close()\n", encoding="utf-8")
    (root / "evil.ini").write_text("[pytest]\naddopts = -p evilplug\n", encoding="utf-8")
    cmd = f"python3 -m pytest -q test_ok.py {flag}"
    report = EvidenceVerifier(root)._verify_test_commands([{"command": cmd}])
    replay = ReplayRunner(root).run_replay({"test_artifacts": [{"command": cmd}]})
    _assert_no_side_effect(root)
    assert report["executed"] == []
    assert replay["replay_count"] == 0


def test_replay_runner_still_runs_an_allowed_pytest(tmp_path):
    root = _project(tmp_path)
    replay = ReplayRunner(root).run_replay({
        "test_artifacts": [
            {"command": "python3 -m pytest -q -p no:cacheprovider test_ok.py", "exit_code": 0}
        ]
    })
    assert replay["status"] == "COMPLETED"
    assert replay["replay_count"] == 1


@pytest.mark.parametrize("relative", [False, True])
def test_fromfile_basetemp_deletion_repro_is_refused(tmp_path, relative):
    """Round-2 repro (B4): an @file holding --basetemp=<victim> deleted the victim."""
    (tmp_path / "proj").mkdir()
    root = _project(tmp_path / "proj")
    victim = tmp_path / "victim"
    (victim / "keep").mkdir(parents=True)
    (victim / "keep" / "precious.txt").write_text("keep", encoding="utf-8")
    # A test that uses tmp_path makes pytest empty --basetemp (verified unguarded).
    (root / "test_ok.py").write_text("def test_ok(tmp_path):\n    assert True\n", encoding="utf-8")
    args_file = root / "args.txt"
    args_file.write_text(f"--basetemp={victim}\n", encoding="utf-8")
    ref = "args.txt" if relative else str(args_file)
    cmd = f"python3 -m pytest -q test_ok.py @{ref}"
    for parse in (_evidence_parse, _replay_parse):
        with pytest.raises(ValueError, match="@file"):
            parse(cmd, root)
    report = EvidenceVerifier(root)._verify_test_commands([{"command": cmd}])
    replay = ReplayRunner(root).run_replay({"test_artifacts": [{"command": cmd}]})
    assert report["executed"] == []
    assert report["status"] == "UNCOVERED"
    assert replay["status"] == "REJECTED"
    assert replay["replay_count"] == 0
    assert (victim / "keep" / "precious.txt").exists()
