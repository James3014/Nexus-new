"""local_heal retries run on a disposable World C copy, never on the caller's repo.

The repair loop resets its workspace each round (``git checkout -- .`` and
``git clean -fd`` in ``repo_dir``). The fence-error retry and the committee retry of
``LocalModelExecutor`` hand that loop a World C copy, as the delegated retry does, and
the reset refuses a ``repo_dir`` that is empty or relative (it would be the cwd).

Every repo here is a fresh ``git init`` under ``tmp_path``. Each test first moves the
cwd to a sentinel directory under ``tmp_path``. No model is called.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    _delegated_retry_world_c,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.local_heal.orchestrator import HealOrchestrator

DIRTY_EDIT = "x = 2  # uncommitted edit\n"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _repo_with_local_work(root: Path) -> Path:
    """A git repo with one uncommitted edit (notes.py) and one untracked file (SENTINEL)."""
    (root / "toy").mkdir(parents=True)
    (root / "toy" / "math_util.py").write_text("old\n", encoding="utf-8")
    (root / "file.py").write_text("def func():\n    pass\n", encoding="utf-8")
    (root / "notes.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "base")
    (root / "SENTINEL").write_text("local work\n", encoding="utf-8")
    (root / "notes.py").write_text(DIRTY_EDIT, encoding="utf-8")
    return root


def _assert_local_work_kept(root: Path) -> None:
    assert (root / "SENTINEL").read_text(encoding="utf-8") == "local work\n"
    assert (root / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


def _reset_workspace(repo_dir: Path) -> None:
    """The repair loop's per-round reset, called with only the fields it reads."""
    ctx = SimpleNamespace(op=SimpleNamespace(repo_dir=repo_dir))
    HealOrchestrator._reset_workspace(cast(Any, SimpleNamespace()), cast(Any, ctx))


@pytest.fixture
def sentinel_cwd(tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "SENTINEL").write_text("cwd\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("NEXUS_ROOT", raising=False)
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")
    monkeypatch.setenv("NEXUS_ARMOR_ARTIFACT_ROOT", str(tmp_path / "armor"))
    return cwd


@pytest.fixture
def pipeline_runs_reset(monkeypatch):
    """HealPipeline.run stand-in: runs the real per-round workspace reset on repo_dir."""
    seen: list[dict] = []

    def fake_run(self, heal_ctx):
        _reset_workspace(heal_ctx.repo_dir)
        seen.append({
            "instance_id": heal_ctx.instance_id,
            "repo_dir": Path(heal_ctx.repo_dir),
            "route_context": dict(heal_ctx.route_context or {}),
        })
        result = MagicMock()
        result.final_patch = ""
        result.pre_verification_final_patch = ""
        result.failure_reason = "stub"
        result.model_decisions = []
        result._orchestrator_verifier_evidence_passed = False
        result._orchestrator_verifier_evidence_fields = ""
        result._orchestrator_retry_prompt_evidence_hash = ""
        result._semantic_retry_telemetry = {}
        return result

    monkeypatch.setattr(
        "nexus.services.local_heal.pipeline.HealPipeline.__init__", lambda self, *a, **k: None
    )
    monkeypatch.setattr("nexus.services.local_heal.pipeline.HealPipeline.run", fake_run)
    return seen


def _assert_ran_on_a_copy(run: dict, source: Path) -> None:
    repo_dir = run["repo_dir"].resolve()
    assert repo_dir != source.resolve()
    assert not repo_dir.is_relative_to(source.resolve())
    assert run["route_context"]["world_c_source_root"] == str(source)
    assert run["route_context"]["world_c_workspace_path"] == str(run["repo_dir"])


def _apply_receipt(req) -> IsolatedApplyReceipt:
    return IsolatedApplyReceipt(
        task_id=req.task_id,
        patch_apply_status="applied",
        patch_apply_error="",
        target_file=req.target_file,
        selected_candidate_hash=req.selected_candidate_hash,
        applied_patch_hash=req.selected_candidate_hash,
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        workspace_path="/nonexistent/ws",
        mutation_allowed=True,
        applied_patch_hash_source="git_diff",
    )


def _verifier_receipt(req, status: str = "fail") -> IsolatedVerifierReceipt:
    return IsolatedVerifierReceipt(
        task_id=req.task_id,
        verifier_status=status,
        exit_code=0 if status == "pass" else 1,
        stdout_tail="" if status == "pass" else "AssertionError",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
    )


def test_reset_workspace_refuses_an_empty_repo_dir(tmp_path, sentinel_cwd):
    _git(sentinel_cwd, "init", "-q")
    assert Path("").is_dir()

    _reset_workspace(Path(""))

    assert (sentinel_cwd / "SENTINEL").read_text(encoding="utf-8") == "cwd\n"


def test_reset_workspace_refuses_a_relative_repo_dir(tmp_path, sentinel_cwd):
    _git(sentinel_cwd, "init", "-q")
    (sentinel_cwd / "sub").mkdir()
    _repo_with_local_work(sentinel_cwd / "sub" / "repo")

    _reset_workspace(Path("sub/repo"))
    _reset_workspace(Path("  "))

    _assert_local_work_kept(sentinel_cwd / "sub" / "repo")
    assert (sentinel_cwd / "SENTINEL").exists()


def test_source_repo_keeps_local_work_when_the_reset_runs_on_its_world_c_copy(
    tmp_path, sentinel_cwd
):
    source = _repo_with_local_work(tmp_path / "source_repo")
    request = LocalModelExecutorRequest(
        task_id="t-copy",
        problem_statement="p",
        repo_root=str(source),
        target_file="toy/math_util.py",
        selected_capabilities=("repair_loop",),
        evidence_refs=("ref",),
        route_context={},
    )
    workspace = _delegated_retry_world_c(request, {})

    _reset_workspace(Path(workspace))

    assert Path(workspace).resolve() != source.resolve()
    _assert_local_work_kept(source)
    assert (sentinel_cwd / "SENTINEL").exists()


@pytest.mark.parametrize(("name", "as_file"), [(".Git", False), (".GIT", True)])
def test_world_c_copy_omits_git_metadata_under_any_letter_case(
    tmp_path, sentinel_cwd, name, as_file
):
    # The name is built directly, so this does not depend on a case-insensitive file system.
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SENTINEL").write_text("outside\n", encoding="utf-8")
    source = tmp_path / "source_project"
    source.mkdir()
    (source / "pyproject.toml").write_text("[project]\nname = 't'\n", encoding="utf-8")
    (source / "mod.py").write_text("x = 1\n", encoding="utf-8")
    if as_file:
        (source / name).write_text(f"gitdir: {outside}\n", encoding="utf-8")
    else:
        (source / name).mkdir()
        (source / name / "config").write_text(
            f"[core]\n\tbare = false\n\tworktree = {outside}\n", encoding="utf-8"
        )
    request = LocalModelExecutorRequest(
        task_id="t-case",
        problem_statement="p",
        repo_root=str(source),
        target_file="mod.py",
        selected_capabilities=("repair_loop",),
        evidence_refs=("ref",),
        route_context={},
    )

    workspace = Path(_delegated_retry_world_c(request, {}))

    assert (workspace / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
    assert all(entry.casefold() != ".git" for entry in os.listdir(workspace))
    _reset_workspace(workspace)
    assert (outside / "SENTINEL").exists()
    assert (sentinel_cwd / "SENTINEL").exists()


@pytest.mark.parametrize("gitdir_file", [False, True])
def test_reset_leaves_an_outside_worktree_named_by_core_worktree_untouched(
    tmp_path, sentinel_cwd, monkeypatch, gitdir_file
):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    outside = tmp_path / "outside"
    (outside / "sub").mkdir(parents=True)
    (outside / "SENTINEL").write_text("outside\n", encoding="utf-8")
    (outside / "sub" / "SENTINEL").write_text("outside\n", encoding="utf-8")
    copy = tmp_path / "copy"
    copy.mkdir()
    (copy / "mod.py").write_text("x = 1\n", encoding="utf-8")
    if gitdir_file:
        # A gitdir file pointing at a git directory kept outside the copy.
        gitdir = tmp_path / "elsewhere"
        gitdir.mkdir()
        _git(gitdir, "init", "-q")
        (copy / ".git").write_text(f"gitdir: {gitdir / '.git'}\n", encoding="utf-8")
        _git(copy, "--git-dir", str(gitdir / ".git"), "config", "core.worktree", str(outside))
    else:
        _git(copy, "init", "-q")
        _git(copy, "config", "core.worktree", str(outside))

    _reset_workspace(copy)

    assert (outside / "SENTINEL").read_text(encoding="utf-8") == "outside\n"
    assert (outside / "sub" / "SENTINEL").read_text(encoding="utf-8") == "outside\n"
    assert (copy / "mod.py").exists()
    assert (sentinel_cwd / "SENTINEL").exists()


def test_reset_leaves_a_copy_whose_git_dir_lives_outside_it_untouched(
    tmp_path, sentinel_cwd, monkeypatch
):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    elsewhere = _repo_with_local_work(tmp_path / "elsewhere")
    copy = tmp_path / "copy"
    copy.mkdir()
    (copy / "SENTINEL").write_text("copy\n", encoding="utf-8")
    (copy / ".git").write_text(f"gitdir: {elsewhere / '.git'}\n", encoding="utf-8")

    _reset_workspace(copy)

    assert (copy / "SENTINEL").read_text(encoding="utf-8") == "copy\n"
    assert not (copy / "notes.py").exists()
    _assert_local_work_kept(elsewhere)
    assert (sentinel_cwd / "SENTINEL").exists()


def test_reset_still_cleans_a_normal_workspace_copy(tmp_path, sentinel_cwd, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    copy = _repo_with_local_work(tmp_path / "copy")

    _reset_workspace(copy)

    assert not (copy / "SENTINEL").exists()
    assert (copy / "notes.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (sentinel_cwd / "SENTINEL").exists()


def test_fence_error_retry_runs_on_a_world_c_copy(
    tmp_path, sentinel_cwd, pipeline_runs_reset, monkeypatch
):
    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )

    source = _repo_with_local_work(tmp_path / "source_repo")
    prose_patch = "```python\nHere is the fix:\ndef func():\n    return 1\n```"
    envelope = CandidateEnvelope(
        candidate_id="c-fence",
        task_id="fence-retry-copy",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(prose_patch.encode("utf-8")).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=prose_patch,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider, "generate_committee_candidates", lambda *a, **k: [envelope]
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-fence",
            selected_candidate_patch=prose_patch,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )
    req = LocalModelExecutorRequest(
        task_id="fence-retry-copy",
        problem_statement="test",
        repo_root=str(source),
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=("ref1",),
        dry_run=False,
        route_context={
            "locked_search": "def func():\n    pass",
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with (
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply",
            side_effect=_apply_receipt,
        ),
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_verifier",
            side_effect=_verifier_receipt,
        ),
    ):
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    assert (
        resp.raw_model_metadata.get("protocol_parse_error_kind")
        == "REPLACEMENT_PROSE_CONTAMINATION"
    )
    fence_runs = [run for run in pipeline_runs_reset if run["instance_id"] == "fence-retry-copy"]
    assert fence_runs, "the fence-error retry did not run"
    for run in fence_runs:
        _assert_ran_on_a_copy(run, source)
    _assert_local_work_kept(source)
    assert (sentinel_cwd / "SENTINEL").exists()


def test_committee_retry_runs_each_candidate_on_a_world_c_copy(
    tmp_path, sentinel_cwd, pipeline_runs_reset
):
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult

    source = _repo_with_local_work(tmp_path / "source_repo")
    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"
    req = LocalModelExecutorRequest(
        task_id="committee-retry-copy",
        problem_statement="test",
        repo_root=str(source),
        target_file="toy/math_util.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
        route_context={
            "verifier_command": ["python3", "-c", "raise SystemExit(1)"],
            "python_executable": "/nonexistent/venv/bin/python",
            "source_revision": "a" * 40,
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": [
                    "qwen2.5-coder:7b-instruct",
                    "deepseek-coder:6.7b-instruct",
                ],
            },
        },
    )

    with (
        patch(
            "nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute"
        ) as mock_exec,
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply",
            side_effect=_apply_receipt,
        ),
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_verifier",
            side_effect=_verifier_receipt,
        ),
    ):
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop",
            selected=True,
            invoked=True,
            gate_passed=True,
            outcome_contributed=True,
            evidence_present=True,
            failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text),
                "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
                "patch_synthesis_model_called": True,
                "provider_invoked": True,
                "model_called": True,
                "localheal_pipeline_run_called": True,
                "localheal_pipeline_run_success": True,
                "localheal_pipeline_invoked": True,
                "localheal_pipeline_actual_execution": True,
                "orchestrator_run_reachable": True,
                "path_a_actual_execution": True,
            },
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    assert resp.raw_model_metadata.get("delegated_retry_committee_path_used") is True
    committee_runs = [run for run in pipeline_runs_reset if "#committee-" in run["instance_id"]]
    assert len(committee_runs) == 2
    for run in committee_runs:
        _assert_ran_on_a_copy(run, source)
    assert committee_runs[0]["repo_dir"] != committee_runs[1]["repo_dir"]
    _assert_local_work_kept(source)
    assert (sentinel_cwd / "SENTINEL").exists()


# --- The reset runs no program the repository names -------------------------------------
# A retry workspace may hold a repository its candidate made. Each script below only touches
# a marker file under tmp_path; the test then checks the marker was never created.


def _marker_script(tmp_path: Path, name: str, marker: Path, *, passthrough: bool = False) -> Path:
    """A script that touches ``marker`` (and copies stdin to stdout if ``passthrough``)."""
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    script = tools / name
    body = f'#!/bin/sh\ntouch "{marker}"\n' + ("cat\n" if passthrough else "")
    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    return script


@pytest.fixture
def reset_env(tmp_path, sentinel_cwd, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return tmp_path


def _assert_reset_ran(copy: Path) -> None:
    assert not (copy / "SENTINEL").exists()
    assert (copy / "notes.py").read_text(encoding="utf-8") == "x = 1\n"


def test_reset_does_not_run_a_post_checkout_hook_the_candidate_created(reset_env):
    copy = _repo_with_local_work(reset_env / "copy")
    marker = reset_env / "hook-ran"
    hook = copy / ".git" / "hooks" / "post-checkout"
    hook.write_text(f'#!/bin/sh\ntouch "{marker}"\n', encoding="utf-8")
    hook.chmod(0o755)

    _reset_workspace(copy)

    assert not marker.exists()
    _assert_reset_ran(copy)
    assert (reset_env / "cwd" / "SENTINEL").exists()


@pytest.mark.parametrize("via_include", [False, True])
def test_reset_does_not_run_a_filter_the_candidate_configured(reset_env, via_include):
    copy = _repo_with_local_work(reset_env / "copy")
    (copy / ".gitattributes").write_text("*.py filter=mark\n", encoding="utf-8")
    _git(copy, "add", ".gitattributes")
    _git(copy, "commit", "-qm", "attributes")
    marker = reset_env / "filter-ran"
    script = _marker_script(reset_env, "filter.sh", marker, passthrough=True)
    drivers = f'[filter "mark"]\n\tsmudge = {script}\n\tclean = {script}\n'
    if via_include:
        (copy / ".git" / "extra.cfg").write_text(drivers, encoding="utf-8")
        _git(copy, "config", "include.path", "extra.cfg")
    else:
        with open(copy / ".git" / "config", "a", encoding="utf-8") as config:
            config.write(drivers)

    _reset_workspace(copy)

    assert not marker.exists()
    _assert_local_work_kept(copy)
    assert (reset_env / "cwd" / "SENTINEL").exists()


def test_reset_does_not_invoke_an_fsmonitor_the_candidate_configured(reset_env):
    copy = _repo_with_local_work(reset_env / "copy")
    marker = reset_env / "fsmonitor-ran"
    _git(copy, "config", "core.fsmonitor", str(_marker_script(reset_env, "fsmonitor.sh", marker)))

    _reset_workspace(copy)

    assert not marker.exists()
    _assert_reset_ran(copy)


@pytest.mark.parametrize(
    ("key", "value"), [("remote.origin.promisor", "true"), ("extensions.partialClone", "origin")]
)
def test_reset_leaves_a_repository_with_a_promisor_remote_untouched(reset_env, key, value):
    copy = _repo_with_local_work(reset_env / "copy")
    _git(copy, "config", "core.repositoryformatversion", "1")
    _git(copy, "config", "remote.origin.url", str(reset_env / "nowhere"))
    _git(copy, "config", key, value)

    _reset_workspace(copy)

    _assert_local_work_kept(copy)


def test_reset_leaves_a_repository_whose_config_includes_another_file_untouched(reset_env):
    copy = _repo_with_local_work(reset_env / "copy")
    # The included file can be written after the check, so an include alone refuses the reset.
    _git(copy, "config", "include.path", str(reset_env / "later.cfg"))

    _reset_workspace(copy)

    _assert_local_work_kept(copy)


def test_reset_does_not_enter_a_submodule_the_candidate_configured(reset_env):
    sub = reset_env / "sub"
    sub.mkdir()
    (sub / "f.py").write_text("a\n", encoding="utf-8")
    (sub / ".gitattributes").write_text("*.py filter=mark\n", encoding="utf-8")
    _git(sub, "init", "-q")
    _git(sub, "add", ".")
    _git(sub, "commit", "-qm", "sub")
    copy = _repo_with_local_work(reset_env / "copy")
    _git(copy, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "sub")
    _git(copy, "commit", "-qm", "submodule")
    marker = reset_env / "submodule-filter-ran"
    script = _marker_script(reset_env, "filter.sh", marker, passthrough=True)
    _git(copy / "sub", "config", "filter.mark.smudge", str(script))
    _git(copy / "sub", "config", "filter.mark.clean", str(script))
    _git(copy, "config", "submodule.recurse", "true")
    (copy / "sub" / "f.py").write_text("dirty\n", encoding="utf-8")

    _reset_workspace(copy)

    assert not marker.exists()
    _assert_reset_ran(copy)


def test_reset_restores_tracked_and_removes_untracked_files_under_a_foreign_git_environment(
    reset_env, monkeypatch
):
    copy = _repo_with_local_work(reset_env / "copy")
    elsewhere = _repo_with_local_work(reset_env / "elsewhere")
    marker = reset_env / "env-hook-ran"
    hooks = reset_env / "env-hooks"
    hooks.mkdir()
    (hooks / "post-checkout").write_text(f'#!/bin/sh\ntouch "{marker}"\n', encoding="utf-8")
    (hooks / "post-checkout").chmod(0o755)
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(elsewhere))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(hooks))

    _reset_workspace(copy)

    _assert_reset_ran(copy)
    _assert_local_work_kept(elsewhere)
    assert not marker.exists()


def test_every_reset_git_call_has_a_timeout_and_a_git_free_environment(reset_env, monkeypatch):
    copy = _repo_with_local_work(reset_env / "copy")
    monkeypatch.setenv("GIT_DIR", str(copy / ".git"))
    real_run = subprocess.run
    calls: list[tuple[list[str], dict]] = []

    def recording_run(args, **kwargs):
        calls.append((list(args), kwargs))
        return real_run(args, **kwargs)

    monkeypatch.setattr("nexus.services.local_heal.orchestrator.subprocess.run", recording_run)

    _reset_workspace(copy)

    _assert_reset_ran(copy)
    assert len(calls) >= 3
    for args, kwargs in calls:
        assert args[0] == "git"
        assert kwargs.get("timeout")
        env = kwargs.get("env")
        assert env is not None
        assert "GIT_DIR" not in env
        assert env.get("GIT_CONFIG_NOSYSTEM") == "1"
