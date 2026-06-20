import pytest
import sys
from pathlib import Path
from nexus.services.local_heal.micro_verifier import MicroVerifier, MicroVerifyResult


def test_generic_python3_not_full_verifier(tmp_path):
    """Bare python3 is not a full verifier, blocked by default when not allowed."""
    (tmp_path / "hello.py").write_text("print('hello')\n", encoding="utf-8")
    
    # 預設不允許 bare python3
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["hello.py"],
        verifier_env_metadata={"interpreter": "python3", "allow_bare_python": False}
    )
    assert res.passed is False
    assert res.error_message == "ENV_BLOCKED"
    assert "env_blocked" in res.classifications


def test_task_scoped_interpreter_recorded(tmp_path):
    """The specified interpreter is recorded in the result and used."""
    (tmp_path / "hello.py").write_text("print('hello')\n", encoding="utf-8")
    
    current_interpreter = sys.executable
    
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["hello.py"],
        verifier_env_metadata={"interpreter": current_interpreter, "allow_bare_python": False}
    )
    assert res.passed is True
    assert res.interpreter_used == current_interpreter
    assert "task_scoped_import_check" in res.classifications


def test_env_mismatch_classified(tmp_path):
    """When interpreter is missing and allow_bare_python=False, env_blocked is classified."""
    (tmp_path / "hello.py").write_text("x = 1\n", encoding="utf-8")
    
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["hello.py"],
        verifier_env_metadata={} # empty metadata -> no interpreter
    )
    assert res.passed is False
    assert res.error_message == "ENV_BLOCKED"
    assert "env_blocked" in res.classifications
    assert "false_fail_risk" in res.classifications


def test_syntax_parse_not_import_success(tmp_path):
    """Syntax check parses AST locally, while import check runs in subprocess; import failure behaves correctly."""
    # Syntax is valid, but importing it will fail due to a runtime import error
    (tmp_path / "bad_import.py").write_text("import non_existent_module_xyz\n", encoding="utf-8")
    
    current_interpreter = sys.executable
    
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["bad_import.py"],
        verifier_env_metadata={"interpreter": current_interpreter}
    )
    assert res.passed is False
    assert res.syntax_ok is True # Syntax parse is fine
    assert res.import_ok is False # Import fails
    assert res.error_message == "IMPORT_ERROR"
    assert "syntax_parse_check" in res.classifications
    assert "import_failed" in res.classifications


def test_verifier_command_context_preserved(tmp_path):
    """If pytest_command is specified, it will be used for test checks."""
    (tmp_path / "test_dummy.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    
    current_interpreter = sys.executable
    
    # We use python as mock pytest command to simulate FileNotFoundError or direct run
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["test_dummy.py"],
        verifier_env_metadata={
            "interpreter": current_interpreter,
            "pytest_command": "non_existent_pytest_cmd"
        }
    )
    # Since pytest command does not exist, it should fail with verifier_unavailable
    assert res.passed is False
    assert "verifier_unavailable" in res.classifications
    assert "test_failed" in res.classifications
