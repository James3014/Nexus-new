"""#2721 measurement prerequisites on the Agy executor.

* ``NEXUS_AGY_DENY_WEB_FETCH=1`` adds the URL-tool deny rules; unset (or any
  other value) the run settings are byte-identical to before.
* ``NEXUS_AGY_KEEP_TOOL_TRACE=1`` copies only the run HOME's conversation
  databases out before the run root is deleted, bounded, with sha256; never
  the OAuth token or other HOME files, never through symlinks or hard links.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.executors import agy_write_admission as admission
from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.worker_contract import WorkerOutcome
from nexus.executors.worker_registry import AgyWorkerAdapter

# The exact settings.json bytes main wrote before #2721 (default must not drift).
_PRE_2721_IMPLEMENTATION_SETTINGS = (
    '{\n  "permissions": {\n    "allow": [],\n    "deny": [\n      "command(*)"\n    ]\n  }\n}\n'
)
_PRE_2721_PLAN_SETTINGS = (
    '{\n  "permissions": {\n    "allow": [],\n    "deny": [\n      "command(*)",\n'
    '      "write_file(*)"\n    ]\n  }\n}\n'
)
_OK = json.dumps({"status": "SUCCESS", "response": "edited"}).encode()


def _settings_text(tmp_path: Path, name: str, *, read_only: bool) -> tuple[str, str]:
    source = tmp_path / "src"
    (source / ".gemini" / "antigravity-cli").mkdir(parents=True, exist_ok=True)
    refusal, profile = admission.materialize_run_home(
        source, tmp_path / name, read_only=read_only, isolate_keychain=False
    )
    assert refusal is None
    text = (tmp_path / name / admission.AGY_RUN_HOME_SETTINGS).read_text(encoding="utf-8")
    return text, profile


# ---------------------------------------------------------------------------
# item 1: opt-in URL-tool deny
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "0", "true", "yes"])
def test_default_run_settings_are_byte_identical_to_pre_2721(monkeypatch, tmp_path, value):
    if value is None:
        monkeypatch.delenv(admission.AGY_DENY_WEB_FETCH_ENV, raising=False)
    else:
        monkeypatch.setenv(admission.AGY_DENY_WEB_FETCH_ENV, value)
    impl, _ = _settings_text(tmp_path, "impl", read_only=False)
    plan, _ = _settings_text(tmp_path, "plan", read_only=True)
    assert impl == _PRE_2721_IMPLEMENTATION_SETTINGS
    assert plan == _PRE_2721_PLAN_SETTINGS
    assert admission.agy_run_settings(read_only=False) == {
        "permissions": {"allow": [], "deny": ["command(*)"]}
    }


def test_deny_web_fetch_env_adds_url_tool_rules(monkeypatch, tmp_path):
    monkeypatch.delenv(admission.AGY_DENY_WEB_FETCH_ENV, raising=False)
    _, default_profile = _settings_text(tmp_path, "default", read_only=False)
    monkeypatch.setenv(admission.AGY_DENY_WEB_FETCH_ENV, "1")
    assert admission.agy_run_settings(read_only=False)["permissions"]["deny"] == [
        "command(*)",
        "read_url(*)",
        "execute_url(*)",
    ]
    assert admission.agy_run_settings(read_only=True)["permissions"]["deny"] == [
        "command(*)",
        "write_file(*)",
        "read_url(*)",
        "execute_url(*)",
    ]
    impl, denied_profile = _settings_text(tmp_path, "impl", read_only=False)
    assert json.loads(impl)["permissions"]["deny"][-2:] == ["read_url(*)", "execute_url(*)"]
    assert "search_web" not in impl  # proven ineffective in #2721; not pretended
    # The profile hash binds the settings, so both arms can be compared.
    assert denied_profile != default_profile
    # Each call reads the env afresh and never mutates shared state.
    monkeypatch.delenv(admission.AGY_DENY_WEB_FETCH_ENV)
    assert admission.agy_run_settings(read_only=False)["permissions"]["deny"] == ["command(*)"]


# ---------------------------------------------------------------------------
# item 2: opt-in tool trace
# ---------------------------------------------------------------------------


def _run_home(tmp_path: Path, name: str = "home") -> Path:
    home = tmp_path / name
    cli = home / ".gemini" / "antigravity-cli"
    (cli / "conversations").mkdir(parents=True)
    (cli / "antigravity-oauth-token").write_text("SECRET-TOKEN", encoding="utf-8")
    (cli / "installation_id").write_text("install", encoding="utf-8")
    return home


def test_trace_root_is_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv(admission.AGY_KEEP_TOOL_TRACE_ENV, raising=False)
    monkeypatch.setenv(admission.AGY_TOOL_TRACE_DIR_ENV, str(tmp_path))
    assert admission.agy_tool_trace_root() is None
    monkeypatch.setenv(admission.AGY_KEEP_TOOL_TRACE_ENV, "true")
    assert admission.agy_tool_trace_root() is None
    monkeypatch.setenv(admission.AGY_KEEP_TOOL_TRACE_ENV, "1")
    assert admission.agy_tool_trace_root() == tmp_path
    monkeypatch.setenv(admission.AGY_TOOL_TRACE_DIR_ENV, "relative/dir")
    assert admission.agy_tool_trace_root() is None
    monkeypatch.delenv(admission.AGY_TOOL_TRACE_DIR_ENV)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    assert admission.agy_tool_trace_root() == (
        tmp_path / "h" / ".local" / "state" / "nexus-agy-tool-trace"
    )


def test_preserve_copies_only_conversation_databases(tmp_path):
    home = _run_home(tmp_path)
    conv = home / admission.AGY_RUN_HOME_CONVERSATIONS
    (conv / "abc-123.db").write_bytes(b"sqlite-main")
    (conv / "abc-123.db-wal").write_bytes(b"wal")
    (conv / "abc-123.db-shm").write_bytes(b"shm")
    (conv / "notes.txt").write_text("x", encoding="utf-8")
    token = home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    (conv / "link.db").symlink_to(token)
    os.link(token, conv / "hard.db")
    root = tmp_path / "trace"

    manifest_path = admission.preserve_agy_tool_trace(
        [home], task_id="../evil/task", run_id="nexus-agy-run-x", root=root
    )

    assert manifest_path is not None
    assert manifest_path.parent.is_relative_to(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == admission.AGY_TOOL_TRACE_SCHEMA
    files = {entry["name"]: entry for entry in manifest["attempts"][0]["files"]}
    assert files["abc-123.db"]["sha256"] == hashlib.sha256(b"sqlite-main").hexdigest()
    assert files["abc-123.db-wal"]["sha256"] == hashlib.sha256(b"wal").hexdigest()
    assert files["link.db"]["skipped"] == "unreadable_or_symlink"
    assert files["hard.db"]["skipped"] == "not_a_single_link_regular_file"
    assert "abc-123.db-shm" not in files and "notes.txt" not in files
    copied = {p.name for p in manifest_path.parent.rglob("*") if p.is_file()}
    assert copied == {"manifest.json", "abc-123.db", "abc-123.db-wal"}
    for path in manifest_path.parent.rglob("*"):
        if path.is_file():
            assert b"SECRET-TOKEN" not in path.read_bytes()
            assert path.stat().st_mode & 0o077 == 0


def test_preserve_refuses_conversations_dir_symlinked_out_of_run_home(tmp_path):
    home = tmp_path / "home"
    (home / ".gemini" / "antigravity-cli").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.db").write_bytes(b"secret")
    (home / admission.AGY_RUN_HOME_CONVERSATIONS).symlink_to(outside)

    manifest_path = admission.preserve_agy_tool_trace(
        [home], task_id="t", run_id="r", root=tmp_path / "trace"
    )

    assert manifest_path is not None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["attempts"][0]["status"] == "conversations_path_escapes_run_home"
    assert not list((tmp_path / "trace").rglob("secret.db"))


def test_preserve_enforces_size_caps(monkeypatch, tmp_path):
    monkeypatch.setattr(admission, "AGY_TOOL_TRACE_FILE_MAX_BYTES", 10)
    monkeypatch.setattr(admission, "AGY_TOOL_TRACE_TOTAL_MAX_BYTES", 12)
    home = _run_home(tmp_path)
    conv = home / admission.AGY_RUN_HOME_CONVERSATIONS
    (conv / "a.db").write_bytes(b"x" * 8)
    (conv / "b.db").write_bytes(b"y" * 8)  # would exceed the 12-byte run budget
    (conv / "c.db").write_bytes(b"z" * 11)  # exceeds the 10-byte file cap

    manifest_path = admission.preserve_agy_tool_trace(
        [home], task_id="t", run_id="r", root=tmp_path / "trace"
    )

    assert manifest_path is not None
    files = {
        e["name"]: e
        for e in json.loads(manifest_path.read_text(encoding="utf-8"))["attempts"][0]["files"]
    }
    assert "sha256" in files["a.db"]
    assert files["b.db"]["skipped"] == "size_cap"
    assert files["c.db"]["skipped"] == "size_cap"


def test_preserve_never_raises_when_trace_dir_unwritable(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a dir", encoding="utf-8")
    assert (
        admission.preserve_agy_tool_trace(
            [_run_home(tmp_path)], task_id="t", run_id="r", root=blocker
        )
        is None
    )


# ---------------------------------------------------------------------------
# adapter wiring: copied before the run root is deleted; default unchanged
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _canonical(tmp_path: Path) -> Path:
    root = tmp_path / "canonical"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root.resolve()


@pytest.fixture
def ready(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "realhome"
    cli = home / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    (cli / "antigravity-oauth-token").write_text("SECRET-TOKEN", encoding="utf-8")
    (cli / "installation_id").write_text("install", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_WORKER_MODEL", raising=False)
    monkeypatch.delenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", raising=False)
    monkeypatch.delenv(admission.AGY_DENY_WEB_FETCH_ENV, raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    target = tmp_path / "target"
    target.mkdir()
    return target.resolve()


def _fake_worker(captured: dict):
    def fake(request, on_process_group=None):
        run_home = Path(request.env["HOME"])
        captured["run_root"] = run_home.parent.parent
        conv = run_home / admission.AGY_RUN_HOME_CONVERSATIONS
        conv.mkdir(parents=True, exist_ok=True)
        (conv / "c1.db").write_bytes(b"tool-call: read_url")
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=_OK,
            stderr=b"",
            wall_time_ms=3,
            process_group_id=None,
            timed_out=False,
            descendants_swept=True,
        )

    return fake


def _invoke(target: Path, tmp_path: Path):
    adapter = AgyWorkerAdapter(canonical_root=_canonical(tmp_path))
    contract = SimpleNamespace(task_id="measure-row-1", maximum_provider_calls=1)
    return adapter.invoke(
        contract,
        SimpleNamespace(target_worktree=str(target)),
        prompt="bounded task",
        worker_role="implementation",
    )


def test_adapter_keeps_trace_before_deleting_run_root(monkeypatch, tmp_path, ready):
    trace = tmp_path / "trace"
    monkeypatch.setenv(admission.AGY_KEEP_TOOL_TRACE_ENV, "1")
    monkeypatch.setenv(admission.AGY_TOOL_TRACE_DIR_ENV, str(trace))
    captured: dict = {}
    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", _fake_worker(captured))

    receipt = _invoke(ready, tmp_path)

    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert not captured["run_root"].exists()
    (manifest_path,) = trace.glob("measure-row-1/*/manifest.json")
    assert manifest_path.parent.name == captured["run_root"].name
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    (entry,) = manifest["attempts"][0]["files"]
    assert entry["sha256"] == hashlib.sha256(b"tool-call: read_url").hexdigest()
    assert (manifest_path.parent / "attempt-1" / "c1.db").read_bytes() == b"tool-call: read_url"
    copied = {p.name for p in trace.rglob("*") if p.is_file()}
    assert copied == {"manifest.json", "c1.db"}


def test_adapter_writes_no_trace_by_default(monkeypatch, tmp_path, ready):
    monkeypatch.delenv(admission.AGY_KEEP_TOOL_TRACE_ENV, raising=False)
    monkeypatch.setenv(admission.AGY_TOOL_TRACE_DIR_ENV, str(tmp_path / "trace"))
    captured: dict = {}
    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", _fake_worker(captured))

    receipt = _invoke(ready, tmp_path)

    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert not captured["run_root"].exists()
    assert not (tmp_path / "trace").exists()
