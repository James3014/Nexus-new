"""Unit tests for nexus.contracts.core_mutation_binding."""

from pathlib import Path
import pytest
import subprocess

from nexus.contracts.core_mutation_binding import (
    CORE_MUTATION_BINDING_SCHEMA,
    create_repository_mutation_binding,
    compute_binding_hash,
    derive_physical_changeset,
    verify_core_mutation_completion,
)


def test_create_and_verify_mutation_binding(tmp_path: Path):
    # Initialize a dummy git repo in tmp_path
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    test_file = tmp_path / "hello.txt"
    test_file.write_text("initial content\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=tmp_path, check=True)

    # 1. Pre-binding
    binding = create_repository_mutation_binding(
        operation_id="op-1234567890",
        attempt_id="att-01",
        repo_root=tmp_path,
        execution_lane="DIRECT_CANONICAL",
        allowed_files=["hello.txt"],
        verifier_commands=["git diff --check"],
        deletion_policy="FORBID",
    )

    assert binding.schema == CORE_MUTATION_BINDING_SCHEMA
    assert binding.operation_id == "op-1234567890"
    assert binding.binding_hash == compute_binding_hash(binding.to_dict())
    assert binding.core["acceptance_contract"]["allowed_paths"] == ["hello.txt"]

    # 2. Mutate file
    test_file.write_text("updated content\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "apply change"], cwd=tmp_path, check=True)

    target_tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # 3. Post-execution Core generic verification: PASS case
    result = verify_core_mutation_completion(
        binding=binding,
        repo_root=tmp_path,
        target_tree=target_tree,
        verifier_results={"git diff --check": True},
    )

    assert result["status"] == "VERIFIED"
    assert result["reason_codes"] == []
    assert result["integrity"] == "VALID"
    assert result["changed_files"] == ["hello.txt"]
    assert result["deleted_files"] == []


def test_scope_escape_fails_verification(tmp_path: Path):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    test_file = tmp_path / "hello.txt"
    test_file.write_text("initial content\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=tmp_path, check=True)

    binding = create_repository_mutation_binding(
        operation_id="op-scope-test",
        attempt_id="att-01",
        repo_root=tmp_path,
        execution_lane="DIRECT_CANONICAL",
        allowed_files=["hello.txt"],
        verifier_commands=["git diff --check"],
    )

    # Worker writes to an unauthorized path
    escaped_file = tmp_path / "escaped.txt"
    escaped_file.write_text("unauthorized write\n")
    subprocess.run(["git", "add", "escaped.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "escaped commit"], cwd=tmp_path, check=True)

    target_tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    result = verify_core_mutation_completion(
        binding=binding,
        repo_root=tmp_path,
        target_tree=target_tree,
        verifier_results={"git diff --check": True},
    )

    assert result["status"] == "FAILED_VERIFICATION"
    assert "SCOPE_ESCAPE" in result["reason_codes"]


def test_forbidden_deletion_fails_verification(tmp_path: Path):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    test_file = tmp_path / "hello.txt"
    test_file.write_text("initial content\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=tmp_path, check=True)

    binding = create_repository_mutation_binding(
        operation_id="op-del-test",
        attempt_id="att-01",
        repo_root=tmp_path,
        execution_lane="DIRECT_CANONICAL",
        allowed_files=["hello.txt"],
        verifier_commands=["git diff --check"],
        deletion_policy="FORBID",
    )

    # Worker deletes hello.txt
    test_file.unlink()
    subprocess.run(["git", "rm", "hello.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "delete file"], cwd=tmp_path, check=True)

    target_tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    result = verify_core_mutation_completion(
        binding=binding,
        repo_root=tmp_path,
        target_tree=target_tree,
        verifier_results={"git diff --check": True},
    )

    assert result["status"] == "FAILED_VERIFICATION"
    assert "DELETION_FORBIDDEN" in result["reason_codes"] or "SCOPE_ESCAPE" in result["reason_codes"]


def test_failed_verifier_fails_verification(tmp_path: Path):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    test_file = tmp_path / "hello.txt"
    test_file.write_text("initial content\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=tmp_path, check=True)

    binding = create_repository_mutation_binding(
        operation_id="op-verifier-fail",
        attempt_id="att-01",
        repo_root=tmp_path,
        execution_lane="DIRECT_CANONICAL",
        allowed_files=["hello.txt"],
        verifier_commands=["pytest test_foo.py"],
    )

    test_file.write_text("modified\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "modified"], cwd=tmp_path, check=True)

    target_tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    result = verify_core_mutation_completion(
        binding=binding,
        repo_root=tmp_path,
        target_tree=target_tree,
        verifier_results={"pytest test_foo.py": False},  # Verifier failed
    )

    assert result["status"] == "FAILED_VERIFICATION"
    assert "pytest test_foo.py" in result["reason_codes"] or "VERIFIER_FAILED" in result["reason_codes"]
