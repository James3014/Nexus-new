"""#3018: local_heal's host-side reads of repo_dir do not follow a link left there.

Sandboxed model code may have run in repo_dir before localization, patch synthesis, the repo map,
the orchestrator and the micro verifier read it. A symlink or hard link there to a host file, a
FIFO or a very large file must not be read by the host (its text would reach a model prompt, or
the read would block or run unbounded). Each reader gets a test with a link to an outside file;
controls check that plain files and links inside repo_dir still read.

Also #3037 R6-2: when the committee restore is refused, a winner chosen from an earlier candidate
is not handed on as a verified patch.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nexus.core.contained_write import PathContainmentError, read_text_in_root
from nexus.services.local_heal.context import GovernanceContext, HealContext, OperationalContext
from nexus.services.local_heal.context_budget import ContextBudgetManager
from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer
from nexus.services.local_heal.interface import LocalizationInput, LocalizedFile, RepairPlan
from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.local_heal.micro_verifier import MicroVerifier
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.phases.localization import LocalizationPhase
from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
from nexus.services.local_heal.repo_read import read_repo_text
from nexus.services.local_heal.repomap import RepoMap

HOST_MARKER = "HOST_SECRET_3018"
HOST_TEXT = f"def {HOST_MARKER.lower()}():\n    return '{HOST_MARKER}'\n"
PLAIN_TEXT = "def plain_helper():\n    return 1\n"
LINK_KINDS = ["symlink", "hardlink", "parent_symlink"]


@pytest.fixture
def repo_and_host(tmp_path):
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "plain.py").write_text(PLAIN_TEXT)
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    host_file = host_dir / "target.py"
    host_file.write_text(HOST_TEXT)
    return repo, host_dir, host_file


def _plant(repo: Path, host_dir: Path, host_file: Path, kind: str) -> str:
    """Leave a link at repo/<returned relative path> that reaches host_file."""
    if kind == "symlink":
        (repo / "pkg" / "target.py").symlink_to(host_file)
        return "pkg/target.py"
    if kind == "hardlink":
        os.link(host_file, repo / "pkg" / "target.py")
        return "pkg/target.py"
    (repo / "linked").symlink_to(host_dir, target_is_directory=True)
    return "linked/target.py"


def _host_seen(blob: object) -> bool:
    dumped = json.dumps(blob, default=str)
    return HOST_MARKER in dumped or hashlib.sha256(HOST_TEXT.encode()).hexdigest() in dumped


# --- shared helpers ---------------------------------------------------------------------


def test_read_text_in_root_refuses_a_file_over_max_bytes(tmp_path):
    (tmp_path / "big.py").write_text("x" * 101)
    (tmp_path / "ok.py").write_text("x" * 100)
    with pytest.raises(PathContainmentError, match="file_too_large"):
        read_text_in_root(tmp_path, "big.py", max_bytes=100)
    assert read_text_in_root(tmp_path, "ok.py", max_bytes=100) == "x" * 100
    assert read_text_in_root(tmp_path, "big.py") == "x" * 101


@pytest.mark.parametrize("kind", LINK_KINDS)
def test_read_repo_text_refuses_a_link_to_an_outside_file(repo_and_host, kind):
    repo, host_dir, host_file = repo_and_host
    relative = _plant(repo, host_dir, host_file, kind)
    assert read_repo_text(repo, relative) is None
    assert read_repo_text(repo, repo / relative) is None


def test_read_repo_text_refuses_paths_outside_repo_dir(repo_and_host):
    repo, _host_dir, host_file = repo_and_host
    assert read_repo_text(repo, host_file) is None
    assert read_repo_text(repo, "../host/target.py") is None


def test_read_repo_text_refuses_a_fifo_without_blocking(repo_and_host):
    repo, _host_dir, _host_file = repo_and_host
    os.mkfifo(repo / "pkg" / "pipe.py")
    assert read_repo_text(repo, "pkg/pipe.py") is None


def test_read_repo_text_refuses_an_oversized_file(repo_and_host):
    repo, _host_dir, _host_file = repo_and_host
    (repo / "pkg" / "big.py").write_text("y" * 64)
    assert read_repo_text(repo, "pkg/big.py", max_bytes=63) is None
    assert read_repo_text(repo, "pkg/big.py", max_bytes=64) == "y" * 64


def test_read_repo_text_reads_plain_files_and_links_inside_repo(repo_and_host):
    repo, _host_dir, _host_file = repo_and_host
    (repo / "pkg" / "alias.py").symlink_to("plain.py")
    assert read_repo_text(repo, "pkg/plain.py") == PLAIN_TEXT
    assert read_repo_text(repo, repo / "pkg" / "plain.py") == PLAIN_TEXT
    assert read_repo_text(repo, "pkg/alias.py") == PLAIN_TEXT
    assert read_repo_text(repo, "pkg/missing.py") is None


# --- localization ------------------------------------------------------------------------


def _localization_phase() -> LocalizationPhase:
    return LocalizationPhase(GranularMethodLocalizer(), ContextBudgetManager())


@pytest.mark.parametrize("kind", ["hardlink"])
def test_canonical_localization_does_not_read_a_hard_linked_target(repo_and_host, kind):
    repo, host_dir, host_file = repo_and_host
    relative = _plant(repo, host_dir, host_file, kind)
    out = _localization_phase()._run_canonical_target(
        target_file=relative,
        input_data=LocalizationInput(
            problem_statement="fix it", repro_evidence="", repo_dir=repo, plan=None
        ),
    )
    assert out.success is False
    assert out.error_reason == "LOCALIZATION_TARGET_READ_FAILED"
    assert not _host_seen([f.content for f in out.localized_files])


def test_canonical_localization_still_reads_a_plain_target(repo_and_host):
    repo, _host_dir, _host_file = repo_and_host
    out = _localization_phase()._run_canonical_target(
        target_file="pkg/plain.py",
        input_data=LocalizationInput(
            problem_statement="fix plain_helper", repro_evidence="", repo_dir=repo, plan=None
        ),
    )
    assert out.success is True
    assert "plain_helper" in out.localized_files[0].content


@pytest.mark.parametrize("kind", LINK_KINDS)
def test_ranked_localization_skips_a_link_to_an_outside_file(repo_and_host, kind):
    repo, host_dir, host_file = repo_and_host
    _plant(repo, host_dir, host_file, kind)
    ranked = GranularMethodLocalizer().rank_files(f"{HOST_MARKER} plain_helper", repo)
    assert not _host_seen([doc["content"] for _score, doc in ranked])
    assert any(doc["path"] == "pkg/plain.py" for _score, doc in ranked)


def test_issue_text_naming_an_outside_path_is_not_read(repo_and_host):
    repo, _host_dir, host_file = repo_and_host
    issue = f'Traceback:\n  File "{host_file}", line 1\nplain_helper is wrong'
    ranked = GranularMethodLocalizer().rank_files(issue, repo)
    assert not _host_seen([doc["content"] for _score, doc in ranked])


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_issue_text_naming_a_linked_repo_path_is_not_read(repo_and_host, kind):
    repo, host_dir, host_file = repo_and_host
    relative = _plant(repo, host_dir, host_file, kind)
    ranked = GranularMethodLocalizer().rank_files(f"see `{relative}`", repo)
    assert not _host_seen([doc["content"] for _score, doc in ranked])


# --- repo map ----------------------------------------------------------------------------


@pytest.mark.parametrize("kind", LINK_KINDS)
def test_repomap_does_not_index_a_link_to_an_outside_file(repo_and_host, kind):
    repo, host_dir, host_file = repo_and_host
    _plant(repo, host_dir, host_file, kind)
    repo_map = RepoMap(repo)
    repo_map.build_index()
    assert not _host_seen(repo_map._file_index)
    assert HOST_MARKER.lower() not in repo_map._symbol_index
    assert repo_map._file_index["pkg/plain.py"] == PLAIN_TEXT


# --- patch synthesis ---------------------------------------------------------------------


def _synthesis_ctx(repo: Path, localized: list[LocalizedFile]) -> HealContext:
    return HealContext(
        op=OperationalContext(
            instance_id="reads-3018",
            repo_dir=repo,
            problem_statement="fix target",
            repro_evidence="AssertionError",
            localized_files=localized,
            plan=RepairPlan(search_symbols=["target"], repair_strategy="fix"),
            max_tries=1,
        ),
        gov=GovernanceContext(),
    )


@pytest.mark.parametrize("kind", ["hardlink", "parent_symlink"])
def test_patch_synthesis_prompt_does_not_carry_a_linked_target(repo_and_host, kind):
    repo, host_dir, host_file = repo_and_host
    relative = _plant(repo, host_dir, host_file, kind)
    prompts: list[str] = []

    def model_client(system_prompt, user_prompt, model=None, timeout=None):
        prompts.append(f"{system_prompt}\n{user_prompt}")
        return "no patch"

    ctx = _synthesis_ctx(repo, [LocalizedFile(path=relative, content="LOCALIZED_ONLY = 1\n")])
    PatchSynthesisPhase(
        parser=SolidSearchReplaceProtocol(), patcher=Patcher(), model_client=model_client
    ).execute(ctx)
    assert prompts
    assert not _host_seen(prompts)
    assert any("LOCALIZED_ONLY" in p for p in prompts)
    assert host_file.read_text() == HOST_TEXT


def test_patch_synthesis_still_reads_a_plain_target_from_disk(repo_and_host):
    repo, _host_dir, _host_file = repo_and_host
    prompts: list[str] = []

    def model_client(system_prompt, user_prompt, model=None, timeout=None):
        prompts.append(f"{system_prompt}\n{user_prompt}")
        return "no patch"

    ctx = _synthesis_ctx(repo, [LocalizedFile(path="pkg/plain.py", content="STALE = 1\n")])
    PatchSynthesisPhase(
        parser=SolidSearchReplaceProtocol(), patcher=Patcher(), model_client=model_client
    ).execute(ctx)
    assert any("plain_helper" in p for p in prompts)


def test_unified_diff_header_naming_an_outside_file_is_not_read(repo_and_host):
    repo, _host_dir, host_file = repo_and_host
    diff = (
        f"--- {host_file}\n+++ {host_file}\n@@ -1,2 +1,2 @@\n"
        f" def {HOST_MARKER.lower()}():\n-    return '{HOST_MARKER}'\n+    return 'x'\n"
    )

    def model_client(system_prompt, user_prompt, model=None, timeout=None):
        return diff

    ctx = _synthesis_ctx(repo, [])
    PatchSynthesisPhase(
        parser=SolidSearchReplaceProtocol(), patcher=Patcher(), model_client=model_client
    ).execute(ctx)
    decisions = [d for d in ctx.op.model_decisions if d.get("phase") == "patch"]
    assert decisions
    assert decisions[-1]["conversion_status"] == "unified_diff_target_mismatch"
    assert decisions[-1]["conversion_source_hash_before"] == ""
    assert host_file.read_text() == HOST_TEXT


# --- orchestrator ------------------------------------------------------------------------


def _orch_ctx(repo: Path, localized: list[LocalizedFile] | None = None):
    return SimpleNamespace(
        op=SimpleNamespace(repo_dir=repo, plan=None, localized_files=localized or [])
    )


@pytest.mark.parametrize("kind", LINK_KINDS + ["absolute", "dotdot"])
def test_fuzzy_healing_does_not_read_a_linked_or_outside_file(repo_and_host, kind):
    repo, host_dir, host_file = repo_and_host
    if kind == "absolute":
        f_path = str(host_file)
    elif kind == "dotdot":
        f_path = "../host/target.py"
    else:
        f_path = _plant(repo, host_dir, host_file, kind)
    err = SimpleNamespace(closest_match=None)
    res = SimpleNamespace(
        error_metadata={"failed_search_text": f"return '{HOST_MARKER}'", "file_path": f_path}
    )
    HealOrchestrator._attempt_fuzzy_healing(None, _orch_ctx(repo), res, err)  # type: ignore[arg-type]
    assert not _host_seen(err.closest_match or "")


def test_fuzzy_healing_still_reads_a_plain_file(repo_and_host):
    repo, _host_dir, _host_file = repo_and_host
    err = SimpleNamespace(closest_match=None)
    res = SimpleNamespace(
        error_metadata={"failed_search_text": "return 1", "file_path": "pkg/plain.py"}
    )
    HealOrchestrator._attempt_fuzzy_healing(None, _orch_ctx(repo), res, err)  # type: ignore[arg-type]
    assert err.closest_match and "return 1" in err.closest_match


@pytest.mark.parametrize("kind", LINK_KINDS)
def test_resolve_target_file_skips_a_link_to_an_outside_file(repo_and_host, kind):
    repo, host_dir, host_file = repo_and_host
    relative = _plant(repo, host_dir, host_file, kind)
    ctx = _orch_ctx(repo, [LocalizedFile(path=relative, content="")])
    assert HealOrchestrator._resolve_target_file(None, ctx) is None  # type: ignore[arg-type]
    ctx = _orch_ctx(
        repo,
        [LocalizedFile(path=relative, content=""), LocalizedFile(path="pkg/plain.py", content="")],
    )
    assert HealOrchestrator._resolve_target_file(None, ctx) == repo / "pkg" / "plain.py"  # type: ignore[arg-type]


class _StopRetry(Exception):
    pass


def _semantic_retry_orch(monkeypatch, tmp_path, *, response: str, spy_span=None):
    """A HealOrchestrator whose semantic retry runs for real up to the diff conversion."""
    import nexus.services.local_heal.canonical_span as canonical_span_mod
    from nexus.services.local_heal.diff_to_ssrp import DiffToSSRPConverter
    from nexus.services.local_heal.prompt_builder import PromptBuilder

    monkeypatch.delenv("NEXUS_PROTOCOL_MODE", raising=False)  # restored after the test
    monkeypatch.setattr(
        canonical_span_mod,
        "get_canonical_search_span",
        spy_span or (lambda **_kw: SimpleNamespace(span="x = 1", source="test")),
    )
    prompts: list[str] = []
    converted: list[dict] = []

    def _build_prompt(**kwargs):
        prompts.append(json.dumps(kwargs, default=str))
        return "RETRY PROMPT"

    def _convert(**kwargs):
        converted.append(kwargs)
        raise _StopRetry

    monkeypatch.setattr(
        PromptBuilder, "build_verification_guided_retry_prompt", staticmethod(_build_prompt)
    )
    monkeypatch.setattr(DiffToSSRPConverter, "convert", staticmethod(_convert))

    class _Client:
        def generate(self, **kwargs):
            prompts.append(json.dumps(kwargs, default=str))
            return response

    orch = object.__new__(HealOrchestrator)
    orch.patch_phase = SimpleNamespace(llm_client=_Client())
    orch._extract_target_symbol = lambda ctx: ""  # type: ignore[method-assign]
    orch._render_memory_lessons = lambda ctx, target: ("", [])  # type: ignore[method-assign]
    orch._extract_codeintel_context_for_retry = lambda ctx: ""  # type: ignore[method-assign]
    orch._learning_closure_path = lambda: tmp_path / "no-closure.jsonl"  # type: ignore[method-assign]
    return orch, prompts, converted


def _semantic_retry_ctx(repo: Path, final_patch: str, localized=None):
    return SimpleNamespace(
        op=SimpleNamespace(
            repo_dir=repo,
            final_patch=final_patch,
            user_prompt="fix target",
            problem_statement="fix target",
            attempt=2,
            model_decisions=[],
            localized_files=localized or [],
            plan=None,
        )
    )


def _run_semantic_retry(orch, ctx) -> None:
    try:
        orch._attempt_semantic_retry(ctx, "verifier failed", "verification_failed")
    except _StopRetry:
        pass


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "parent_symlink", "dotdot"])
def test_semantic_retry_diff_target_is_not_read_through_a_link(
    repo_and_host, monkeypatch, tmp_path, kind
):
    repo, host_dir, host_file = repo_and_host
    if kind == "dotdot":
        relative = "../host/target.py"
    else:
        relative = _plant(repo, host_dir, host_file, kind)
    header = f"--- a/{relative}\n+++ b/{relative}\n"
    response = header + "@@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    orch, prompts, converted = _semantic_retry_orch(monkeypatch, tmp_path, response=response)
    ctx = _semantic_retry_ctx(repo, header + "@@ -1 +1 @@\n-a\n+b\n")
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol

    assert SolidSearchReplaceProtocol().classify_format(response) == "UNIFIED_DIFF"
    _run_semantic_retry(orch, ctx)

    assert prompts  # the retry reached the model call
    assert not _host_seen(prompts)
    assert not _host_seen([c.get("source_text", "") for c in converted])
    assert host_file.read_text() == HOST_TEXT


def test_semantic_retry_diff_target_still_reads_a_plain_file(repo_and_host, monkeypatch, tmp_path):
    repo, _host_dir, _host_file = repo_and_host
    header = "--- a/pkg/plain.py\n+++ b/pkg/plain.py\n"
    response = header + "@@ -1,2 +1,2 @@\n def plain_helper():\n-    return 1\n+    return 2\n"
    orch, _prompts, converted = _semantic_retry_orch(monkeypatch, tmp_path, response=response)
    _run_semantic_retry(orch, _semantic_retry_ctx(repo, header + "@@ -1 +1 @@\n-a\n+b\n"))
    assert converted and converted[0]["source_text"] == PLAIN_TEXT


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "parent_symlink"])
def test_semantic_retry_canonical_span_source_is_not_read_through_a_link(
    repo_and_host, monkeypatch, tmp_path, kind
):
    """A link swapped in after _resolve_target_file checked the entry is not read either."""
    repo, host_dir, host_file = repo_and_host
    relative = _plant(repo, host_dir, host_file, kind)
    seen: list[dict] = []

    def _spy_span(**kwargs):
        seen.append(kwargs)
        source_file = kwargs.get("source_file")
        text = kwargs.get("source_text")
        if text is None and source_file is not None:
            text = Path(source_file).read_text()  # what the real span would read by path
        return SimpleNamespace(span=text or "x = 1", source="test")

    orch, prompts, _converted = _semantic_retry_orch(
        monkeypatch, tmp_path, response="no diff", spy_span=_spy_span
    )
    orch._resolve_target_file = lambda ctx: repo / relative  # type: ignore[method-assign]
    _run_semantic_retry(
        orch,
        _semantic_retry_ctx(repo, f"--- a/{relative}\n+++ b/{relative}\n@@ -1 +1 @@\n-a\n+b\n"),
    )

    assert seen
    assert seen[0]["source_file"] is None
    assert not _host_seen(seen[0].get("source_text") or "")
    assert not _host_seen(prompts)


def test_semantic_retry_canonical_span_still_gets_a_plain_source(
    repo_and_host, monkeypatch, tmp_path
):
    repo, _host_dir, _host_file = repo_and_host
    seen: list[dict] = []

    def _spy_span(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(span="x = 1", source="test")

    orch, _prompts, _converted = _semantic_retry_orch(
        monkeypatch, tmp_path, response="no diff", spy_span=_spy_span
    )
    ctx = _semantic_retry_ctx(
        repo,
        "--- a/pkg/plain.py\n+++ b/pkg/plain.py\n@@ -1 +1 @@\n-a\n+b\n",
        localized=[LocalizedFile(path="pkg/plain.py", content="")],
    )
    _run_semantic_retry(orch, ctx)
    assert seen[0]["source_file"] == repo / "pkg" / "plain.py"
    assert seen[0]["source_text"] == PLAIN_TEXT


# --- micro verifier ----------------------------------------------------------------------


@pytest.mark.parametrize("kind", LINK_KINDS)
def test_micro_verifier_does_not_parse_a_linked_patched_file(repo_and_host, kind):
    repo, host_dir, host_file = repo_and_host
    host_file.write_text(f"{HOST_MARKER} = (\n")  # a syntax error that would quote the file
    relative = _plant(repo, host_dir, host_file, kind)
    result = MicroVerifier.verify(
        "",
        repo,
        [relative],
        verifier_env_metadata={"allow_bare_python": True, "interpreter": "python3"},
    )
    assert result.passed is False
    assert result.syntax_ok is False
    assert f"{relative}: read_refused" in result.details


def test_micro_verifier_still_parses_a_plain_patched_file(repo_and_host):
    repo, _host_dir, _host_file = repo_and_host
    (repo / "pkg" / "broken.py").write_text("x = (\n")
    result = MicroVerifier.verify(
        "",
        repo,
        ["pkg/broken.py"],
        verifier_env_metadata={"allow_bare_python": True, "interpreter": "python3"},
    )
    assert result.syntax_ok is False
    assert result.error_message == "SYNTAX_ERROR"
    assert "read_refused" not in result.details


# --- #3037 R6-2: committee restore refused after a winner was chosen ----------------------

TARGET = "toy/math_util.py"
ORIGINAL = "def add(a, b):\n    return a - b\n"
DIFF = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"
SSRP = (
    "FILE: toy/math_util.py\nSEARCH:\n    return a - b\nREPLACE:\n    return a + b\nEND\n"
    "<<<<<<< SEARCH\n    return a - b\n=======\n    return a + b\n>>>>>>> REPLACE\n"
)


@pytest.fixture
def _world_c_copies_of_tmp_repos(monkeypatch):
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")


TWO_MODELS = ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"]


def _committee_request(repo: Path, models: list[str]) -> LocalModelExecutorRequest:
    return LocalModelExecutorRequest(
        task_id="reads-3018-r6-2",
        problem_statement="test",
        repo_root=str(repo),
        target_file=TARGET,
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
        route_context={
            "verifier_command": ["python3", "-c", "pass"],
            "python_executable": "python3",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": list(models),
            },
        },
    )


def _pipeline_result(*_a, **_kw):
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


def _verifier(req):
    """The first pass fails (so the committee runs); committee candidates pass."""
    passed = "#committee-" in req.task_id
    return IsolatedVerifierReceipt(
        task_id=req.task_id,
        verifier_status="pass" if passed else "fail",
        exit_code=0 if passed else 1,
        stdout_tail="" if passed else "AssertionError",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
    )


def _committee_candidate_result():
    r = MagicMock()
    r.final_patch = SSRP
    r.pre_verification_final_patch = ""
    r.failure_reason = ""
    r._orchestrator_verifier_evidence_passed = False
    r._orchestrator_verifier_evidence_fields = ""
    r._orchestrator_retry_prompt_evidence_hash = ""
    r._semantic_retry_telemetry = {}
    r.model_decisions = [
        {
            "phase": "patch",
            "output_class": "VALID_SEARCH_REPLACE",
            "parser_error_kind": "none",
            "status": "SUCCESS",
            "output_excerpt": SSRP,
        }
    ]
    return r


def _run_committee(repo: Path, committee_run, models: list[str] = TWO_MODELS):
    with (
        patch(
            "nexus.services.local_heal.local_model_capability_executors."
            "LocalHealPipelineCapabilityExecutor.execute",
            side_effect=_pipeline_result,
        ),
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply",
            side_effect=_apply_receipt,
        ),
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_verifier",
            side_effect=_verifier,
        ),
        patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None),
        patch("nexus.services.local_heal.pipeline.HealPipeline.run", side_effect=committee_run),
    ):
        return LocalModelExecutor.run(
            _committee_request(repo, models), provider=InjectedLocalModelProvider(lambda _: DIFF)
        )


def _committee_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "toy").mkdir(parents=True)
    (repo / TARGET).write_text(ORIGINAL)
    host_file = tmp_path / "host" / "math_util.py"
    host_file.parent.mkdir()
    host_file.write_text(HOST_TEXT)
    return repo, host_file


@pytest.mark.usefixtures("_world_c_copies_of_tmp_repos")
def test_committee_restore_refused_after_a_winner_hands_on_no_patch(tmp_path):
    repo, host_file = _committee_repo(tmp_path)
    calls = []

    def committee_run(heal_ctx):
        calls.append(heal_ctx)
        if len(calls) == 2:  # the second candidate leaves a link at the target
            (repo / TARGET).unlink()
            (repo / TARGET).symlink_to(host_file)
        return _committee_candidate_result()

    resp = _run_committee(repo, committee_run)
    meta = resp.raw_model_metadata
    assert len(calls) == 2
    assert meta["delegated_retry_committee_restore_refused"] is True
    assert resp.candidate_patch == ""
    assert meta.get("solved") is not True
    assert meta.get("isolated_verifier_status") != "pass"
    assert meta["isolated_apply_status"] == "restore_refused"
    assert "selected_candidate_model" not in meta or not meta["selected_candidate_model"]
    candidates = json.loads(meta["delegated_retry_committee_candidates_json"])
    assert not any(c.get("selected") for c in candidates)
    assert host_file.read_text() == HOST_TEXT


@pytest.mark.usefixtures("_world_c_copies_of_tmp_repos")
def test_committee_restore_refused_at_a_third_candidate_reports_no_winner(tmp_path):
    repo, host_file = _committee_repo(tmp_path)
    calls = []

    def committee_run(heal_ctx):
        calls.append(heal_ctx)
        if len(calls) == 3:  # candidate 1 won, candidate 2 was rejected behind it
            (repo / TARGET).unlink()
            (repo / TARGET).symlink_to(host_file)
        return _committee_candidate_result()

    resp = _run_committee(repo, committee_run, [*TWO_MODELS, "llama3.1:8b"])
    meta = resp.raw_model_metadata
    assert len(calls) == 3
    assert resp.candidate_patch == ""
    assert meta.get("solved") is not True
    assert meta["delegated_retry_stage"] != "committee_winner_selected"
    candidates = json.loads(meta["delegated_retry_committee_candidates_json"])
    assert not any(c.get("selected") for c in candidates)
    assert all(c["rejection_reason"] != "winner_already_selected" for c in candidates)


@pytest.mark.usefixtures("_world_c_copies_of_tmp_repos")
def test_committee_winner_without_a_refusal_is_still_handed_on(tmp_path):
    repo, _host_file = _committee_repo(tmp_path)

    resp = _run_committee(repo, lambda _ctx: _committee_candidate_result())
    meta = resp.raw_model_metadata
    assert "delegated_retry_committee_restore_refused" not in meta
    assert resp.candidate_patch.strip()
    assert meta.get("solved") is True
    assert meta.get("selected_candidate_model")
