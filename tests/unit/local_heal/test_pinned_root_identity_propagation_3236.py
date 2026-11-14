from pathlib import Path

import pytest

from nexus.core.contained_write import root_identity
from nexus.engine.model_output_sandbox import SandboxError, _bind_root
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierRequest,
    run_isolated_verifier,
)
from nexus.services.local_heal.micro_verifier import MicroVerifier


def _replace_with_symlink(root: Path, target: Path) -> None:
    root.rename(root.with_name(f"{root.name}-original"))
    root.symlink_to(target, target_is_directory=True)


def test_isolated_verifier_rejects_workspace_replaced_after_selection(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    identity = root_identity(workspace)
    _replace_with_symlink(workspace, replacement)
    called = False

    def run_model(*args, **kwargs):
        nonlocal called
        called = True
        _bind_root(kwargs["work_dir"], "work_dir")
        raise AssertionError("replacement unexpectedly passed root binding")

    monkeypatch.setattr("nexus.services.local_heal.isolated_verifier.run_model_argv", run_model)
    receipt = run_isolated_verifier(
        IsolatedVerifierRequest(
            task_id="task",
            workspace_path=str(workspace),
            workspace_identity=identity,
            verifier_command=("python", "-c", "pass"),
            verifier_allowed=True,
        )
    )

    assert receipt.verifier_status == "blocked"
    assert "replaced" in receipt.verifier_error
    assert called
    assert list(replacement.iterdir()) == []


def test_evaluation_gate_rejects_copy_replaced_after_identity_capture(tmp_path, monkeypatch):
    from nexus.services.local_heal import evaluation_gate as gate

    source = tmp_path / "source"
    source.mkdir()
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    original_identity = gate.root_identity

    def capture_then_replace(root):
        identity = original_identity(root)
        if Path(root).name.startswith("eval-gate-"):
            Path(root).rename(Path(root).with_name(f"{Path(root).name}-original"))
            Path(root).symlink_to(replacement, target_is_directory=True)
        return identity

    def run_model(*args, **kwargs):
        _bind_root(kwargs["work_dir"], "work_dir")
        raise AssertionError("replacement unexpectedly passed root binding")

    monkeypatch.setattr(gate, "root_identity", capture_then_replace)
    monkeypatch.setattr(gate, "run_model_argv", run_model)
    with pytest.raises(SandboxError, match="replaced"):
        gate.EvaluationGate(source)._run_confined(["python", "-c", "pass"], 1)
    assert list(replacement.iterdir()) == []


def test_reproduction_rejects_copy_replaced_after_identity_capture(tmp_path, monkeypatch):
    from nexus.services.local_heal import reproduction

    source = tmp_path / "source"
    source.mkdir()
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    original_identity = reproduction.root_identity

    def capture_then_replace(root):
        identity = original_identity(root)
        if Path(root).name.startswith("repro-run-"):
            Path(root).rename(Path(root).with_name(f"{Path(root).name}-original"))
            Path(root).symlink_to(replacement, target_is_directory=True)
        return identity

    def run_model(*args, **kwargs):
        _bind_root(kwargs["work_dir"], "work_dir")
        raise AssertionError("replacement unexpectedly passed root binding")

    monkeypatch.setattr(reproduction, "root_identity", capture_then_replace)
    monkeypatch.setattr(reproduction, "run_model_argv", run_model)
    passed, output = reproduction.ReproductionRunner(source).run_repro("assert False")
    assert not passed
    assert "replaced" in output
    assert list(replacement.iterdir()) == []


def test_micro_scratch_copy_rejects_replacement_after_identity_capture(tmp_path, monkeypatch):
    from nexus.services.local_heal import micro_verifier as micro

    source = tmp_path / "source"
    source.mkdir()
    (source / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    original_copy = micro.copy_repo_entries

    def copy_then_replace(source_root, target_root):
        original_copy(source_root, target_root)
        target = Path(target_root)
        target.rename(target.with_name(f"{target.name}-original"))
        target.symlink_to(replacement, target_is_directory=True)

    def run_model(*args, **kwargs):
        raise AssertionError("replaced workspace must be rejected before sandbox entry")

    monkeypatch.setattr(micro, "copy_repo_entries", copy_then_replace)
    monkeypatch.setattr(micro, "run_model_argv", run_model)
    result = micro.micro_verify_in_scratch_copy(
        "",
        source,
        ["test_ok.py"],
        verifier_env_metadata={"interpreter": "python3", "allow_bare_python": True},
        env_taxonomy={"interpreter": "python3"},
    )
    assert not result.passed
    assert result.error_message == "MICRO_VERIFY_ROOT_REPLACED"
    assert list(replacement.iterdir()) == []


def test_micro_verifier_requires_captured_workspace_identity(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    identity = root_identity(workspace)
    _replace_with_symlink(workspace, replacement)
    called = False

    def run_model(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("sandbox must reject the replaced workspace")

    monkeypatch.setattr("nexus.services.local_heal.micro_verifier.run_model_argv", run_model)
    result = MicroVerifier.verify(
        patch_content="",
        repo_dir=workspace,
        workspace_identity=identity,
        patched_files=[],
        verifier_env_metadata={"interpreter": "python3", "allow_bare_python": True},
        env_taxonomy={"interpreter": "python3"},
    )

    assert not result.passed
    assert result.error_message == "MICRO_VERIFY_ROOT_REPLACED"
    assert not called
    assert list(replacement.iterdir()) == []


def test_isolated_verifier_without_workspace_identity_blocks_before_sandbox(tmp_path, monkeypatch):
    called = False

    def run_model(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("missing identity must block before sandbox entry")

    monkeypatch.setattr("nexus.services.local_heal.isolated_verifier.run_model_argv", run_model)
    receipt = run_isolated_verifier(
        IsolatedVerifierRequest(
            task_id="task",
            workspace_path=str(tmp_path),
            verifier_command=("python", "-c", "pass"),
            verifier_allowed=True,
        )
    )

    assert receipt.verifier_status == "blocked"
    assert "identity_missing" in receipt.verifier_error
    assert not called


def test_micro_verifier_without_workspace_identity_blocks_before_reads(tmp_path, monkeypatch):
    called = False

    def run_model(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("missing identity must block before sandbox entry")

    monkeypatch.setattr("nexus.services.local_heal.micro_verifier.run_model_argv", run_model)
    result = MicroVerifier.verify(
        patch_content="",
        repo_dir=tmp_path,
        patched_files=[],
        verifier_env_metadata={"interpreter": "python3", "allow_bare_python": True},
    )

    assert not result.passed
    assert result.error_message == "MICRO_VERIFY_ROOT_IDENTITY_MISSING"
    assert not called
