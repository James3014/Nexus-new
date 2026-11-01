"""pr_preflight: the nexus-core pin comes from the base ref only, and the certify run is bounded.

The pinned nexus-core ref is built and run on this host through ``uvx``. These tests use a fake
``uvx`` that records its arguments, so nothing is fetched or built:

- the pin is read from the base ref only; no pin at the base is a FAIL with no uvx run;
- a base pin is used as is, whatever the head pins;
- a certify run past its time bound is a FAIL, and its whole process group is killed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ops" / "pr_preflight.py"
CERTIFY_PIN_WORKFLOW = ".github/workflows/nexus-core-issue-completion.yml"
BASE_PIN = "3f3dc38de7120b66f25eb246d22ef29d5d5971d9"
HEAD_PIN = "b" * 40
MARKER = "sha256:" + "a" * 64
OPEN_ISSUE = {"state": "OPEN", "body": f"<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: {MARKER} -->"}


def _load():
    spec = importlib.util.spec_from_file_location("pr_preflight_core_pin_source", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pf = _load()


def _git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _pin_text(ref: str) -> str:
    return f'steps:\n  with:\n    nexus-certify-ref: "{ref}"\n'


def _repo(tmp_path: Path, *, base_pin: str | None, head_pin: str | None) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, "README.md", "fixture\n")
    if base_pin is not None:
        _write(root, CERTIFY_PIN_WORKFLOW, _pin_text(base_pin))
    base = _commit(root, "base")
    _git(root, "update-ref", "refs/remotes/origin/main", base)
    _git(root, "checkout", "-q", "-b", "feature")
    if head_pin is not None:
        _write(root, CERTIFY_PIN_WORKFLOW, _pin_text(head_pin))
    _write(root, "docs/note.md", "note\n")
    _commit(root, "feature work")
    return root


def _fake_uvx(tmp_path: Path, body: str) -> tuple[Path, Path]:
    """A ``uvx`` stand-in that appends its argv (one JSON list per line) to a log, then runs body."""
    log = tmp_path / "uvx-calls.jsonl"
    script = tmp_path / "bin" / "uvx"
    script.parent.mkdir()
    script.write_text(
        "#!/bin/sh\n"
        f"{sys.executable} -I -c 'import json,sys; print(json.dumps(sys.argv[1:]))' \"$@\""
        f" >> '{log}'\n" + body,
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script, log


def _calls(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def _run_issue_check(repo: Path, tmp_path: Path, capsys, monkeypatch, uvx: Path) -> tuple:
    monkeypatch.delenv("NEXUS_CERTIFY", raising=False)
    monkeypatch.setattr(pf.shutil, "which", lambda name: str(uvx) if name == "uvx" else None)
    body = tmp_path / "pr-body.md"
    body.write_text("Refs #1916.\n\n<!-- NEXUS_CORE_ISSUE: 1916 -->\n", encoding="utf-8")
    issue = tmp_path / "issue.json"
    issue.write_text(json.dumps(OPEN_ISSUE), encoding="utf-8")
    argv = ["--repo", str(repo), "--no-fetch", "--json", "--skip-static", "--only", "issue"]
    argv += ["--body-file", str(body), "--issue-json", str(issue)]
    code = pf.main(argv)
    report = json.loads(capsys.readouterr().out)
    return code, next(c for c in report["checks"] if c["check"] == "issue")


_PRINT_MARKER = (
    "cat <<'EOF'\n"
    + json.dumps({"issue_marker": f"<!-- NEXUS_CORE_EVIDENCE_UNIVERSE: {MARKER} -->"})
    + "\nEOF\n"
)


def test_pin_only_at_head_fails_closed_without_running_uvx(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path, base_pin=None, head_pin=HEAD_PIN)
    uvx, log = _fake_uvx(tmp_path, _PRINT_MARKER)
    code, check = _run_issue_check(repo, tmp_path, capsys, monkeypatch, uvx)
    assert code == 1
    assert (check["status"], check["code"]) == ("FAIL", pf.NEXUS_CERTIFY_UNAVAILABLE)
    assert "no nexus-certify-ref" in check["detail"]
    assert "base ref only" in check["detail"]
    assert _calls(log) == []
    assert HEAD_PIN not in check["detail"] + check["fix"]


def test_trusted_config_mode_only_at_head_still_needs_a_base_pin(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path, base_pin=None, head_pin=None)
    _write(
        repo,
        CERTIFY_PIN_WORKFLOW,
        _pin_text(HEAD_PIN) + "    evidence-universe: trusted-config\n",
    )
    _commit(repo, "workflow at head only")
    uvx, log = _fake_uvx(tmp_path, _PRINT_MARKER)
    code, check = _run_issue_check(repo, tmp_path, capsys, monkeypatch, uvx)
    assert code == 1
    assert (check["status"], check["code"]) == ("FAIL", pf.NEXUS_CERTIFY_UNAVAILABLE)
    assert "derived from trusted base config" not in check["detail"]
    assert _calls(log) == []


def test_base_pin_is_the_only_ref_run(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path, base_pin=BASE_PIN, head_pin=HEAD_PIN)
    uvx, log = _fake_uvx(tmp_path, _PRINT_MARKER)
    code, check = _run_issue_check(repo, tmp_path, capsys, monkeypatch, uvx)
    assert (code, check["status"]) == (0, "PASS"), check
    calls = _calls(log)
    assert len(calls) == 1
    assert calls[0][:3] == ["--from", f"{pf.CERTIFY_REPO_URL}@{BASE_PIN}", "nexus-certify"]
    assert not any(HEAD_PIN in arg for arg in calls[0])


def test_base_pin_resolves_even_when_head_drops_it(tmp_path, monkeypatch):
    repo = _repo(tmp_path, base_pin=BASE_PIN, head_pin=None)
    _git(repo, "rm", "-q", CERTIFY_PIN_WORKFLOW)
    _commit(repo, "drop workflow at head")
    ctx = pf.Context(
        repo=repo,
        base_ref="origin/main",
        base_sha=_git(repo, "rev-parse", "origin/main"),
        head_sha=_git(repo, "rev-parse", "HEAD"),
        repository="James3014/Nexus-new",
        body=None,
        title=None,
        pr_number=None,
        issue_number=None,
        issue_json=None,
        nexus_certify=None,
        tools_venv=repo / ".venv",
        lane_owner_pending=False,
    )
    assert pf._certify_pin(ctx) == (BASE_PIN, "")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_certify_timeout_fails_and_reaps_the_process_group(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path, base_pin=BASE_PIN, head_pin=None)
    pid_file = tmp_path / "grandchild.pid"
    # The grandchild has no hold on the output pipes, so only a group kill reaches it.
    uvx, log = _fake_uvx(
        tmp_path,
        f"sleep 60 >/dev/null 2>&1 </dev/null &\necho $! > '{pid_file}'\nexec sleep 60\n",
    )
    monkeypatch.setattr(pf, "CERTIFY_TIMEOUT_SECONDS", 2)
    grandchild = None
    try:
        started = time.monotonic()
        code, check = _run_issue_check(repo, tmp_path, capsys, monkeypatch, uvx)
        elapsed = time.monotonic() - started
        assert pid_file.exists(), "fake uvx did not start its background process"
        grandchild = int(pid_file.read_text(encoding="utf-8").strip())
        assert code == 1
        assert (check["status"], check["code"]) == ("FAIL", pf.NEXUS_CERTIFY_UNAVAILABLE)
        assert "could not run" in check["detail"]
        assert "timed out" in check["detail"]
        assert elapsed < 30
        assert len(_calls(log)) == 1
        deadline = time.monotonic() + 5
        while _alive(grandchild) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(grandchild), "background process of the certify run outlived it"
    finally:
        # Only the process this test's fake uvx started, by the pid it recorded.
        if grandchild is not None and _alive(grandchild):
            os.kill(grandchild, signal.SIGKILL)


def test_reaping_helper_unavailable_is_a_fail_not_a_plain_run(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path, base_pin=BASE_PIN, head_pin=None)
    uvx, log = _fake_uvx(tmp_path, _PRINT_MARKER)

    def unavailable():
        raise OSError("argv_command.py unavailable")

    monkeypatch.setattr(pf, "_argv_command", unavailable)
    code, check = _run_issue_check(repo, tmp_path, capsys, monkeypatch, uvx)
    assert code == 1
    assert (check["status"], check["code"]) == ("FAIL", pf.NEXUS_CERTIFY_UNAVAILABLE)
    assert _calls(log) == []


def test_reaping_helper_missing_from_loaded_file_is_a_clean_fail(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path, base_pin=BASE_PIN, head_pin=None)
    uvx, log = _fake_uvx(tmp_path, _PRINT_MARKER)
    # A tree whose nexus/core/argv_command.py loads but has no run_reaping_process_group.
    tree = tmp_path / "tree"
    _write(tree, "nexus/core/argv_command.py", "VALUE = 1\n")
    monkeypatch.setattr(pf, "__file__", str(tree / "scripts" / "ops" / "pr_preflight.py"))
    monkeypatch.setattr(pf, "_argv_command_module", None)
    monkeypatch.delitem(sys.modules, "_preflight_argv_command", raising=False)
    code, check = _run_issue_check(repo, tmp_path, capsys, monkeypatch, uvx)
    assert code == 1
    assert (check["status"], check["code"]) == ("FAIL", pf.NEXUS_CERTIFY_UNAVAILABLE)
    assert "run_reaping_process_group" in check["detail"]
    assert _calls(log) == []
    assert "_preflight_argv_command" not in sys.modules
