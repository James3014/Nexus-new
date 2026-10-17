from pathlib import Path

import pytest

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

    # #2189: the Online provider is the policy-admitted worker's provider; the
    # gateway's auto-detected default ("codex" here) no longer leaks into the route.
    assert seen["provider"] == _policy_routed_online_worker().provider
    assert seen["provider"] != "codex"
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


def _policy_routed_online_worker(role: str = "fast_bounded_implementation"):
    from nexus.services.nightshift_queue_consumer import resolve_nightshift_online_worker

    return resolve_nightshift_online_worker(role)


def _git_fixture(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "demo.py").write_text("value = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_demo.py").write_text(
        "def test_demo():\n    assert True\n", encoding="utf-8"
    )
    # The operator's workspace Online policy (a separate gate from Workforce
    # Admission) allows Online here so the admitted call reaches the transport.
    (root / ".nexus").mkdir()
    (root / ".nexus" / "online_execution_policy.json").write_text(
        '{"default_online_policy": "auto"}', encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(root), "add", "demo.py", "tests"], check=True)
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


@pytest.fixture(params=["ollama", "gemini"])
def fake_registered_cli(request, monkeypatch):
    """Hermetic transport: whatever the gateway's host default, no real CLI runs.

    The gateway default provider is pinned to each auto-detected value in turn and
    the Ollama probe points at a closed port, so results never depend on the host.
    The registered CLI builder is replaced by a recorder that reports the provider
    it was built for.
    """
    import nexus.services.unified_runtime as unified_runtime

    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", request.param)
    monkeypatch.setenv("NEXUS_OLLAMA_ENDPOINT", "http://127.0.0.1:9")
    built: list[tuple[str, str]] = []
    calls: list[dict] = []

    def _builder(provider, *, command=None, model_name=None, timeout_sec=None):
        built.append((provider, model_name))

        def _invoker(context):
            calls.append(dict(context))
            return unified_runtime.normalize_online_invoker_payload(
                provider=provider,
                task_id=str(context.get("task_id", "")),
                invoked=True,
                output_delivered=True,
                gate_passed=True,
                provider_call_count=1,
                response={"status": "APPROVED", "patch": "value = 2\n"},
                raw_response="raw",
                evidence_refs=[f"fixture:{provider}"],
                transport="registered_cli",
                selection_source="workforce_admission",
            )

        _invoker.provider = provider
        return _invoker

    monkeypatch.setattr(unified_runtime, "build_registered_online_invoker", _builder, raising=False)
    return {"gateway_default": request.param, "built": built, "calls": calls}


def _runner(root: Path, *, with_card: bool = True, **kwargs):
    from nexus.services.gateway import BattlesuitGateway

    _git_fixture(root)
    runner = AutoResearchNightShift(
        project_root=root,
        task="nightshift admission fixture",
        target_file="demo.py",
        gateway=BattlesuitGateway(project_root=root),
        **kwargs,
    )
    runner.resolved_target_file = runner._resolve_target_file()
    if with_card:
        assert runner._record_task_card()
    return runner


def _ask(runner, root: Path, *, task_kind: str = "generation", model=None):
    return runner._ask_unified_candidate(
        workpath=root,
        round_id=1,
        attempt=1,
        model=model or runner.model_name,
        prompt="Return a candidate",
        payload="Return full file content.",
        task_kind=task_kind,
    )


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


GOVERNED_ONLY_CONTROLS = {
    "task_card",
    "allowed_files",
    "mandatory_commands",
    "independent_verification",
}


@pytest.mark.parametrize("with_card", [True, False])
def test_nightshift_online_request_blocked_without_governed_task_card(
    tmp_path: Path, fake_registered_cli, with_card: bool
):
    """A runner-built card is self-issued metadata and never declares task_card (#2189)."""
    runner = _runner(tmp_path, with_card=with_card)
    worker = _policy_routed_online_worker()

    response, _raw, receipt = _ask(runner, tmp_path)

    admission = receipt["workforce_admission"]
    record = admission["records"][0]
    assert record["request"]["requested_worker_id"] == worker.worker_id
    assert not GOVERNED_ONLY_CONTROLS & set(record["request"]["provided_controls"])
    assert "task_card" in worker.requires
    assert admission["overall_decision"] == "BLOCK"
    assert "task_card" in record["decision"]["missing_controls"]
    assert receipt["gateway_invocation_authority"]["status"] == "BLOCKED"
    assert receipt["online"]["invoked"] is False
    assert fake_registered_cli["calls"] == []
    assert response["status"] == "FAIL"


def test_nightshift_route_provider_is_admitted_worker_provider(tmp_path: Path, fake_registered_cli):
    runner = _runner(tmp_path)
    seen = {}
    original = runner.gateway.ask_unified

    def _spy(request, **kwargs):
        seen["route"] = dict(request.route)
        return original(request, **kwargs)

    runner.gateway.ask_unified = _spy
    _ask(runner, tmp_path)

    worker = _policy_routed_online_worker()
    assert seen["route"]["provider"] == worker.provider
    assert seen["route"]["provider"] != fake_registered_cli["gateway_default"]
    assert seen["route"]["workforce_bindings"]["online"]["worker_id"] == worker.worker_id


def test_nightshift_task_card_hash_is_recorded_with_run(tmp_path: Path, fake_registered_cli):
    import hashlib
    import json

    runner = _runner(tmp_path)
    card = runner.task_card_path.read_bytes()

    assert hashlib.sha256(card).hexdigest() == runner.task_card_sha256
    payload = json.loads(card)
    assert payload["target_file"] == "demo.py"
    assert payload["tier1_commands"] == runner._tier1_commands()

    _response, _raw, receipt = _ask(runner, tmp_path)
    assert f"nightshift:task_card:sha256:{runner.task_card_sha256}" in json.dumps(receipt)
    assert fake_registered_cli["calls"] == []


def test_nightshift_unadmitted_model_override_is_blocked(tmp_path: Path, fake_registered_cli):
    runner = _runner(tmp_path, model_name="gemini-3.1-pro-preview")

    response, _raw, receipt = _ask(runner, tmp_path)

    authority = receipt["gateway_invocation_authority"]
    assert runner.model_name == "gemini-3.1-pro-preview"
    assert authority["status"] == "BLOCKED"
    assert authority["gate_passed"] is False
    assert receipt["online"]["invoked"] is False
    assert fake_registered_cli["calls"] == []
    assert response["status"] == "FAIL"


def test_nightshift_policy_load_failure_blocks_online_calls(
    tmp_path: Path, fake_registered_cli, monkeypatch
):
    import nexus.services.nightshift_queue_consumer as consumer
    from nexus.services.model_workforce_policy import WorkforcePolicyError

    def _unavailable(*_args, **_kwargs):
        raise WorkforcePolicyError("policy unavailable")

    monkeypatch.setattr(consumer, "resolve_nightshift_online_worker", _unavailable)
    runner = _runner(tmp_path)
    assert runner.model_name is None
    assert runner._candidate_models() == []

    _response, _raw, receipt = _ask(runner, tmp_path, model="gemini-3.8-flash-medium")

    assert receipt["workforce_admission"]["overall_decision"] == "BLOCK"
    assert receipt["gateway_invocation_authority"]["status"] == "BLOCKED"
    assert fake_registered_cli["calls"] == []


def test_nightshift_judge_uses_focused_verification_route(tmp_path: Path, fake_registered_cli):
    from nexus.services.model_workforce_policy import WorkforcePolicyError

    runner = _runner(tmp_path)
    try:
        judge_worker = _policy_routed_online_worker("focused_verification")
    except WorkforcePolicyError:
        judge_worker = None

    _response, _raw, receipt = _ask(
        runner, tmp_path, task_kind="evaluation", model=runner._judge_model_name()
    )

    authority = receipt["gateway_invocation_authority"]
    if judge_worker is None:
        # The policy routes no worker for the judge role: the call fails closed.
        assert receipt["workforce_admission"]["overall_decision"] == "BLOCK"
        assert authority["status"] == "BLOCKED"
        assert fake_registered_cli["calls"] == []
    else:
        assert authority["resolved_worker_id"] == judge_worker.worker_id


def test_nightshift_preflight_makes_no_model_call(tmp_path: Path, monkeypatch):
    import subprocess

    def _no_subprocess(*_args, **_kwargs):
        raise AssertionError("preflight must not invoke a model outside admission")

    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    runner = AutoResearchNightShift(
        project_root=tmp_path, task="preflight", model_name="gemini-3.1-pro-preview"
    )

    runner._preflight_models()

    assert runner.model_exhausted == {}
    assert not hasattr(runner, "_probe_model_capacity")


def test_nightshift_pending_manifest_item_carries_no_bindings(tmp_path: Path):
    import json

    runner = AutoResearchNightShift(project_root=tmp_path, task="manifest bindings")
    runner._append_to_pending_manifest("task-a", "demo.py", "abc123", 1.0, str(tmp_path))

    items = json.loads(runner.pending_manifest_path.read_text(encoding="utf-8"))
    assert "workforce_bindings" not in items[0]


def test_pending_manifest_two_appends_keep_both_entries(tmp_path: Path):
    import json

    runner = AutoResearchNightShift(project_root=tmp_path, task="manifest two appends")
    runner._append_to_pending_manifest("task-a", "demo.py", "abc123", 1.0, str(tmp_path))
    runner._append_to_pending_manifest("task-b", "demo.py", "def456", 1.0, str(tmp_path))

    items = json.loads(runner.pending_manifest_path.read_text(encoding="utf-8"))
    assert len(items) == 2
    assert [item["task"] for item in items] == ["task-a", "task-b"]
