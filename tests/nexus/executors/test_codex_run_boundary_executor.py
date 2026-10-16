"""#2254: CodexCliExecutor runs codex in a disposable HOME and checks the target."""

import os
from pathlib import Path

from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.codex_executor import CodexCliExecutor
from tests.nexus.executors.test_codex_executor import _contract, _lease


def _executable(tmp_path: Path) -> Path:
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def _fake_worker(captured, mutate=None, refresh=False, stdout=b"{}\n"):
    def fake_worker(request, **_kwargs):
        captured["request"] = request
        home = Path((request.env or {}).get("HOME", "/nonexistent"))
        captured["home_existed"] = home.is_dir()
        captured["codex_home_files"] = (
            sorted(p.name for p in (home / ".codex").iterdir()) if home.is_dir() else []
        )
        if mutate is not None:
            mutate(Path(request.cwd))
        if refresh:
            (home / ".codex" / "auth.json").write_text('{"OPENAI_API_KEY":"new"}', encoding="utf-8")
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=stdout,
            stderr=b"",
            wall_time_ms=1,
            process_group_id=1,
        )

    return fake_worker


def _real_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "realhome"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text('{"OPENAI_API_KEY":"v"}', encoding="utf-8")
    (home / ".codex" / "history.jsonl").write_text("h\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("GH_TOKEN", "ghp_fake")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    return home


def test_codex_executor_runs_with_a_disposable_home_and_allowlisted_env(tmp_path, monkeypatch):
    real_home = _real_home(tmp_path, monkeypatch)
    contract = _contract(tmp_path)
    lease = _lease(tmp_path, contract)
    captured: dict = {}
    monkeypatch.setattr("nexus.executors.codex_executor.run_cli_worker", _fake_worker(captured))

    receipt = CodexCliExecutor(executable=str(_executable(tmp_path))).invoke(
        contract, lease, prompt="Edit only files allowed by the contract."
    )

    request = captured["request"]
    assert request.exact_env is True
    env = dict(request.env)
    assert Path(env["HOME"]) != real_home
    assert env["CODEX_HOME"] == str(Path(env["HOME"]) / ".codex")
    assert "GH_TOKEN" not in env and "SSH_AUTH_SOCK" not in env
    assert captured["home_existed"] is True
    assert captured["codex_home_files"] == ["auth.json"]
    assert not Path(env["HOME"]).exists()
    assert receipt.exit_code == 0 and receipt.failure_reason is None


def test_codex_executor_fails_the_run_on_a_planted_escaping_symlink(tmp_path, monkeypatch):
    _real_home(tmp_path, monkeypatch)
    contract = _contract(tmp_path)
    lease = _lease(tmp_path, contract)
    outside = tmp_path / "outside"
    outside.mkdir()
    captured: dict = {}
    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        _fake_worker(captured, lambda target: os.symlink(outside, target / "escape")),
    )

    receipt = CodexCliExecutor(executable=str(_executable(tmp_path))).invoke(
        contract, lease, prompt="Edit only files allowed by the contract."
    )

    assert receipt.exit_code == 1
    assert receipt.failure_reason == "codex_target_symlink_or_git_escape"


def test_codex_executor_fails_the_run_when_the_git_pointer_changes(tmp_path, monkeypatch):
    _real_home(tmp_path, monkeypatch)
    contract = _contract(tmp_path)
    lease = _lease(tmp_path, contract)
    (Path(lease.target_worktree) / ".git").write_text("gitdir: /real\n", encoding="utf-8")
    captured: dict = {}
    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        _fake_worker(
            captured,
            lambda target: (target / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8"),
        ),
    )

    receipt = CodexCliExecutor(executable=str(_executable(tmp_path))).invoke(
        contract, lease, prompt="Edit only files allowed by the contract."
    )

    assert receipt.exit_code == 1
    assert receipt.failure_reason == "codex_target_symlink_or_git_escape"


def test_codex_adapter_surfaces_the_typed_boundary_failure_reason(tmp_path, monkeypatch):
    from nexus.executors.worker_registry import CodexWorkerAdapter, WorkerPreflight

    contract = _contract(tmp_path)
    lease = _lease(tmp_path, contract)
    executable = str(_executable(tmp_path))
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        _fake_worker({}, lambda target: os.symlink(outside, target / "escape")),
    )
    _real_home(tmp_path, monkeypatch)
    executor = CodexCliExecutor(executable=executable)
    adapter = CodexWorkerAdapter(executor)
    monkeypatch.setattr(
        adapter,
        "preflight",
        lambda: WorkerPreflight(
            provider="codex",
            executable=executable,
            executable_available=True,
            authorized=True,
            implementation_status="IMPLEMENTED",
            ready=True,
            reason="ready",
        ),
    )

    receipt = adapter.invoke(contract, lease, prompt="Edit only files allowed by the contract.")

    assert receipt.outcome == "FAILED"
    assert receipt.failure_reason == "codex_target_symlink_or_git_escape"


def _run_with_refresh(tmp_path, monkeypatch, *, stdout=b"{}\n", mutate=None):
    real_home = _real_home(tmp_path, monkeypatch)
    contract = _contract(tmp_path)
    lease = _lease(tmp_path, contract)
    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        _fake_worker({}, mutate, refresh=True, stdout=stdout),
    )
    CodexCliExecutor(executable=str(_executable(tmp_path))).invoke(
        contract, lease, prompt="Edit only files allowed by the contract."
    )
    return (real_home / ".codex" / "auth.json").read_text(encoding="utf-8")


def test_codex_executor_writes_back_a_refreshed_token_after_a_clean_run(tmp_path, monkeypatch):
    assert _run_with_refresh(tmp_path, monkeypatch) == '{"OPENAI_API_KEY":"new"}'


def test_codex_executor_does_not_write_back_after_an_escape(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    body = _run_with_refresh(
        tmp_path, monkeypatch, mutate=lambda target: os.symlink(outside, target / "escape")
    )
    assert body == '{"OPENAI_API_KEY":"v"}'


def test_codex_executor_does_not_write_back_after_a_denied_action(tmp_path, monkeypatch):
    denied = b'{"type":"item.completed","item":{"type":"command_execution","status":"declined"}}\n'
    assert _run_with_refresh(tmp_path, monkeypatch, stdout=denied) == '{"OPENAI_API_KEY":"v"}'
