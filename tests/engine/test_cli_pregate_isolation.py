from pathlib import Path
import pytest
import json
from nexus.engine.target_env_context import TargetEnvContext
from nexus.engine.cli_pregate import (
    detect_project_language,
    resolve_target_python,
    build_verify_commands,
    _auto_detect_verify_commands,
    run_cli_pregate
)

def test_detect_project_language_python(tmp_path):
    (tmp_path / "pytest.ini").write_text("")
    langs = detect_project_language(tmp_path)
    assert "python" in langs

def test_detect_project_language_rust(tmp_path):
    (tmp_path / "Cargo.toml").write_text("")
    langs = detect_project_language(tmp_path)
    assert "rust" in langs

def test_detect_project_language_go(tmp_path):
    (tmp_path / "go.mod").write_text("")
    langs = detect_project_language(tmp_path)
    assert "go" in langs

def test_detect_project_language_node(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
    langs = detect_project_language(tmp_path)
    assert "node" in langs

def test_resolve_target_python_uses_target_venv(tmp_path):
    engine_root = tmp_path / "engine"
    target_repo_root = tmp_path / "target"
    target_venv = tmp_path / "target_venv"
    
    engine_root.mkdir()
    target_repo_root.mkdir()
    target_venv.mkdir()
    
    # Create mock python in target_venv/bin/python3
    bin_dir = target_venv / "bin"
    bin_dir.mkdir()
    mock_python = bin_dir / "python3"
    mock_python.write_text("")
    mock_python.chmod(0o755)
    
    ctx = TargetEnvContext(
        engine_root=engine_root,
        target_repo_root=target_repo_root,
        target_venv=target_venv
    )
    
    resolved = resolve_target_python(ctx)
    assert resolved == str(mock_python)

def test_build_verify_commands_uses_target_repo(tmp_path):
    engine_root = tmp_path / "engine"
    target_repo_root = tmp_path / "target"
    target_venv = tmp_path / "target_venv"
    
    engine_root.mkdir()
    target_repo_root.mkdir()
    target_venv.mkdir()
    
    # Write python files to target repo (not engine_root!)
    (target_repo_root / "pytest.ini").write_text("")
    
    # Mock target venv python
    bin_dir = target_venv / "bin"
    bin_dir.mkdir()
    mock_python = bin_dir / "python3"
    mock_python.write_text("")
    
    ctx = TargetEnvContext(
        engine_root=engine_root,
        target_repo_root=target_repo_root,
        target_venv=target_venv
    )
    
    cmds = build_verify_commands(ctx)
    assert len(cmds) == 1
    assert str(mock_python) in cmds[0]
    assert "pytest" in cmds[0]

def test_backward_compat_no_target_env(tmp_path):
    # If using deprecated _auto_detect_verify_commands, it should work like before
    (tmp_path / "pytest.ini").write_text("")
    cmds = _auto_detect_verify_commands(tmp_path)
    assert len(cmds) == 1
    assert "pytest" in cmds[0]

def test_run_cli_pregate_uses_target_env_context(tmp_path):
    engine_root = tmp_path / "engine"
    target_repo_root = tmp_path / "target"
    target_venv = tmp_path / "target_venv"
    
    engine_root.mkdir()
    target_repo_root.mkdir()
    target_venv.mkdir()
    
    # Create bin/Scripts directory and python mock
    bin_dir = target_venv / "bin"
    bin_dir.mkdir()
    mock_python = bin_dir / "python3"
    mock_python.write_text("")
    
    ctx = TargetEnvContext(
        engine_root=engine_root,
        target_repo_root=target_repo_root,
        target_venv=target_venv
    )
    
    passed, results = run_cli_pregate(ctx, ["echo hello"])
    assert passed is True
    assert len(results) == 1
    assert "hello" in results[0]["stdout_tail"]
