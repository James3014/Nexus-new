from pathlib import Path

from nexus.pilot_cli.workspace_ops import clone_repo
from nexus.pilot_cli.workspace_ops import default_clone_dir
from nexus.pilot_cli.workspace_ops import infer_repo_name
from nexus.pilot_cli.workspace_ops import is_repo_url


def test_is_repo_url_recognizes_github_urls():
    assert is_repo_url("https://github.com/example/repo.git") is True
    assert is_repo_url("git@github.com:example/repo.git") is True
    assert is_repo_url("/tmp/local-repo") is False


def test_infer_repo_name_strips_git_suffix():
    assert infer_repo_name("https://github.com/example/repo.git") == "repo"


def test_default_clone_dir_uses_tenant_root(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_PILOT_WORKSPACE_ROOT", str(tmp_path))
    target = default_clone_dir("pilot_a", "https://github.com/example/repo.git")
    assert target == tmp_path / "pilot_a" / "repo"


def test_clone_repo_runs_git_clone(monkeypatch, tmp_path):
    calls = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, capture_output, text, check):
        calls["cmd"] = cmd
        return Result()

    monkeypatch.setattr("nexus.pilot_cli.workspace_ops.subprocess.run", fake_run)

    target = clone_repo(
        "https://github.com/example/repo.git",
        "pilot_a",
        dest=str(tmp_path / "repo"),
    )
    assert target == Path(tmp_path / "repo")
    assert calls["cmd"] == ["git", "clone", "https://github.com/example/repo.git", str(tmp_path / "repo")]
