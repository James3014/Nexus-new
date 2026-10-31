"""#3023: the remaining host writes of a target file go through the contained-write helper.

- LocalModelExecutor restores the original target file after the pipeline run and after each
  committee candidate. Model code may have run in repo_root by then and left a link at the
  target or on the way to it: the restore must not write through it to a file outside
  repo_root, the snapshot reads around it must not record that file's text, and a refused
  committee restore stops the committee loop and is recorded.
- The committee routed tool writes the winning candidate to repo_root / target_file: a link
  there, or a target_file that leaves repo_root, is refused.
- contained_write gives a new file the permission bits a plain create would (0o666 & ~umask).
- With the process cwd at ``/``, an empty sys.path entry must not make every temp dir whose
  path is all identifiers count as host code.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexus.core.contained_write import write_text_in_root
from nexus.engine.model_output_sandbox import holds_host_code
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    _apply_candidate,
)
from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate

TARGET = "toy/math_util.py"
ORIGINAL = "def add(a, b):\n    return a - b\n"
HOST = "HOST FILE - must not change\n"
DIFF = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"


@pytest.fixture(autouse=True)
def _world_c_copies_of_tmp_repos(monkeypatch):
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")


@pytest.fixture
def repo_and_host(tmp_path):
    repo = tmp_path / "repo"
    (repo / "toy").mkdir(parents=True)
    (repo / TARGET).write_text(ORIGINAL)
    host = tmp_path / "host" / "secret.py"
    host.parent.mkdir()
    host.write_text(HOST)
    return repo, host


def _plant_link(repo: Path, host: Path) -> None:
    """What model code run in repo_root can do: replace the target with a link to a host file."""
    target = repo / TARGET
    target.unlink()
    target.symlink_to(host)


def _plant_parent_link(repo: Path, host: Path) -> None:
    """Same, one level up: the target's directory becomes a link to a host dir."""
    (host.parent / Path(TARGET).name).write_text(HOST)
    toy = repo / Path(TARGET).parent
    for child in toy.iterdir():
        child.unlink()
    toy.rmdir()
    toy.symlink_to(host.parent, target_is_directory=True)


def _assert_no_host_text_recorded(meta) -> None:
    dumped = json.dumps(meta, default=str)
    assert HOST.strip() not in dumped
    assert hashlib.sha256(HOST.encode()).hexdigest() not in dumped


def _request(repo: Path, task_id: str, candidate_models: list[str]) -> LocalModelExecutorRequest:
    snapshot = {
        "execution_topology": "localheal_pipeline",
        "model_call_allowed": True,
        "selected_executor": "local_model",
        "executor_model": "qwen2.5-coder:7b-instruct",
        "protocol_mode": "anchored_edit",
        "mutation_allowed": True,
        "verifier_allowed": True,
    }
    if candidate_models:
        snapshot["delegated_retry_candidate_models"] = candidate_models
    return LocalModelExecutorRequest(
        task_id=task_id,
        problem_statement="test",
        repo_root=str(repo),
        target_file=TARGET,
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
        route_context={
            "verifier_command": ["python3", "-c", "pass"],
            "python_executable": "python3",
            "signal_snapshot": snapshot,
        },
    )


def _pipeline_result(**_kw):
    return CapabilityExecutionResult(
        name="repair_loop",
        selected=True,
        invoked=True,
        gate_passed=True,
        outcome_contributed=True,
        evidence_present=True,
        failure_reason="",
        telemetries={
            "pipeline_final_patch": DIFF,
            "pipeline_solve_eligible": True,
            "pipeline_failure_reason": "",
            "patch_synthesis_output_len": len(DIFF),
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


def _apply_receipt(req):
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


def _verifier_fail(req):
    return IsolatedVerifierReceipt(
        task_id=req.task_id,
        verifier_status="fail",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
    )


def _committee_run_result(_heal_ctx):
    r = MagicMock()
    r.final_patch = DIFF
    r.pre_verification_final_patch = ""
    r.failure_reason = ""
    r._orchestrator_verifier_evidence_passed = False
    r._orchestrator_verifier_evidence_fields = ""
    r._orchestrator_retry_prompt_evidence_hash = ""
    r._semantic_retry_telemetry = {}
    r.model_decisions = [
        {
            "phase": "patch",
            "output_class": "UNIFIED_DIFF",
            "parser_error_kind": "none",
            "status": "SUCCESS",
            "output_excerpt": DIFF,
        }
    ]
    return r


def _run(req, *, pipeline_execute, committee_run):
    with (
        patch(
            "nexus.services.local_heal.local_model_capability_executors."
            "LocalHealPipelineCapabilityExecutor.execute",
            side_effect=pipeline_execute,
        ),
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply",
            side_effect=_apply_receipt,
        ),
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_verifier",
            side_effect=_verifier_fail,
        ),
        patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None),
        patch("nexus.services.local_heal.pipeline.HealPipeline.run", side_effect=committee_run),
    ):
        return LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: DIFF))


def test_restore_after_the_pipeline_run_does_not_write_through_a_planted_link(repo_and_host):
    repo, host = repo_and_host

    def pipeline_execute(*_a, **_kw):
        _plant_link(repo, host)
        return _pipeline_result()

    resp = _run(
        _request(repo, "restore-3023-a", []),
        pipeline_execute=pipeline_execute,
        committee_run=_committee_run_result,
    )
    assert host.read_text() == HOST
    meta = resp.raw_model_metadata
    assert meta["isolated_apply_status"] == "restore_refused"
    assert meta["isolated_apply_error"].startswith("TARGET_RESTORE_REFUSED:")
    assert meta["isolated_verifier_status"] == "not_run"
    _assert_no_host_text_recorded(meta)


def test_restore_refuses_a_link_on_the_way_to_the_target_and_records_nothing_from_it(
    repo_and_host,
):
    repo, host = repo_and_host

    def pipeline_execute(*_a, **_kw):
        _plant_parent_link(repo, host)
        return _pipeline_result()

    resp = _run(
        _request(repo, "restore-3023-d", []),
        pipeline_execute=pipeline_execute,
        committee_run=_committee_run_result,
    )
    assert host.read_text() == HOST
    assert (host.parent / Path(TARGET).name).read_text() == HOST
    meta = resp.raw_model_metadata
    assert meta["isolated_apply_status"] == "restore_refused"
    assert meta["isolated_verifier_status"] == "not_run"
    _assert_no_host_text_recorded(meta)


def test_restore_after_a_committee_candidate_does_not_write_through_a_planted_link(
    repo_and_host,
):
    repo, host = repo_and_host

    calls = []

    def committee_run(heal_ctx):
        calls.append(heal_ctx)
        if (repo / TARGET).is_symlink() is False:
            _plant_link(repo, host)
        return _committee_run_result(heal_ctx)

    resp = _run(
        _request(
            repo,
            "restore-3023-b",
            ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
        ),
        pipeline_execute=lambda *_a, **_kw: _pipeline_result(),
        committee_run=committee_run,
    )
    assert host.read_text() == HOST
    meta = resp.raw_model_metadata
    # The refusal is recorded and no later candidate runs against the planted link.
    assert meta["delegated_retry_committee_restore_refused"] is True
    assert meta["delegated_retry_committee_restore_refused_reason"].startswith(
        "restore-3023-b#delegated-retry-01-"
    )
    assert len(calls) == 1


def test_restore_still_puts_the_original_back_when_nothing_was_planted(repo_and_host):
    repo, _host = repo_and_host

    def committee_run(heal_ctx):
        (repo / TARGET).write_text("model wrote this\n")
        return _committee_run_result(heal_ctx)

    _run(
        _request(
            repo,
            "restore-3023-c",
            ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
        ),
        pipeline_execute=lambda *_a, **_kw: _pipeline_result(),
        committee_run=committee_run,
    )
    assert not (repo / TARGET).is_symlink()
    assert (repo / TARGET).read_text() == ORIGINAL


def _candidate(text: str) -> CanonicalPatchCandidate:
    return CanonicalPatchCandidate(
        source_format="search_replace",
        raw_output=text,
        raw_output_hash="h",
        normalized_patch=text,
        normalized_patch_hash="h",
        normalization_steps=(),
        safety_flags=(),
    )


def test_committee_routed_apply_refuses_a_link_and_a_path_outside_repo(repo_and_host):
    repo, host = repo_and_host
    _plant_link(repo, host)
    linked = _apply_candidate(
        _candidate("payload\n"),
        CommitteeRoutedToolRequest(task_id="t", repo_root=str(repo), target_file=TARGET),
    )
    assert linked["applied"] is False
    assert host.read_text() == HOST

    escaped = _apply_candidate(
        _candidate("payload\n"),
        CommitteeRoutedToolRequest(task_id="t", repo_root=str(repo), target_file="../escape.py"),
    )
    assert escaped["applied"] is False
    assert not (repo.parent / "escape.py").exists()

    ok = _apply_candidate(
        _candidate("payload\n"),
        CommitteeRoutedToolRequest(task_id="t", repo_root=str(repo), target_file="toy/new.py"),
    )
    assert ok["applied"] is True
    assert (repo / "toy/new.py").read_text() == "payload\n"


def test_a_new_file_gets_the_mode_a_plain_create_would(tmp_path):
    old = os.umask(0o002)
    try:
        write_text_in_root(tmp_path, "new.py", "x = 1\n")
        (tmp_path / "plain.py").write_text("x = 1\n")
    finally:
        os.umask(old)
    mode = (tmp_path / "new.py").stat().st_mode & 0o777
    assert mode == (tmp_path / "plain.py").stat().st_mode & 0o777 == 0o664


def test_cwd_at_filesystem_root_does_not_make_a_temp_dir_host_code(monkeypatch):
    # Under /tmp every component of mkdtemp()'s path is an identifier ("tmp", "tmpab12_x"), so
    # an empty sys.path entry resolved against cwd "/" used to claim it as importable host code.
    work = Path(tempfile.mkdtemp(dir="/tmp"))
    try:
        monkeypatch.chdir("/")
        monkeypatch.setattr(sys, "path", ["", *sys.path])
        assert holds_host_code(work) is False
        assert holds_host_code("/") is True
    finally:
        work.rmdir()


def test_removing_a_new_target_does_not_remove_a_file_behind_a_directory_link(repo_and_host):
    # The target did not exist before the run, so the cleanup removes it; a directory link
    # planted on the way must not turn that into removing a host file.
    repo, host = repo_and_host
    (repo / TARGET).unlink()

    def pipeline_execute(*_a, **_kw):
        _plant_parent_link(repo, host)
        return _pipeline_result()

    resp = _run(
        _request(repo, "restore-3023-e", []),
        pipeline_execute=pipeline_execute,
        committee_run=_committee_run_result,
    )
    assert (host.parent / Path(TARGET).name).read_text() == HOST
    meta = resp.raw_model_metadata
    assert meta["isolated_apply_status"] == "restore_refused"
    _assert_no_host_text_recorded(meta)
