"""Armor-on local repair lane uses the bare HealPipeline contract and a runnable World C.

Measured defect (7B armor-on A/B, 0/12 vs bare 11/12 on the same tasks): the World C and isolated
apply workspaces held only the target file, so ``python repro.py`` could not run and every correct
candidate failed verification; the delegated retry then patched the caller's source tree; and the
pipeline bridge merged the system prompt into the user prompt and dropped the bare lane's options.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from nexus.services.local_heal import local_model_provider
from nexus.services.local_heal.client import default_heal_generation_options
from nexus.services.local_heal.isolated_workspace_apply import (
    IsolatedApplyRequest,
    run_isolated_workspace_apply,
)
from nexus.services.local_heal.local_model_capability_context import LocalModelCapabilityContext
from nexus.services.local_heal.local_model_capability_executors import (
    LocalHealPipelineCapabilityExecutor,
)
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutorRequest,
    _delegated_retry_world_c,
    _world_c_verifier_files,
)
from nexus.services.local_heal.local_model_provider import (
    LocalModelProviderRequest,
    LocalModelProviderResponse,
    OllamaLocalModelProvider,
)
from nexus.services.local_heal.pipeline_isolation import (
    prepare_world_c_workspace,
    verifier_input_files,
)

BUGGY = "def f():\n    return 1\n"
REPRO = "import sys\nfrom m import f\nsys.exit(0 if f() == 2 else 1)\n"
PATCH = "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"


@pytest.fixture
def synthetic_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A task snapshot like memory_ab_tasks_v1: no .git and no pyproject.toml."""
    monkeypatch.setenv("NEXUS_ARMOR_ALLOW_EPHEMERAL", "1")
    monkeypatch.setenv("NEXUS_ARMOR_ARTIFACT_ROOT", str(tmp_path / "armor"))
    source = tmp_path / "task"
    source.mkdir()
    (source / "m.py").write_text(BUGGY, encoding="utf-8")
    (source / "repro.py").write_text(REPRO, encoding="utf-8")
    (source / "unrelated.txt").write_text("not a verifier input\n", encoding="utf-8")
    return source


def test_verifier_input_files_keeps_only_relative_files_inside_source(
    synthetic_task: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    (synthetic_task / "link.py").symlink_to(outside)
    command = (
        "python",
        "-u",
        "repro.py",
        "missing.py",
        "../outside.py",
        str(outside),
        "link.py",
        "repro.py",
    )

    assert verifier_input_files(synthetic_task, command) == ("repro.py",)
    # argv[0] is the interpreter, never a task file
    assert verifier_input_files(synthetic_task, ("repro.py",)) == ()


def test_world_c_workspace_contains_the_verifier_script(synthetic_task: Path) -> None:
    files = verifier_input_files(synthetic_task, ("python", "repro.py"))
    workspace = prepare_world_c_workspace(
        synthetic_task, "t-world-c", target_file="m.py", verifier_files=files
    )

    assert (workspace / "m.py").read_text(encoding="utf-8") == BUGGY
    assert (workspace / "repro.py").read_text(encoding="utf-8") == REPRO
    assert not (workspace / "unrelated.txt").exists()


def test_isolated_apply_copies_verifier_inputs_without_changing_the_applied_hash(
    synthetic_task: Path, tmp_path: Path
) -> None:
    candidate_hash = hashlib.sha256(PATCH.encode("utf-8")).hexdigest()
    request = IsolatedApplyRequest(
        task_id="t-apply",
        source_root=str(synthetic_task),
        target_file="m.py",
        unified_diff=PATCH,
        selected_candidate_hash=candidate_hash,
        work_dir=str(tmp_path / "apply"),
        mutation_allowed=True,
        verifier_files=("repro.py", "../escape.py"),
    )
    receipt = run_isolated_workspace_apply(request)

    workspace = Path(receipt.workspace_path)
    assert receipt.patch_apply_status == "applied"
    assert receipt.selected_candidate_hash_matches_applied is True
    assert (workspace / "repro.py").read_text(encoding="utf-8") == REPRO
    assert "return 2" in (workspace / "m.py").read_text(encoding="utf-8")
    assert (synthetic_task / "m.py").read_text(encoding="utf-8") == BUGGY


def test_delegated_retry_runs_in_an_isolated_world_c_copy(synthetic_task: Path) -> None:
    request = LocalModelExecutorRequest(
        task_id="t-retry",
        problem_statement="f() returns 1 instead of 2",
        repo_root=str(synthetic_task),
        target_file="m.py",
        selected_capabilities=("repair_loop",),
        evidence_refs=("ref",),
        route_context={"verifier_command": ["python", "repro.py"]},
    )
    route_ctx = dict(request.route_context)

    workspace = _delegated_retry_world_c(request, route_ctx)

    assert Path(workspace).resolve() != synthetic_task.resolve()
    assert (Path(workspace) / "repro.py").is_file()
    assert route_ctx["world_c_source_root"] == str(synthetic_task)
    assert route_ctx["world_c_workspace_path"] == str(workspace)
    assert _world_c_verifier_files(request) == {"verifier_files": ("repro.py",)}


class _CapturingProvider:
    def __init__(self) -> None:
        self.requests: list[LocalModelProviderRequest] = []

    def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
        self.requests.append(request)
        return LocalModelProviderResponse(
            provider_invoked=True, model_called=True, model_name="m", output_text="ok"
        )


def test_pipeline_bridge_sends_bare_lane_system_split_and_options(
    synthetic_task: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.services.local_heal import pipeline

    def fake_run(self, ctx):  # one planner-style call, exactly as OllamaLLMClient makes it
        self.ollama_generate("SYSTEM RULES", "USER TASK", model="ignored", phase="patch")
        return ctx

    monkeypatch.setattr(pipeline.HealPipeline, "run", fake_run)
    provider = _CapturingProvider()
    ctx = LocalModelCapabilityContext(
        task_id="t-bridge",
        source_root=str(synthetic_task),
        problem_statement="f() returns 1 instead of 2",
        target_file="m.py",
        target_symbol="f",
        selected_capabilities=("repair_loop",),
        execution_topology="localheal_pipeline",
        evidence_refs=("ref",),
        route_context={
            "run_group": "bridge-contract",
            "verifier_command": ["python", "repro.py"],
            "signal_snapshot": {"executor_model": "qwen2.5-coder:7b-instruct"},
        },
        provider=provider,
    )

    LocalHealPipelineCapabilityExecutor().execute(ctx)

    assert len(provider.requests) == 1
    sent = provider.requests[0]
    assert sent.system_prompt == "SYSTEM RULES"
    assert sent.user_prompt == "USER TASK"
    assert sent.prompt == "SYSTEM RULES\n\nUSER TASK"  # ledger hash input unchanged
    assert sent.options == default_heal_generation_options()
    assert sent.model_name == "qwen2.5-coder:7b-instruct"


def test_default_options_match_the_bare_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_OLLAMA_NUM_CTX", raising=False)
    monkeypatch.delenv("NEXUS_OLLAMA_NUM_PREDICT", raising=False)
    bare = pytest.importorskip("benchmarking.swebench_lite.swe_local_heal")
    assert default_heal_generation_options() == {
        "temperature": 0.0,
        "num_ctx": bare.DEFAULT_OLLAMA_NUM_CTX,
        "num_predict": bare.DEFAULT_OLLAMA_NUM_PREDICT,
    }


def _capture_ollama_payload(monkeypatch: pytest.MonkeyPatch, request: LocalModelProviderRequest):
    sent: dict = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        sent.update(json.loads(req.data.decode("utf-8")))
        return _Resp(json.dumps({"response": "ok", "eval_count": 1}).encode("utf-8"))

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_PROVIDER", "ollama")
    monkeypatch.setattr(local_model_provider.urllib.request, "urlopen", fake_urlopen)
    response = OllamaLocalModelProvider().generate(request)
    assert response.model_called is True
    return sent


def test_ollama_provider_sends_system_field_for_split_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture_ollama_payload(
        monkeypatch,
        LocalModelProviderRequest(
            task_id="t",
            prompt="SYS\n\nUSER",
            evidence_refs=(),
            model_name="qwen2.5-coder:7b-instruct",
            system_prompt="SYS",
            user_prompt="USER",
        ),
    )
    assert sent["system"] == "SYS"
    assert sent["prompt"] == "USER"


def test_ollama_provider_legacy_request_payload_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture_ollama_payload(
        monkeypatch,
        LocalModelProviderRequest(
            task_id="t",
            prompt="WHOLE PROMPT",
            evidence_refs=(),
            model_name="qwen2.5-coder:7b-instruct",
        ),
    )
    assert "system" not in sent
    assert sent["prompt"] == "WHOLE PROMPT"
