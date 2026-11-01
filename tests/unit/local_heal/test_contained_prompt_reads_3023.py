"""#3023: host reads of the target whose text reaches a model prompt never follow a link.

LocalModelExecutor reads the current target file in three more places:

- the original snapshot before the pipeline run, later re-anchored against and written back;
- the committee / delegated-retry pre-fill of ``localized_files`` (the committee prompt);
- the ``source_context`` lines of the single-model unified-diff prompt.

A link at the target, or at a directory on the way to it, would put the text of a file outside
repo_root into the prompt or copy it into repo_root. Each read is contained; a refused read
reads nothing and is recorded. A regular target still reaches the prompt unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
)

TARGET = "toy/math_util.py"
ORIGINAL = "def add(a, b):\n    return a - b\n"
HOST = "HOST FILE - must not reach a prompt\n"
DIFF = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"
COMMITTEE = ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"]


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
    (host.parent / Path(TARGET).name).write_text(HOST)
    return repo, host


def _plant_link(repo: Path, host: Path) -> None:
    target = repo / TARGET
    target.unlink()
    target.symlink_to(host)


def _plant_parent_link(repo: Path, host: Path) -> None:
    toy = repo / Path(TARGET).parent
    for child in toy.iterdir():
        child.unlink()
    toy.rmdir()
    toy.symlink_to(host.parent, target_is_directory=True)


PLANTERS = {"link_at_target": _plant_link, "link_on_the_way": _plant_parent_link}


def _assert_no_host_text(value) -> None:
    dumped = json.dumps(value, default=str)
    assert HOST.strip() not in dumped
    assert hashlib.sha256(HOST.encode()).hexdigest() not in dumped


def _pipeline_request(repo: Path, task_id: str, candidate_models: list[str]):
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


def _pipeline_result():
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


def _run_pipeline(req, *, pipeline_execute, verifier, committee_run):
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
            side_effect=verifier,
        ),
        patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None),
        patch("nexus.services.local_heal.pipeline.HealPipeline.run", side_effect=committee_run),
    ):
        return LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: DIFF))


def _localized_contents(heal_ctx) -> list[str]:
    return [str(getattr(f, "content", "")) for f in (heal_ctx.localized_files or [])]


# --- committee pre-fill of localized_files -------------------------------------------------


@pytest.mark.parametrize("plant", sorted(PLANTERS))
def test_committee_prompt_files_never_hold_text_read_through_a_link(repo_and_host, plant):
    # The pipeline restore leaves the original in place; the link appears afterwards (model
    # code from the verifier run), right before the committee pre-fills localized_files.
    repo, host = repo_and_host
    calls = []

    def verifier(req):
        if not (repo / Path(TARGET).parent).is_symlink() and not (repo / TARGET).is_symlink():
            PLANTERS[plant](repo, host)
        return _verifier_fail(req)

    def committee_run(heal_ctx):
        calls.append(_localized_contents(heal_ctx))
        return _committee_run_result(heal_ctx)

    resp = _run_pipeline(
        _pipeline_request(repo, f"prompt-3023-committee-{plant}", COMMITTEE),
        pipeline_execute=lambda *_a, **_kw: _pipeline_result(),
        verifier=verifier,
        committee_run=committee_run,
    )
    # Each committee candidate runs on a World C copy of repo_root, and the copy refuses
    # a target behind a link, so no candidate runs (like the single retry below).
    for contents in calls:
        _assert_no_host_text(contents)
    assert calls == []
    meta = resp.raw_model_metadata
    assert meta["delegated_retry_target_read_refused"] is True
    assert meta["delegated_retry_target_read_refused_reason"]


def test_committee_prompt_files_still_hold_a_regular_target(repo_and_host):
    repo, _host = repo_and_host
    calls = []

    def committee_run(heal_ctx):
        calls.append(_localized_contents(heal_ctx))
        return _committee_run_result(heal_ctx)

    resp = _run_pipeline(
        _pipeline_request(repo, "prompt-3023-committee-control", COMMITTEE),
        pipeline_execute=lambda *_a, **_kw: _pipeline_result(),
        verifier=_verifier_fail,
        committee_run=committee_run,
    )
    assert calls and calls[0] == [ORIGINAL]
    assert "delegated_retry_target_read_refused" not in resp.raw_model_metadata


# --- the original snapshot before the pipeline run -----------------------------------------


def _replace_with_regular_target(repo: Path) -> None:
    """Model code removes the planted link and leaves a regular target behind."""
    toy = repo / Path(TARGET).parent
    if toy.is_symlink():
        toy.unlink()
        toy.mkdir()
    target = repo / TARGET
    if target.is_symlink():
        target.unlink()
    target.write_text("model wrote this\n")


@pytest.mark.parametrize("plant", sorted(PLANTERS))
def test_original_snapshot_is_not_read_through_a_link(repo_and_host, plant):
    # A link already sits at the target when the pipeline starts. Its text must not become the
    # "original" that is written back into repo_root after the run.
    repo, host = repo_and_host
    PLANTERS[plant](repo, host)
    applied = []

    def apply(req):
        applied.append(req)
        return _apply_receipt(req)

    def pipeline_execute(*_a, **_kw):
        _replace_with_regular_target(repo)
        return _pipeline_result()

    with patch(
        "nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply",
        side_effect=apply,
    ):
        resp = _run_pipeline(
            _pipeline_request(repo, f"prompt-3023-original-{plant}", []),
            pipeline_execute=pipeline_execute,
            verifier=_verifier_fail,
            committee_run=_committee_run_result,
        )
    assert (repo / TARGET).read_text() == "model wrote this\n"
    assert host.read_text() == HOST
    meta = resp.raw_model_metadata
    assert meta["original_target_read_refused"]
    assert meta["isolated_apply_status"] == "restore_refused"
    assert meta["isolated_apply_error"].startswith("TARGET_READ_REFUSED:")
    assert meta["isolated_verifier_status"] == "not_run"
    assert applied == []
    _assert_no_host_text(meta)


def test_original_snapshot_of_a_regular_target_is_still_restored(repo_and_host):
    repo, _host = repo_and_host

    def pipeline_execute(*_a, **_kw):
        (repo / TARGET).write_text("model wrote this\n")
        return _pipeline_result()

    resp = _run_pipeline(
        _pipeline_request(repo, "prompt-3023-original-control", []),
        pipeline_execute=pipeline_execute,
        verifier=_verifier_fail,
        committee_run=_committee_run_result,
    )
    assert (repo / TARGET).read_text() == ORIGINAL
    meta = resp.raw_model_metadata
    assert not meta.get("original_target_read_refused")
    assert meta["isolated_apply_status"] == "applied"


def test_original_snapshot_of_a_non_utf8_target_is_not_rewritten(repo_and_host):
    # The contained read decodes with replacement characters; writing that text back would change
    # the target's bytes, so the run takes the refused-restore path and the bytes stay as found.
    repo, _host = repo_and_host
    original = b"# caf\xe9\ndef double(x):\n    return x * 2\n"
    (repo / TARGET).write_bytes(original)
    applied = []

    def apply(req):
        applied.append(req)
        return _apply_receipt(req)

    def pipeline_execute(*_a, **_kw):
        (repo / TARGET).write_bytes(original)  # model code ran; the target is as it was
        return _pipeline_result()

    with patch(
        "nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply",
        side_effect=apply,
    ):
        resp = _run_pipeline(
            _pipeline_request(repo, "prompt-3023-original-not-utf8", []),
            pipeline_execute=pipeline_execute,
            verifier=_verifier_fail,
            committee_run=_committee_run_result,
        )
    assert (repo / TARGET).read_bytes() == original
    meta = resp.raw_model_metadata
    assert meta["original_target_read_refused"] == f"target_not_utf8:{TARGET}"
    assert meta["isolated_apply_status"] == "restore_refused"
    assert meta["isolated_verifier_status"] == "not_run"
    assert applied == []


# --- source_context in the single-model unified-diff prompt --------------------------------


def _single_request(repo: Path, task_id: str) -> LocalModelExecutorRequest:
    return LocalModelExecutorRequest(
        task_id=task_id,
        problem_statement="fix add",
        repo_root=str(repo),
        target_file=TARGET,
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
        route_context={
            "locked_search": "def add(a, b):",
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "unified_diff",
            },
        },
    )


def _run_single(req, monkeypatch) -> tuple[str, dict]:
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "unified_diff")
    prompts: list[str] = []

    def gen(preq: LocalModelProviderRequest) -> str:
        prompts.append(preq.prompt)
        return "diff patch"

    resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(gen))
    assert len(prompts) == 1
    return prompts[0], resp.raw_model_metadata


@pytest.mark.parametrize("plant", sorted(PLANTERS))
def test_source_context_is_not_read_through_a_link(repo_and_host, monkeypatch, plant):
    repo, host = repo_and_host
    PLANTERS[plant](repo, host)
    prompt, meta = _run_single(_single_request(repo, f"prompt-3023-source-{plant}"), monkeypatch)
    assert HOST.strip() not in prompt
    assert "Relevant source lines" not in prompt
    assert meta["source_context_read_refused"]
    _assert_no_host_text(meta)


def test_source_context_still_shows_a_regular_target(repo_and_host, monkeypatch):
    repo, _host = repo_and_host
    prompt, meta = _run_single(_single_request(repo, "prompt-3023-source-control"), monkeypatch)
    assert "Relevant source lines" in prompt
    assert "1: def add(a, b):" in prompt
    assert "2:     return a - b" in prompt
    assert "source_context_read_refused" not in meta


# --- single-model delegated retry ----------------------------------------------------------


def _hard_link(repo: Path, host: Path) -> None:
    target = repo / TARGET
    target.unlink()
    os.link(host, target)


SINGLE_PLANTERS = {**PLANTERS, "hard_link": _hard_link}


def _workspace_target_text(heal_ctx) -> str:
    try:
        return (Path(heal_ctx.repo_dir) / TARGET).read_text()
    except OSError:
        return ""


@pytest.mark.parametrize("plant", sorted(SINGLE_PLANTERS))
def test_single_retry_does_not_run_on_a_target_behind_a_link(repo_and_host, plant):
    # The retry workspace is a copy of repo_root; copying follows a link, so a refused
    # target read must stop the single retry before any workspace or prompt is built.
    repo, host = repo_and_host
    seen = []

    def verifier(req):
        if (repo / TARGET).read_text() == ORIGINAL and not (repo / TARGET).is_symlink():
            SINGLE_PLANTERS[plant](repo, host)
        return _verifier_fail(req)

    def single_run(heal_ctx):
        seen.append((_localized_contents(heal_ctx), _workspace_target_text(heal_ctx)))
        return _committee_run_result(heal_ctx)

    resp = _run_pipeline(
        _pipeline_request(repo, f"prompt-3023-single-{plant}", []),
        pipeline_execute=lambda *_a, **_kw: _pipeline_result(),
        verifier=verifier,
        committee_run=single_run,
    )
    _assert_no_host_text(seen)
    assert seen == []
    meta = resp.raw_model_metadata
    assert meta["delegated_retry_target_read_refused"] is True
    assert meta["delegated_retry_failure_reason"] == "delegated_retry_target_read_refused"


def test_single_retry_still_runs_on_a_regular_target(repo_and_host):
    repo, _host = repo_and_host
    seen = []

    def single_run(heal_ctx):
        seen.append((_localized_contents(heal_ctx), _workspace_target_text(heal_ctx)))
        return _committee_run_result(heal_ctx)

    resp = _run_pipeline(
        _pipeline_request(repo, "prompt-3023-single-control", []),
        pipeline_execute=lambda *_a, **_kw: _pipeline_result(),
        verifier=_verifier_fail,
        committee_run=single_run,
    )
    assert seen == [([ORIGINAL], ORIGINAL)]
    assert "delegated_retry_target_read_refused" not in resp.raw_model_metadata
