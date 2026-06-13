from pathlib import Path
import pytest
from dataclasses import FrozenInstanceError
from nexus.engine.target_env_context import TargetEnvContext

def test_target_env_context_immutable():
    ctx = TargetEnvContext(
        engine_root=Path("/engine"),
        target_repo_root=Path("/repo"),
        target_venv=Path("/venv"),
        run_dir=Path("/run")
    )
    assert ctx.engine_root == Path("/engine")
    assert ctx.target_repo_root == Path("/repo")
    assert ctx.target_venv == Path("/venv")
    assert ctx.run_dir == Path("/run")
    
    with pytest.raises(FrozenInstanceError):
        ctx.engine_root = Path("/other")  # type: ignore

def test_resolve_target_env_fallback(tmp_path):
    from nexus.engine.target_env_context import resolve_target_env
    ctx = resolve_target_env(tmp_path, "unknown_task_123")
    assert ctx.engine_root == tmp_path
    assert ctx.target_repo_root == tmp_path
    assert ctx.target_venv is None

def test_resolve_target_env_sympy(tmp_path):
    from nexus.engine.target_env_context import resolve_target_env
    
    # Set up mock sympy directories
    sympy_repo = tmp_path / ".nexus" / "workspaces" / "sympy"
    sympy_repo.mkdir(parents=True)
    sympy_venv = tmp_path / ".venv_sympy"
    sympy_venv.mkdir()
    
    ctx = resolve_target_env(tmp_path, "sympy__sympy-12096")
    assert ctx.engine_root == tmp_path
    assert ctx.target_repo_root == sympy_repo
    assert ctx.target_venv == sympy_venv

def test_resolve_target_env_by_desc(tmp_path):
    from nexus.engine.target_env_context import resolve_target_env
    
    sympy_repo = tmp_path / ".nexus" / "workspaces" / "sympy"
    sympy_repo.mkdir(parents=True)
    sympy_venv = tmp_path / ".venv_sympy"
    sympy_venv.mkdir()
    
    ctx = resolve_target_env(tmp_path, "bug-123456", task_desc="sympy__sympy-12096")
    assert ctx.engine_root == tmp_path
    assert ctx.target_repo_root == sympy_repo
    assert ctx.target_venv == sympy_venv

def test_resolve_target_env_by_desc(tmp_path):
    from nexus.engine.target_env_context import resolve_target_env
    
    sympy_repo = tmp_path / ".nexus" / "workspaces" / "sympy"
    sympy_repo.mkdir(parents=True)
    sympy_venv = tmp_path / ".venv_sympy"
    sympy_venv.mkdir()
    
    ctx = resolve_target_env(tmp_path, "bug-123456", task_desc="sympy__sympy-12096")
    assert ctx.engine_root == tmp_path
    assert ctx.target_repo_root == sympy_repo
    assert ctx.target_venv == sympy_venv
