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
    """When interpreter is missing and allow_bare_python=False, context-missing is classified."""
    (tmp_path / "hello.py").write_text("x = 1\n", encoding="utf-8")
    
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["hello.py"],
        verifier_env_metadata={} # empty metadata -> no interpreter
    )
    assert res.passed is False
    assert res.error_message == "MICRO_VERIFY_CONTEXT_MISSING"
    assert "env_blocked" in res.classifications
    assert "false_fail_risk" in res.classifications
    assert "micro_verify_context_missing" in res.classifications


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


# ─── T2: Task-scoped verifier tests ──────────────────────────────────────────

def test_env_taxonomy_provides_task_scoped_interpreter(tmp_path):
    """env_taxonomy with interpreter field provides task-scoped context."""
    (tmp_path / "hello.py").write_text("x = 1\n", encoding="utf-8")
    
    import sys
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["hello.py"],
        verifier_env_metadata={},
        env_taxonomy={"interpreter": sys.executable},
    )
    assert res.passed is True
    assert res.task_scoped is True
    assert "task_scoped_verifier" in res.classifications


def test_env_taxonomy_verifier_command(tmp_path):
    """env_taxonomy with verifier_command field provides task-scoped context."""
    (tmp_path / "hello.py").write_text("x = 1\n", encoding="utf-8")
    
    import sys
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["hello.py"],
        verifier_env_metadata={},
        env_taxonomy={"verifier_command": sys.executable},
    )
    assert res.passed is True
    assert res.task_scoped is True


def test_no_context_no_taxonomy_fails_closed(tmp_path):
    """No interpreter, no taxonomy, no allow_bare_python → MICRO_VERIFY_CONTEXT_MISSING."""
    (tmp_path / "hello.py").write_text("x = 1\n", encoding="utf-8")
    
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["hello.py"],
        verifier_env_metadata={},
        env_taxonomy={},
    )
    assert res.passed is False
    assert res.error_message == "MICRO_VERIFY_CONTEXT_MISSING"
    assert res.task_scoped is False
    assert "micro_verify_context_missing" in res.classifications


def test_metadata_interpreter_not_task_scoped(tmp_path):
    """Raw metadata interpreter is NOT task-scoped (only env_taxonomy is)."""
    (tmp_path / "hello.py").write_text("x = 1\n", encoding="utf-8")
    
    import sys
    res = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=["hello.py"],
        verifier_env_metadata={"interpreter": sys.executable, "allow_bare_python": True},
        env_taxonomy={},
    )
    assert res.passed is True
    assert res.task_scoped is False  # metadata interpreter is not task-scoped
    assert "task_scoped_verifier" not in res.classifications
