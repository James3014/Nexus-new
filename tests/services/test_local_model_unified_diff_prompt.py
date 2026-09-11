from pathlib import Path

from nexus.services.local_heal.isolated_workspace_apply import (
    IsolatedApplyRequest,
    run_isolated_workspace_apply,
)
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    _normalize_candidate_patch,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider


def _request(tmp_path: Path) -> LocalModelExecutorRequest:
    (tmp_path / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    return LocalModelExecutorRequest(
        task_id="unified-diff-prompt-test",
        problem_statement="Change target to return 2.",
        repo_root=str(tmp_path),
        target_file="target.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=("test:unified-diff-prompt",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "unified_diff",
                "model_call_allowed": True,
                "executor_model": "qwen2.5-coder:7b-instruct",
            },
            "target_symbol": "target",
            "locked_search": "def target():\n    return 1\n",
        },
        dry_run=False,
    )


def test_unified_diff_prompt_requires_effective_edit_and_preserves_one_sided_edits(tmp_path: Path):
    captured = {}

    def generate(request):
        captured["prompt"] = request.prompt
        return "--- a/target.py\n+++ b/target.py\n@@ -1,2 +1,2 @@\n def target():\n-    return 1\n+    return 2\n"

    provider = InjectedLocalModelProvider(generate)
    response = LocalModelExecutor.run(_request(tmp_path), provider=provider)
    prompt = captured["prompt"]
    assert "effective edit" in prompt
    assert "context-only" in prompt
    assert "replacement" in prompt
    assert "pure insertion or deletion" in prompt
    assert response.local_model_called is True

    request = _request(tmp_path)
    replacement = "--- a/target.py\n+++ b/target.py\n@@ -1,2 +1,2 @@\n def target():\n-    return 1\n+    return 2\n"
    insertion = "--- a/target.py\n+++ b/target.py\n@@ -1,2 +1,3 @@\n def target():\n     return 1\n+    return 2\n"
    deletion = "--- a/target.py\n+++ b/target.py\n@@ -1,2 +1,1 @@\n def target():\n-    return 1\n"
    for patch in (replacement, insertion, deletion):
        normalized, metadata = _normalize_candidate_patch(
            request, request.route_context["locked_search"], patch
        )
        assert normalized == patch
        assert metadata.get("protocol_used") == "passthrough"


def test_unified_diff_prompt_does_not_make_context_only_hunk_valid(tmp_path: Path):
    request = _request(tmp_path)
    noop = "--- a/target.py\n+++ b/target.py\n@@ -1,2 +1,2 @@\n def target():\n     return 1\n"
    normalized, metadata = _normalize_candidate_patch(
        request, request.route_context["locked_search"], noop
    )
    assert normalized == noop
    assert metadata.get("protocol_used") == "passthrough"
    receipt = run_isolated_workspace_apply(
        IsolatedApplyRequest(
            task_id=request.task_id,
            source_root=str(tmp_path),
            target_file="target.py",
            unified_diff=noop,
            selected_candidate_hash="noop",
            work_dir=str(tmp_path),
            mutation_allowed=True,
        )
    )
    assert receipt.patch_apply_status == "failed"
    assert (tmp_path / "target.py").read_text(encoding="utf-8") == "def target():\n    return 1\n"
