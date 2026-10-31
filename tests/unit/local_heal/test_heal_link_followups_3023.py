"""#3023 follow-ups: the remaining reads and checks of a target file in local_heal do not follow
a link that model code may have left at the target or on the way to it.

- The re-anchor step and the diff builder read the target when there is no original text (a
  new target): through a link they would take line positions from a file outside repo_root.
- After the pipeline run, a new target whose directory became a link is refused, also when
  the linked directory does not hold the file.
- After a committee candidate, a target whose directory became a link is refused, recorded
  and stops the loop, also when the linked directory does not hold the file; so is a dangling
  link at the target.
- The committee routed tool's verify step does not read the target through a link.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    _verify_applied_candidate,
)
from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    _build_unified_diff_from_search_and_replacement,
    _reanchor_pipeline_patch_to_locked_search,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate

TARGET = "toy/math_util.py"
ORIGINAL = "def add(a, b):\n    return a - b\n"
HOST = "HOST FILE - must not change\n"
DIFF = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"
# A host file whose 6th line starts the anchor text: a read through a link would put "-6," in
# the hunk header.
HOST_WITH_ANCHOR = "".join(f"# host line {i}\n" for i in range(1, 6)) + ORIGINAL
LOCKED = ORIGINAL
FIXED = "def add(a, b):\n    return a + b\n"
PROJECTED = (
    "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1,2 +1,2 @@\n"
    "-def add(a,b):\n-    return a-b\n+def add(a, b):\n+    return a + b\n"
)


@pytest.fixture(autouse=True)
def _world_c_copies_of_tmp_repos(monkeypatch):
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")


@pytest.fixture
def repo_and_host(tmp_path):
    repo = tmp_path / "repo"
    (repo / "toy").mkdir(parents=True)
    (repo / TARGET).write_text(ORIGINAL)
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    return repo, host_dir


def _link_target_to(repo: Path, host_file: Path) -> None:
    target = repo / TARGET
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(host_file)


def _link_parent_to(repo: Path, host_dir: Path) -> None:
    """The target's directory becomes a link to a host dir (which may not hold the file)."""
    toy = repo / Path(TARGET).parent
    for child in toy.iterdir():
        child.unlink()
    toy.rmdir()
    toy.symlink_to(host_dir, target_is_directory=True)


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


def _unit_request(repo: Path) -> LocalModelExecutorRequest:
    return LocalModelExecutorRequest(
        task_id="link-followups-3023",
        problem_statement="test",
        repo_root=str(repo),
        target_file=TARGET,
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
    )


# --- (e)/(i): reads of a new target -------------------------------------------------------


@pytest.mark.parametrize("planted", ["target_link", "parent_link"])
def test_reanchor_of_a_new_target_does_not_read_through_a_link(repo_and_host, planted):
    repo, host_dir = repo_and_host
    host_file = host_dir / Path(TARGET).name
    host_file.write_text(HOST_WITH_ANCHOR)
    if planted == "target_link":
        _link_target_to(repo, host_file)
    else:
        _link_parent_to(repo, host_dir)

    patch_text, meta = _reanchor_pipeline_patch_to_locked_search(
        _unit_request(repo), LOCKED, PROJECTED, original_source_text=None
    )
    assert meta == {"pipeline_locked_search_reanchored": False}
    assert patch_text == PROJECTED
    assert host_file.read_text() == HOST_WITH_ANCHOR


def test_reanchor_of_a_new_target_still_reads_a_plain_file(repo_and_host):
    repo, _host_dir = repo_and_host
    (repo / TARGET).write_text(HOST_WITH_ANCHOR)

    patch_text, meta = _reanchor_pipeline_patch_to_locked_search(
        _unit_request(repo), LOCKED, PROJECTED, original_source_text=None
    )
    assert meta["pipeline_locked_search_reanchored"] is True
    assert "@@ -6,2 +6,2 @@" in patch_text


@pytest.mark.parametrize("planted", ["target_link", "parent_link"])
def test_diff_builder_does_not_take_line_positions_through_a_link(repo_and_host, planted):
    repo, host_dir = repo_and_host
    host_file = host_dir / Path(TARGET).name
    host_file.write_text(HOST_WITH_ANCHOR)
    if planted == "target_link":
        _link_target_to(repo, host_file)
    else:
        _link_parent_to(repo, host_dir)

    diff = _build_unified_diff_from_search_and_replacement(
        _unit_request(repo), TARGET, LOCKED, FIXED
    )
    assert "@@ -1,2 +1,2 @@" in diff
    assert "-6," not in diff


def test_diff_builder_still_anchors_on_a_plain_file(repo_and_host):
    repo, _host_dir = repo_and_host
    (repo / TARGET).write_text(HOST_WITH_ANCHOR)

    diff = _build_unified_diff_from_search_and_replacement(
        _unit_request(repo), TARGET, LOCKED, FIXED
    )
    assert "@@ -6,2 +6,2 @@" in diff


# --- (h): new target behind a directory link without the file -----------------------------


def test_a_new_target_behind_a_directory_link_without_the_file_is_refused(repo_and_host):
    repo, host_dir = repo_and_host
    (repo / TARGET).unlink()

    def pipeline_execute(*_a, **_kw):
        _link_parent_to(repo, host_dir)
        return _pipeline_result()

    resp = _run(
        _request(repo, "link-followups-3023-h", []),
        pipeline_execute=pipeline_execute,
        committee_run=_committee_run_result,
    )
    meta = resp.raw_model_metadata
    assert meta["isolated_apply_status"] == "restore_refused"
    assert meta["isolated_apply_error"].startswith("TARGET_RESTORE_REFUSED:")
    assert meta["isolated_verifier_status"] == "not_run"
    assert list(host_dir.iterdir()) == []


# --- (g)/(j): committee restore -------------------------------------------------------------


def test_committee_restore_behind_a_directory_link_without_the_file_is_refused(repo_and_host):
    repo, host_dir = repo_and_host
    calls = []

    def committee_run(heal_ctx):
        calls.append(heal_ctx)
        if not (repo / Path(TARGET).parent).is_symlink():
            _link_parent_to(repo, host_dir)
        return _committee_run_result(heal_ctx)

    resp = _run(
        _request(
            repo,
            "link-followups-3023-g",
            ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
        ),
        pipeline_execute=lambda *_a, **_kw: _pipeline_result(),
        committee_run=committee_run,
    )
    meta = resp.raw_model_metadata
    assert meta["delegated_retry_committee_restore_refused"] is True
    assert meta["delegated_retry_committee_restore_refused_reason"].startswith(
        "link-followups-3023-g#delegated-retry-01-"
    )
    assert len(calls) == 1
    assert list(host_dir.iterdir()) == []


def test_committee_restore_stops_at_a_dangling_link(repo_and_host):
    repo, host_dir = repo_and_host
    missing_host_file = host_dir / "not_there.py"
    calls = []

    def committee_run(heal_ctx):
        calls.append(heal_ctx)
        if not (repo / TARGET).is_symlink():
            _link_target_to(repo, missing_host_file)
        return _committee_run_result(heal_ctx)

    resp = _run(
        _request(
            repo,
            "link-followups-3023-j",
            ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
        ),
        pipeline_execute=lambda *_a, **_kw: _pipeline_result(),
        committee_run=committee_run,
    )
    meta = resp.raw_model_metadata
    assert meta["delegated_retry_committee_restore_refused"] is True
    assert len(calls) == 1
    assert not missing_host_file.exists()
    assert list(host_dir.iterdir()) == []
    _assert_no_host_text_recorded(meta)


# --- (k): committee routed tool verify step ----------------------------------------------


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


def _verify(repo: Path, target_file: str = TARGET) -> dict:
    return _verify_applied_candidate(
        _candidate("x = 1\n"),
        CommitteeRoutedToolRequest(
            task_id="t", repo_root=str(repo), target_file=target_file, verifier_allowed=True
        ),
    )


@pytest.mark.parametrize("planted", ["target_link", "parent_link"])
def test_committee_routed_verify_does_not_read_through_a_link(repo_and_host, planted):
    repo, host_dir = repo_and_host
    host_file = host_dir / Path(TARGET).name
    host_file.write_text("x = 1\n")
    if planted == "target_link":
        _link_target_to(repo, host_file)
    else:
        _link_parent_to(repo, host_dir)

    result = _verify(repo)
    assert result["status"] == "fail"
    assert "x = 1" not in result["reason"]


def test_committee_routed_verify_still_checks_a_plain_file(repo_and_host):
    repo, _host_dir = repo_and_host
    assert _verify(repo) == {"status": "pass", "reason": "basic_checks_passed"}
    (repo / TARGET).write_text("def broken(:\n")
    assert _verify(repo)["status"] == "fail"
    assert _verify(repo, "toy/missing.py") == {"status": "fail", "reason": "file_not_found"}


def test_committee_routed_verify_fails_a_target_that_is_not_utf8(repo_and_host):
    repo, _host_dir = repo_and_host
    # The bad bytes sit mid-file, so a check that only looks at the end would miss them.
    (repo / TARGET).write_bytes(
        b"x = 1\n# \xff\xfe\n" + b"".join(b"y%d = %d\n" % (i, i) for i in range(20))
    )
    result = _verify(repo)
    assert result["status"] == "fail"
    assert result["reason"].startswith("TARGET_NOT_UTF8:")


# --- link loops: Python 3.11/3.12 raise RuntimeError from Path.resolve, 3.13+ do not -------


@pytest.mark.parametrize("planted", ["target_loop", "parent_loop"])
def test_existence_helper_refuses_a_link_loop(repo_and_host, planted):
    from nexus.core.contained_write import PathContainmentError
    from nexus.services.local_heal.local_model_executor import _target_entry_exists

    repo, _host_dir = repo_and_host
    if planted == "target_loop":
        (repo / TARGET).unlink()
        (repo / TARGET).symlink_to(repo / TARGET)
    else:
        toy = repo / Path(TARGET).parent
        for child in toy.iterdir():
            child.unlink()
        toy.rmdir()
        toy.symlink_to(toy, target_is_directory=True)
    with pytest.raises(PathContainmentError):
        _target_entry_exists(str(repo), TARGET)


@pytest.mark.parametrize(
    ("target_file", "expected"),
    [
        (TARGET, True),
        ("toy/missing.py", False),
        ("missing_dir/x.py", False),
        (TARGET + "/x", False),
    ],
)
def test_existence_helper_answers_plain_paths_without_links(repo_and_host, target_file, expected):
    from nexus.services.local_heal.local_model_executor import _target_entry_exists

    repo, _host_dir = repo_and_host
    assert _target_entry_exists(str(repo), target_file) is expected


def test_existence_helper_refuses_a_path_it_cannot_inspect(repo_and_host, monkeypatch):
    # Any lstat error other than "missing" (here: no permission) is a refusal, not "nothing
    # there". Simulated so the test also holds when the suite runs as root.
    import os

    from nexus.core.contained_write import PathContainmentError
    from nexus.services.local_heal.local_model_executor import _target_entry_exists

    repo, _host_dir = repo_and_host
    blocked = os.path.join(str(repo), TARGET)
    real_lstat = os.lstat

    def lstat(path, *args, **kwargs):
        if os.fspath(path) == blocked:
            raise PermissionError(13, "Permission denied", blocked)
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)
    with pytest.raises(PathContainmentError, match="path_unresolvable"):
        _target_entry_exists(str(repo), TARGET)


def test_committee_restore_stops_at_a_link_loop(repo_and_host):
    repo, _host_dir = repo_and_host
    calls = []

    def committee_run(heal_ctx):
        calls.append(heal_ctx)
        if not (repo / TARGET).is_symlink():
            (repo / TARGET).unlink()
            (repo / TARGET).symlink_to(repo / TARGET)
        return _committee_run_result(heal_ctx)

    resp = _run(
        _request(
            repo,
            "link-followups-3023-loop",
            ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
        ),
        pipeline_execute=lambda *_a, **_kw: _pipeline_result(),
        committee_run=committee_run,
    )
    assert resp.raw_model_metadata["delegated_retry_committee_restore_refused"] is True
    assert len(calls) == 1


def test_a_new_target_that_became_a_link_loop_is_refused_not_raised(repo_and_host):
    repo, _host_dir = repo_and_host
    (repo / TARGET).unlink()

    def pipeline_execute(*_a, **_kw):
        (repo / TARGET).symlink_to(repo / TARGET)
        return _pipeline_result()

    resp = _run(
        _request(repo, "link-followups-3023-loop-new", []),
        pipeline_execute=pipeline_execute,
        committee_run=_committee_run_result,
    )
    assert resp.raw_model_metadata["isolated_apply_status"] == "restore_refused"
