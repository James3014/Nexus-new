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


@pytest.mark.parametrize("replacement_kind", ["directory", "symlink"])
def test_micro_verifier_requires_captured_workspace_identity(
    tmp_path, monkeypatch, replacement_kind
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    identity = root_identity(workspace)
    if replacement_kind == "directory":
        workspace.rename(tmp_path / "workspace-original")
        workspace.mkdir()
    else:
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


def test_isolated_verifier_blocks_relative_workspace_path(tmp_path, monkeypatch):
    from nexus.services.local_heal import isolated_verifier

    called = False

    def run_model(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("relative workspace must be refused before sandbox entry")

    monkeypatch.setattr(isolated_verifier, "run_model_argv", run_model)
    receipt = run_isolated_verifier(
        IsolatedVerifierRequest(
            task_id="relative-workspace",
            workspace_path="relative-workspace",
            workspace_identity=root_identity(tmp_path),
            verifier_command=("python", "-c", "pass"),
            verifier_allowed=True,
        )
    )

    assert receipt.verifier_status == "blocked"
    assert "workspace_path_not_absolute" in receipt.verifier_error
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


@pytest.mark.parametrize("replacement_kind", ["directory", "symlink"])
def test_pinned_root_rejects_workspace_replaced_at_original_path(tmp_path, replacement_kind):
    from nexus.core.contained_write import PinnedRoot

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    identity = root_identity(workspace)
    original = tmp_path / "workspace-original"
    workspace.rename(original)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    if replacement_kind == "directory":
        workspace.mkdir()
    else:
        workspace.symlink_to(replacement, target_is_directory=True)

    with pytest.raises(SandboxError, match="work_dir_replaced"):
        _bind_root(PinnedRoot(str(workspace), identity), "work_dir")


def test_pinned_root_rejects_relative_workspace_path(tmp_path):
    from nexus.core.contained_write import PinnedRoot

    with pytest.raises(SandboxError, match="work_dir_replaced"):
        _bind_root(PinnedRoot("relative-workspace", root_identity(tmp_path)), "work_dir")


def test_resolved_workspace_under_symlink_parent_is_accepted(tmp_path):
    from nexus.core.contained_write import PinnedRoot

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    alias_parent = tmp_path / "alias-parent"
    alias_parent.symlink_to(real_parent, target_is_directory=True)
    workspace = alias_parent / "workspace"
    workspace.mkdir()
    resolved_workspace = workspace.resolve()

    bound, _ = _bind_root(
        PinnedRoot(str(resolved_workspace), root_identity(resolved_workspace)), "work_dir"
    )

    assert bound == resolved_workspace


def test_audit_verifier_passes_workspace_identity(tmp_path, monkeypatch):
    from nexus.services.local_heal import isolated_verifier

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured = {}

    def run(request):
        captured["request"] = request
        return isolated_verifier.IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

    monkeypatch.setattr(isolated_verifier, "run_isolated_verifier", run)
    from scripts.ops.capability_wiring_audit import make_verifier

    make_verifier(
        workspace,
        ("python", "-c", "pass"),
        "audit-task",
        root_identity(workspace),
    )({})

    assert captured["request"].workspace_identity == root_identity(workspace)


def test_canary_resolves_workspace_under_symlink_parent(tmp_path, monkeypatch):
    from nexus.services import product_capability_canary_helper as helper
    from nexus.services.local_heal import isolated_verifier

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    alias_parent = tmp_path / "alias-parent"
    alias_parent.symlink_to(real_parent, target_is_directory=True)
    original_path = Path

    def canary_path(*parts):
        if parts == ("/tmp/nexus_family_canary",):
            return alias_parent
        return original_path(*parts)

    captured = {}

    def run_mainchain(_request, *, verifier, **_kwargs):
        return verifier({"task_id": "task", "capability_evidence_bundle": {}})

    def run_verifier(request):
        captured["request"] = request
        return isolated_verifier.IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

    monkeypatch.setattr(helper, "Path", canary_path)
    monkeypatch.setattr(helper, "run_mainchain", run_mainchain)
    monkeypatch.setattr(isolated_verifier, "run_isolated_verifier", run_verifier)

    helper._run_canary_mainchain_cached(
        "semantic_searcher", positive=False, task_id_override="task"
    )

    request = captured["request"]
    assert Path(request.workspace_path) == Path(request.workspace_path).resolve()
    assert request.workspace_identity == root_identity(Path(request.workspace_path))


def test_same_oracle_rejects_execution_identity_drift_before_verifier(tmp_path, monkeypatch):
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierRequest
    from nexus.services.local_heal.phases import verification

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    held_workspace = verification._HeldWorkspace(
        path=workspace,
        descriptor=-1,
        file_id=root_identity(workspace),
    )
    request = IsolatedVerifierRequest(
        task_id="task",
        workspace_path=str(workspace),
        verifier_command=("python", "-c", "pass"),
        verifier_allowed=True,
        workspace_identity=(held_workspace.file_id[0], held_workspace.file_id[1] + 1),
    )
    called = False

    def run(_request):
        nonlocal called
        called = True

    monkeypatch.setattr(verification, "run_isolated_verifier", run)

    receipt, reason = verification._execute(
        frozen=None,
        identity_request=None,
        execution_request=request,
        held=None,
        sealed=None,
        workspace=held_workspace,
        prefix="CANDIDATE",
    )

    assert receipt is None
    assert reason == "CANDIDATE_WORKSPACE_IDENTITY_DRIFT"
    assert not called


def test_preimage_retry_receipt_carries_workspace_identity(tmp_path, monkeypatch):
    import subprocess

    from nexus.services.local_heal import isolated_workspace_apply as apply_mod

    source = tmp_path / "source"
    source.mkdir()
    (source / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    bad_diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-nothing like it\n+x = 2\n"
    seen = {}

    def _retry(**kwargs):
        seen["tmpdir"] = kwargs["tmpdir"]
        return apply_mod.IsolatedApplyReceipt(
            task_id="t",
            workspace_path=kwargs["tmpdir"],
            target_file="a.py",
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash="h",
            applied_patch_hash="p",
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
        )

    monkeypatch.setattr("nexus.experimental.c6bd_preimage_retry.run_c6bd_preimage_retry", _retry)
    receipt = apply_mod.run_isolated_workspace_apply(
        apply_mod.IsolatedApplyRequest(
            task_id="t",
            source_root=str(source),
            target_file="a.py",
            unified_diff=bad_diff,
            selected_candidate_hash="h",
            mutation_allowed=True,
            search_text="x = 1",
        )
    )
    assert seen, "preimage retry was not reached"
    assert receipt.workspace_identity == root_identity(seen["tmpdir"])
