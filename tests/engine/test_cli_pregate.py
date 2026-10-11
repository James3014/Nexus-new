from pathlib import Path
import pytest
from nexus.engine.cli_pregate import run_cli_pregate, _auto_detect_verify_commands

def test_run_cli_pregate_success(tmp_path):
    all_passed, results = run_cli_pregate(tmp_path, ["echo ok", "echo success"])
    assert all_passed is True
    assert len(results) == 2
    assert results[0]["exit_code"] == 0
    assert "ok" in results[0]["stdout_tail"]

def test_run_cli_pregate_failure(tmp_path):
    all_passed, results = run_cli_pregate(tmp_path, ["echo ok", "exit 1"])
    assert all_passed is False
    assert len(results) == 2
    assert results[0]["exit_code"] == 0
    assert results[1]["exit_code"] != 0
    assert results[1]["passed"] is False

def test_run_cli_pregate_timeout(tmp_path):
    # sleep for 3 seconds but timeout is 1
    all_passed, results = run_cli_pregate(tmp_path, ["sleep 3"], timeout_per_cmd=1)
    assert all_passed is False
    assert len(results) == 1
    assert results[0]["exit_code"] == 124

def test_auto_detect_python(tmp_path):
    (tmp_path / "pytest.ini").write_text("")
    cmds = _auto_detect_verify_commands(tmp_path)
    assert len(cmds) == 1
    assert "pytest" in cmds[0]

def test_auto_detect_rust(tmp_path):
    (tmp_path / "Cargo.toml").write_text("")
    cmds = _auto_detect_verify_commands(tmp_path)
    assert len(cmds) == 1
    assert "cargo test" in cmds[0]

def test_auto_detect_go(tmp_path):
    (tmp_path / "go.mod").write_text("")
    cmds = _auto_detect_verify_commands(tmp_path)
    assert len(cmds) == 1
    assert "go test" in cmds[0]

def test_auto_detect_node(tmp_path):
    import json
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
    cmds = _auto_detect_verify_commands(tmp_path)
    assert len(cmds) == 1
    assert "npm test" in cmds[0]


def test_pregate_runs_without_shell_and_without_github_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_OWNERTOKEN_must_not_leak")
    code = "import os;print('GH_TOKEN' in os.environ)"
    all_passed, results = run_cli_pregate(tmp_path, [f"python3 -c \"{code}\""])
    assert all_passed is True
    assert results[0]["stdout_tail"].strip() == "False"


@pytest.mark.parametrize(
    "cmd",
    [
        'echo a; git push origin HEAD:main',
        "echo a && touch PWNED",
        "sh -c 'touch PWNED'",
        "git -C . push origin HEAD:main",
        "echo $(touch PWNED)",
    ],
)
def test_pregate_rejects_shell_constructs_and_forbidden_commands(tmp_path, cmd):
    all_passed, results = run_cli_pregate(tmp_path, [cmd])
    assert all_passed is False
    assert results[0]["passed"] is False
    assert not (tmp_path / "PWNED").exists()
