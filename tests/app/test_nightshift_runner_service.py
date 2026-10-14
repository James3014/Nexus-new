import pytest
from pathlib import Path
from nexus.app.nightshift_runner_service import AutoResearchNightShift


def test_nightshift_service_init(tmp_path: Path):
    runner = AutoResearchNightShift(project_root=tmp_path, task="test-task")
    assert runner.task == "test-task"
    assert runner.project_root == tmp_path.resolve()


def test_nightshift_uses_injected_context_hub(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    hub = object()

    runner = AutoResearchNightShift(project_root=tmp_path, task="test-task", context_hub=hub)

    assert runner.hub is hub


def test_nightshift_policy_bypass_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NIGHTSHIFT_BYPASS_POLICY", "1")
    runner = AutoResearchNightShift(project_root=tmp_path, task="test-task")
    assert runner._check_policy_readiness() is True


def test_nightshift_tier1_validation_uses_py_compile_for_nongit_fixture(tmp_path: Path):
    runner = AutoResearchNightShift(
        project_root=tmp_path,
        task="benchmark task",
        target_file="demo.py",
        test_file="tests",
    )
    (tmp_path / "demo.py").write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_demo.py").write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "from demo import ok\n\n"
        "def test_ok():\n"
        "    assert ok() == 1\n",
        encoding="utf-8",
    )

    ok, msg = runner._run_tier1_validation(tmp_path)
    assert ok is True
    assert msg == "tier1_pass"


def test_nightshift_finalizes_existing_unified_receipt(tmp_path: Path):
    from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest

    request = UnifiedRuntimeRequest(
        task_id="nightshift-finalize-test",
        workspace_revision="revision-001",
        task_statement="finalize nightshift receipt",
        task_type="repair",
        route={"recommended_flow": "direct", "provider": "gemini"},
    )
    receipt = UnifiedRuntime().run(
        request,
        capability_invokers={
            name: (
                lambda context, _name=name: {
                    "task_id": context["task_id"],
                    "invoked": True,
                    "gate_passed": True,
                    "evidence_refs": [f"test:{_name}:{context['task_id']}:fixture"],
                }
            )
            for name in (
                "harness_preflight_sensor",
                "delivery_gate",
                "mempalace_gate",
                "artifact_gate",
                "claim_gate",
                "research_route",
            )
        },
        online_invoker=lambda _context: {
            "invoked": True,
            "output_delivered": True,
            "gate_passed": True,
            "provider_call_count": 1,
            "evidence_refs": ["online:test:provider"],
        },
    )
    runner = AutoResearchNightShift(project_root=tmp_path, task="finalize nightshift receipt")
    runner.last_unified_runtime_receipt = receipt
    runner.last_learning_closure = {"memory_written": True}

    runner._finalize_unified_runtime_receipt(terminal_status="SUCCESS", final_score=1.0)

    assert runner.last_unified_runtime_receipt["receipt_complete"] is True
    assert runner.last_unified_runtime_receipt["claim_boundary"]["public_claim_allowed"] is False


def test_nightshift_unified_request_uses_gateway_provider(tmp_path: Path):
    seen: dict[str, str] = {}

    class _Gateway:
        oauth_provider = "codex"

        def ask_unified(self, request, **_kwargs):
            seen["provider"] = request.route["provider"]
            return {
                "schema": "nexus.unified_runtime.receipt.v1",
                "task_id": request.task_id,
                "online": {
                    "status": "SUCCEEDED",
                    "response": {
                        "response": {"status": "APPROVED", "patch": "value = 2\n"},
                        "raw_response": "raw",
                    },
                },
            }

    runner = AutoResearchNightShift(
        project_root=tmp_path,
        task="provider-aware nightshift",
        gateway=_Gateway(),
    )
    response, raw, _receipt = runner._ask_unified_candidate(
        workpath=tmp_path,
        round_id=1,
        attempt=1,
        model="gpt-5.5",
        prompt="Return a candidate",
        payload="Return full file content.",
    )

    assert seen["provider"] == "codex"
    assert response["patch"] == "value = 2\n"
    assert raw == "raw"


def test_nightshift_persists_canonical_episode_without_memory_store(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "nexus.research.learn_mode.LearnModeService.ask",
        lambda *_args, **_kwargs: {"citations": []},
    )
    runner = AutoResearchNightShift(project_root=tmp_path, task="episode nightshift")
    runner.memory_store = None
    closure = runner._persist_learning_closure("FAILED", "tier2", 0.0)
    assert closure["learning_episode_status"] == "PASS"
    ledger = tmp_path / ".nexus" / "memory" / "learning_episodes.jsonl"
    assert ledger.exists()
    runner._persist_learning_closure("FAILED", "tier2", 0.0)
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1


def _policy_routed_online_worker():
    from nexus.services.nightshift_queue_consumer import resolve_nightshift_online_worker

    return resolve_nightshift_online_worker()


def _git_fixture(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "demo.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "demo.py"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=nightshift@example.invalid",
            "-c",
            "user.name=nightshift",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )


def _runner_with_fixture_transport(root: Path, **kwargs):
    from nexus.services.gateway import BattlesuitGateway

    _git_fixture(root)
    gateway = BattlesuitGateway(project_root=root)
    calls: list[dict] = []

    def _fixture_structured(*_args, **call_kwargs):
        calls.append(call_kwargs)
        return {"status": "APPROVED", "patch": "value = 2\n"}

    gateway.ask_structured = _fixture_structured
    runner = AutoResearchNightShift(
        project_root=root,
        task="nightshift admission fixture",
        target_file="demo.py",
        gateway=gateway,
        **kwargs,
    )
    return runner, calls


def test_nightshift_default_model_is_admitted_policy_worker(tmp_path: Path):
    from nexus.services.model_workforce_policy import (
        NON_ADMISSIBLE_STATES,
        WorkforcePolicyLoader,
    )
    from nexus.services.nightshift_queue_consumer import _HOST_WORKFORCE_POLICY_PATH

    worker = _policy_routed_online_worker()
    snapshot = WorkforcePolicyLoader(policy_path=_HOST_WORKFORCE_POLICY_PATH).load()
    admitted_models = {
        candidate.model
        for candidate in snapshot.workers.values()
        if candidate.state not in NON_ADMISSIBLE_STATES and candidate.availability == "AVAILABLE"
    }

    runner = AutoResearchNightShift(project_root=tmp_path, task="default model")

    assert runner.model_name == worker.model
    assert runner.model_name in admitted_models
    assert runner.fallback_model_name is None
    assert runner.workforce_bindings["online"]["worker_id"] == worker.worker_id
    assert set(worker.requires) <= set(runner.workforce_bindings["online"]["controls"])


@pytest.mark.parametrize("task_kind", ["generation", "evaluation"])
def test_nightshift_online_request_carries_admitted_workforce_binding(
    tmp_path: Path, task_kind: str
):
    runner, _calls = _runner_with_fixture_transport(tmp_path)
    worker = _policy_routed_online_worker()

    _response, _raw, receipt = runner._ask_unified_candidate(
        workpath=tmp_path,
        round_id=1,
        attempt=1,
        model=runner.model_name,
        prompt="Return a candidate",
        payload="Return full file content.",
        task_kind=task_kind,
    )

    admission = receipt["workforce_admission"]
    authority = receipt["gateway_invocation_authority"]
    assert admission["overall_decision"] == "ALLOW"
    assert authority["status"] == "ALLOW"
    assert authority["gate_passed"] is True
    assert authority["resolved_worker_id"] == worker.worker_id
    assert authority["online_model_name"] == worker.model


def test_nightshift_unadmitted_model_override_is_blocked(tmp_path: Path):
    runner, calls = _runner_with_fixture_transport(tmp_path, model_name="gemini-3.1-pro-preview")

    response, _raw, receipt = runner._ask_unified_candidate(
        workpath=tmp_path,
        round_id=1,
        attempt=1,
        model=runner.model_name,
        prompt="Return a candidate",
        payload="Return full file content.",
    )

    authority = receipt["gateway_invocation_authority"]
    assert runner.model_name == "gemini-3.1-pro-preview"
    assert authority["status"] == "BLOCKED"
    assert authority["gate_passed"] is False
    assert authority["failure_reason"] == "online_model_name_mismatch"
    assert receipt["online"]["invoked"] is False
    assert calls == []
    assert response["status"] == "FAIL"


def test_nightshift_pending_manifest_item_carries_policy_bindings(tmp_path: Path):
    import json

    runner = AutoResearchNightShift(project_root=tmp_path, task="manifest bindings")
    runner._append_to_pending_manifest("task-a", "demo.py", "abc123", 1.0, str(tmp_path))

    items = json.loads(runner.pending_manifest_path.read_text(encoding="utf-8"))
    assert items[0]["workforce_bindings"] == runner.workforce_bindings
    assert items[0]["workforce_bindings"]["online"]["worker_id"] == (
        _policy_routed_online_worker().worker_id
    )
