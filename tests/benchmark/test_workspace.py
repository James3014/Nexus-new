import subprocess

from nexus.benchmark.workspace import BenchmarkWorkspace


def test_benchmark_workspace_isolates_fixture_from_main_worktree(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    target = tmp_path / "nexus" / "engine" / "phases"
    target.mkdir(parents=True)
    main_file = target / "research.py"
    original_text = "#!/usr/bin/env python3\nimport json\nimport os\n"
    main_file.write_text(original_text, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)

    workspace = BenchmarkWorkspace(tmp_path, "OFF-001", tmp_path / ".nexus" / "runs" / "bench-case")
    workspace_root = workspace.create()
    fixture = workspace.apply_fixture(
        {
            "benchmark_fixture": {
                "file": "nexus/engine/phases/research.py",
                "target": "import os\n",
                "replacement": "",
            }
        }
    )

    workspace_file = workspace_root / "nexus" / "engine" / "phases" / "research.py"
    assert workspace_file.read_text(encoding="utf-8") == "#!/usr/bin/env python3\nimport json\n"
    assert main_file.read_text(encoding="utf-8") == original_text

    diff = subprocess.run(
        ["git", "diff", "--cached", "--", "nexus/engine/phases/research.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert diff.stdout == ""

    workspace.restore_fixture(fixture)
    assert workspace_file.read_text(encoding="utf-8") == original_text
    workspace.cleanup()


def test_workspace_create_retries_after_stale_worktree(monkeypatch, tmp_path):
    workspace = BenchmarkWorkspace(tmp_path, "OFF-001", tmp_path / ".nexus" / "runs" / "bench-case")
    calls = []

    def fake_run(cmd, check=False, capture_output=False, text=False):
        calls.append(cmd)
        if cmd[3:5] == ["worktree", "add"]:
            add_calls = len([c for c in calls if c[3:5] == ["worktree", "add"]])
            if add_calls == 1:
                raise subprocess.CalledProcessError(128, cmd, stderr="already exists")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("nexus.benchmark.workspace.subprocess.run", fake_run)
    monkeypatch.setattr("nexus.benchmark.workspace.shutil.rmtree", lambda *_args, **_kwargs: None)

    workspace.create()

    add_calls = [c for c in calls if c[3:5] == ["worktree", "add"]]
    prune_calls = [c for c in calls if c[3:5] == ["worktree", "prune"]]
    assert len(add_calls) == 2
    assert prune_calls


def test_workspace_create_raises_runtime_error_after_retry_failure(monkeypatch, tmp_path):
    workspace = BenchmarkWorkspace(tmp_path, "OFF-001", tmp_path / ".nexus" / "runs" / "bench-case")

    def fake_run(cmd, check=False, capture_output=False, text=False):
        if cmd[3:5] == ["worktree", "add"]:
            raise subprocess.CalledProcessError(128, cmd, stderr="fatal: add failed")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("nexus.benchmark.workspace.subprocess.run", fake_run)
    monkeypatch.setattr("nexus.benchmark.workspace.shutil.rmtree", lambda *_args, **_kwargs: None)

    try:
        workspace.create()
    except RuntimeError as exc:
        assert "git worktree add failed" in str(exc)
        assert "fatal: add failed" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")
