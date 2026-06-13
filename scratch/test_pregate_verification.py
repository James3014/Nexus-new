from pathlib import Path
from nexus.engine.target_env_context import resolve_target_env
from nexus.engine.cli_pregate import build_verify_commands

def verify():
    engine_root = Path("/Users/jameschen/Workspace/nexus")
    task_id = "sympy__sympy-12096"
    
    print("--- Testing Target Environment Context Resolution ---")
    ctx = resolve_target_env(engine_root, task_id)
    print(f"Engine Root: {ctx.engine_root}")
    print(f"Target Repo Root: {ctx.target_repo_root}")
    print(f"Target Venv: {ctx.target_venv}")
    
    print("\n--- Testing Verify Command Generation ---")
    cmds = build_verify_commands(ctx)
    print(f"Verify Commands: {cmds}")
    
    # Assertions to verify correctness
    assert ctx.target_repo_root == engine_root / ".nexus" / "workspaces" / "sympy"
    assert ctx.target_venv == engine_root / ".venv_sympy"
    assert len(cmds) > 0
    assert "pytest" in cmds[0]
    assert ".venv_sympy/bin/python" in cmds[0]
    print("\n✅ Verification Successful! All paths and virtual environment commands resolved correctly.")

if __name__ == "__main__":
    verify()
