from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path[:1]:
    sys.path.insert(0, str(ROOT))

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
from nexus.services.local_heal.local_model_executor import LocalModelExecutorResponse
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
from nexus.services.model_workforce_policy import WorkforcePolicyLoader
from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest


POLICY = ROOT / "nexus/config/model_workforce.yaml"


def _demand(
    channel: str = "local",
    *,
    demand_id: str | None = None,
    role: str = "bounded_code_candidate",
    autonomy: str = "L1",
    context: str = "nexus_bounded",
    mutation: bool = True,
) -> dict[str, object]:
    return {
        "schema": "nexus.workforce_demand.v1",
        "demand_id": demand_id or f"demand_{channel}",
        "execution_channel": channel,
        "requested_role": role,
        "minimum_autonomy": autonomy,
        "context_class": context,
        "mutation_intent": mutation,
        "external_verification_required": True,
        "route_authority": "CapabilityPlanner",
    }


def _demands(*items: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "nexus.workforce_demands.v1",
        "route_authority": "CapabilityPlanner",
        "demands": list(items),
    }


class _Planner:
    def __init__(self, workforce_demands: object | None = None, selected: list[str] | None = None) -> None:
        self.workforce_demands = workforce_demands
        self.selected = selected or []
        self.routes: list[dict[str, object]] = []
        self.plans = 0

    def plan(self, **kwargs: object) -> CapabilityPlan:
        self.plans += 1
        self.routes.append(dict(kwargs["route"]))
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=list(self.selected),
            required_capabilities=list(self.selected),
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=["claim_fail_closed"],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            signal_snapshot=(
                {"workforce_demands": self.workforce_demands}
                if self.workforce_demands is not None
                else {"route_truth_source": "CapabilityPlanner"}
            ),
        )


class _Loader:
    def __init__(self) -> None:
        self._real = WorkforcePolicyLoader(POLICY)
        self.load_calls = 0
        self.admit_calls = 0

    def load(self):
        self.load_calls += 1
        return self._real.load()

    def admit(self, request, snapshot):
        self.admit_calls += 1
        return self._real.admit(request, snapshot)


def _request(route: dict[str, object], *, local: bool = False, online: bool = True) -> UnifiedRuntimeRequest:
    route = dict(route)
    online_model_name = None
    if route.get("workforce_admission_enabled") is True and online:
        bindings = route.get("workforce_bindings")
        online_binding = bindings.get("online") if isinstance(bindings, dict) else None
        if isinstance(online_binding, dict):
            route.setdefault("provider", online_binding.get("provider"))
            route.setdefault(
                "online_transport_binding",
                {"provider": online_binding.get("provider")},
            )
            route.setdefault("online_invoker_provider", online_binding.get("provider"))
            online_model_name = str(online_binding.get("model") or "")
    return UnifiedRuntimeRequest(
        task_id="workforce-admission-runtime-test",
        workspace_revision="rev-workforce-admission",
        task_statement="run the bounded runtime admission seam",
        task_type="bugfix",
        route=route,
        local_enabled=local,
        online_enabled=online,
        online_model_name=online_model_name,
        local_request={"task_id": "workforce-admission-runtime-test"} if local else None,
    )


def _online(context: dict[str, object]) -> dict[str, object]:
    return {
        "task_id": context["task_id"],
        "invoked": True,
        "output_delivered": True,
        "gate_passed": True,
        "provider_call_count": 1,
        "evidence_refs": ["online:workforce-admission:test"],
    }


_online.provider = "codex"
_online.online_invoker_provider = "codex"


def _verifier(context: dict[str, object]) -> dict[str, object]:
    return {
        "task_id": context["task_id"],
        "status": "SUCCEEDED",
        "invoked": True,
        "gate_passed": True,
        "evidence": "bounded verifier",
        "evidence_refs": ["verifier:workforce-admission:test"],
    }


def _learning(context: dict[str, object]) -> dict[str, object]:
    return {
        "task_id": context["task_id"],
        "status": "SUCCEEDED",
        "invoked": True,
        "gate_passed": True,
        "evidence": "bounded learning",
        "evidence_refs": ["learning:workforce-admission:test"],
    }


@dataclass(frozen=True)
class _DataclassLocalRequest:
    task_id: str
    planner_snapshot: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {"task_id": self.task_id, "planner_snapshot": self.planner_snapshot}


class _CapturingLocal:
    def __init__(self) -> None:
        self.calls = 0
        self.seen_request: object | None = None

    def handle(self, request: object) -> dict[str, object]:
        self.calls += 1
        self.seen_request = request
        return {
            "schema": "nexus.local_assist.response.v1",
            "task_id": "workforce-admission-runtime-test",
            "local_model_invoked": True,
            "invoked": True,
            "output_delivered": True,
            "action": "candidate",
            "executor_invoked": True,
            "physical_callable": "LocalModelExecutor.run",
            "receipt_path": "/tmp/workforce-admission-local-receipt.json",
            "provider_call_count": 1,
            "model_call_count": 1,
            "evidence_refs": ["local:workforce-admission:test"],
            "verifier_summary": {
                "verifier_status": "pass",
                "verifier_reached": True,
                "exit_code": 0,
            },
            "candidate_summary": {
                "isolation_status": "isolated",
                "selected_candidate_hash": "abc123",
                "selected_candidate_hash_matches_applied": True,
            },
            "claim_boundary": {
                "local_model_executor_invoked": True,
                "executor_invoked": True,
            },
            "outcome_contributed": True,
        }


def _local_case(
    *,
    binding: dict[str, object] | None = None,
    planner_snapshot: dict[str, object] | None = None,
    local_request: object | None = None,
    demands: dict[str, object] | None = None,
) -> tuple[dict[str, object], _CapturingLocal]:
    route = {
        "workforce_admission_enabled": True,
        "workforce_bindings": {"local": binding or _bindings()["local"]},
    }
    planner = _Planner(demands or _demands(_demand("local", mutation=False)), selected=["local_model_executor"])
    local = _CapturingLocal()
    request = _request(route, local=True, online=False)
    request = replace(
        request,
        local_request=(
            local_request
            if local_request is not None
            else {
                "task_id": request.task_id,
                "planner_snapshot": planner_snapshot or {},
            }
        ),
    )
    receipt = UnifiedRuntime(
        planner=planner,
        local_service=local,
        workforce_policy_loader=_Loader(),
    ).run(request, verifier=_verifier, learning=_learning)
    return receipt, local


def _bindings() -> dict[str, object]:
    return {
        "local": {
            "worker_id": "local_coder_7b",
            "provider": "ollama",
            "model": "qwen2.5-coder:7b-instruct",
            "controls": ["focused_tests", "compile", "parser", "small_scope", "reversible_application"],
        },
        "online": {
            "worker_id": "codex_luna",
            "provider": "codex",
            "model": "gpt-5.6-luna",
            "controls": ["receipt", "independent_verification", "governed_adapter"],
        },
    }


def test_local_authority_is_exactly_propagated_and_binds_mapping_request_identity() -> None:
    receipt, local = _local_case(
        planner_snapshot={
            "executor_provider": "attacker-provider",
            "executor_model": "qwen2.5-coder:7b",
            "execution_topology": "legacy-topology",
            "protocol_mode": "legacy-protocol",
            "model_call_allowed": True,
            "legacy_context": {"forged": True},
            "workforce_admission": {"overall_decision": "BLOCK"},
            "workforce_admission_lineage": {"status": "FORGED"},
            "planner_decision_id": "forged-planner-decision",
            "route_truth_source": "forged-request",
            "policy_identity": {"policy_hash": "forged-policy"},
            "policy_hash": "forged-policy",
            "binding_hash": "forged-binding",
            "aggregate_binding_hash": "forged-aggregate",
            "selected_capabilities": ["forged-capability"],
            "evidence_refs": ["forged-evidence"],
            "task_id": "forged-task",
            "workspace_revision": "forged-workspace",
        }
    )

    authority = receipt["local_model_invocation_authority"]
    assert authority["schema"] == "nexus.local_model_invocation_authority.v1"
    assert authority["status"] == "ALLOW"
    assert authority["gate_passed"] is True
    assert authority["resolved_provider"] == "ollama"
    assert authority["resolved_model"] == "qwen2.5-coder:7b-instruct"
    assert receipt["plan_payload"]["local_model_invocation_authority"] == authority
    assert receipt["plan_payload"]["signal_snapshot"]["local_model_invocation_authority"] == authority
    assert receipt["local"]["context_trace"]["local_model_invocation_authority"] == authority
    assert receipt["context_trace"]["local_model_invocation_authority"] == authority
    seen = local.seen_request
    assert isinstance(seen, dict)
    snapshot = seen["planner_snapshot"]
    assert snapshot["executor_provider"] == authority["resolved_provider"]
    assert snapshot["executor_model"] == authority["resolved_model"]
    assert snapshot["execution_topology"] == "legacy-topology"
    assert snapshot["protocol_mode"] == "legacy-protocol"
    assert snapshot["model_call_allowed"] is True
    planner_snapshot = receipt["plan_payload"]["signal_snapshot"]
    for key in (
        "workforce_admission",
        "workforce_admission_lineage",
        "planner_decision_id",
        "selected_capabilities",
    ):
        assert snapshot[key] == planner_snapshot[key]
    assert snapshot["route_truth_source"] == "CapabilityPlanner"
    assert "evidence_refs" not in snapshot
    for key in (
        "legacy_context",
        "policy_identity",
        "policy_hash",
        "binding_hash",
        "aggregate_binding_hash",
        "task_id",
        "workspace_revision",
    ):
        assert key not in snapshot
    assert json.dumps(
        snapshot["local_model_invocation_authority"],
        sort_keys=True,
        separators=(",", ":"),
    ) == json.dumps(authority, sort_keys=True, separators=(",", ":"))
    assert local.calls == 1
    json.dumps(authority)


def test_local_authority_binds_dataclass_request_and_preserves_admitted_qwen_tag() -> None:
    binding = {
        "worker_id": "local_qwen3_8b",
        "provider": "ollama",
        "model": "qwen3:8b",
        "controls": ["bounded_context", "parser", "focused_tests", "external_verifier"],
    }
    request = _DataclassLocalRequest(
        task_id="workforce-admission-runtime-test",
        planner_snapshot={
            "executor_provider": "wrong",
            "executor_model": "qwen2.5:7b",
            "execution_topology": "legacy-topology",
            "protocol_mode": "legacy-protocol",
            "model_call_allowed": False,
            "workforce_admission": {"overall_decision": "BLOCK"},
            "workforce_admission_lineage": {"status": "FORGED"},
            "planner_decision_id": "forged-planner-decision",
            "route_truth_source": "forged-request",
            "policy_identity": {"policy_hash": "forged-policy"},
            "binding_hash": "forged-binding",
            "aggregate_binding_hash": "forged-aggregate",
            "selected_capabilities": ["forged-capability"],
            "evidence_refs": ["forged-evidence"],
        },
    )
    receipt, local = _local_case(binding=binding, local_request=request)

    authority = receipt["local_model_invocation_authority"]
    assert authority["resolved_model"] == "qwen3:8b"
    assert isinstance(local.seen_request, _DataclassLocalRequest)
    snapshot = local.seen_request.planner_snapshot
    assert snapshot["executor_provider"] == "ollama"
    assert snapshot["executor_model"] == "qwen3:8b"
    assert snapshot["execution_topology"] == "legacy-topology"
    assert snapshot["protocol_mode"] == "legacy-protocol"
    assert snapshot["model_call_allowed"] is False
    planner_snapshot = receipt["plan_payload"]["signal_snapshot"]
    for key in (
        "workforce_admission",
        "workforce_admission_lineage",
        "planner_decision_id",
        "selected_capabilities",
    ):
        assert snapshot[key] == planner_snapshot[key]
    assert snapshot["route_truth_source"] == "CapabilityPlanner"
    assert "evidence_refs" not in snapshot
    for key in ("policy_identity", "binding_hash", "aggregate_binding_hash", "evidence_refs"):
        assert key not in snapshot
    authority = receipt["local_model_invocation_authority"]
    assert json.dumps(
        snapshot["local_model_invocation_authority"],
        sort_keys=True,
        separators=(",", ":"),
    ) == json.dumps(authority, sort_keys=True, separators=(",", ":"))
    assert local.calls == 1


def test_conflicting_local_request_identity_cannot_override_admitted_identity() -> None:
    receipt, local = _local_case(
        planner_snapshot={
            "executor_provider": "evil-provider",
            "executor_model": "evil-model",
        }
    )

    assert receipt["local_model_invocation_authority"]["gate_passed"] is True
    assert local.seen_request["planner_snapshot"]["executor_provider"] == "ollama"
    assert local.seen_request["planner_snapshot"]["executor_model"] == "qwen2.5-coder:7b-instruct"
    assert local.calls == 1


def _formal_local_request(tmp_path: Path, *, task_id: str = "workforce-admission-runtime-test") -> LocalAssistRequest:
    target = tmp_path / "target.py"
    target.write_text("def target():\n    return 1\n", encoding="utf-8")
    return LocalAssistRequest(
        schema="nexus.local_assist.request.v1",
        task_id=task_id,
        parent_task_id=task_id,
        workspace_root=str(tmp_path),
        workspace_revision="rev-workforce-admission",
        task_statement="Produce an isolated bounded candidate for target.py.",
        action="verified-subtask",
        allowed_files=("target.py",),
        target_file="target.py",
        target_symbol="target",
        evidence_refs=("tests/services/test_unified_runtime_workforce_admission.py",),
        verifier_command=(sys.executable, "-c", "print('verified')"),
        requested_role="candidate",
        planner_snapshot={
            "execution_topology": "single_local_model",
            "protocol_mode": "unified_diff",
            "model_call_allowed": True,
        },
    )


def _formal_patch() -> str:
    return (
        "--- a/target.py\n"
        "+++ b/target.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def target():\n"
        "-    return 1\n"
        "+    return 2\n"
    )


def test_workforce_admission_invokes_formal_local_assist_executor_with_receipt_lineage(
    tmp_path: Path,
) -> None:
    local_request = _formal_local_request(tmp_path)
    executor_requests: list[object] = []
    provider = InjectedLocalModelProvider(
        lambda _request: _formal_patch(),
        provider_identity="ollama",
        model_identity="qwen2.5-coder:7b-instruct",
    )

    def bounded_executor(executor_request, *, provider=None):
        executor_requests.append(executor_request)
        return LocalModelExecutorResponse(
            invoked=True,
            local_model_called=True,
            candidate_patch=_formal_patch(),
            candidate_hash="model-candidate",
            reasoning_summary="bounded candidate",
            raw_model_metadata={
                "llm_call_ledger_records": [
                    {
                        "duration_sec": 0.01,
                        "prompt_hash": "prompt-hash",
                        "status": "ok",
                    }
                ],
                "selected_capabilities": ["local_model_executor"],
                "selected_capabilities_used": ["local_model_executor"],
                "capability_usage_status": {"local_model_executor": "used"},
            },
            provider="ollama",
            model_name="qwen2.5-coder:7b-instruct",
            error="",
            timeout=False,
            evidence_refs=executor_request.evidence_refs,
        )

    def isolated_apply(apply_request):
        return IsolatedApplyReceipt(
            task_id=apply_request.task_id,
            workspace_path=str(tmp_path / "isolated"),
            target_file=apply_request.target_file,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=apply_request.selected_candidate_hash,
            applied_patch_hash=apply_request.selected_candidate_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
        )

    def isolated_verifier(verifier_request):
        return IsolatedVerifierReceipt(
            task_id=verifier_request.task_id,
            verifier_status="pass",
            exit_code=0,
            stdout_tail="verified",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

    receipt = UnifiedRuntime(
        planner=_Planner(_demands(_demand("local")), selected=["local_model_executor"]),
        local_service=LocalAssistService(
            provider=provider,
            executor_runner=bounded_executor,
            apply_runner=isolated_apply,
            verifier_runner=isolated_verifier,
        ),
        workforce_policy_loader=_Loader(),
    ).run(
        replace(
            _request(
                {
                    "workforce_admission_enabled": True,
                    "workforce_bindings": {"local": _bindings()["local"]},
                },
                local=True,
                online=False,
            ),
            local_request=local_request,
        ),
        verifier=_verifier,
        learning=_learning,
    )

    local = receipt["local"]
    lineage = local["formal_local_runtime_lineage"]
    assert local["status"] == "SUCCEEDED"
    assert local["gate_passed"] is True
    assert lineage["schema"] == "nexus.formal_local_runtime_lineage.v1"
    assert lineage["entrypoint"] == "UnifiedRuntime._run_local"
    assert lineage["service"] == "LocalAssistService.handle"
    assert lineage["executor"] == "LocalModelExecutor.run"
    assert lineage["gate_passed"] is True
    assert lineage["provider_call_count"] == 1
    assert lineage["model_call_count"] == 1
    assert lineage["candidate_isolation_status"] == "isolated"
    assert lineage["verifier_reached"] is True
    assert lineage["verifier_status"] == "pass"
    assert receipt["context_trace"]["formal_local_runtime_lineage"] == lineage
    response = local["response"]
    assert response["schema"] == "nexus.local_assist.response.v1"
    assert response["physical_callable"] == "LocalModelExecutor.run"
    assert response["executor_invoked"] is True
    assert response["provider_call_count"] == 1
    assert response["candidate_summary"]["isolation_status"] == "isolated"
    assert response["verifier_summary"]["verifier_status"] == "pass"
    assert len(executor_requests) == 1
    executor_request = executor_requests[0]
    assert executor_request.model_name == "qwen2.5-coder:7b-instruct"
    assert executor_request.route_context["signal_snapshot"]["local_model_invocation_authority"] == receipt[
        "local_model_invocation_authority"
    ]
    disk_receipt = json.loads(Path(response["receipt_path"]).read_text(encoding="utf-8"))
    assert disk_receipt["physical_callable"] == "LocalModelExecutor.run"
    assert disk_receipt["executor_invoked"] is True
    assert (tmp_path / "target.py").read_text(encoding="utf-8") == "def target():\n    return 1\n"


def test_workforce_local_provider_mismatch_is_zero_model_call(tmp_path: Path) -> None:
    provider = InjectedLocalModelProvider(
        lambda _request: _formal_patch(),
        provider_identity="injected",
        model_identity="qwen2.5-coder:7b-instruct",
    )
    receipt = UnifiedRuntime(
        planner=_Planner(_demands(_demand("local")), selected=["local_model_executor"]),
        local_service=LocalAssistService(provider=provider),
        workforce_policy_loader=_Loader(),
    ).run(
        replace(
            _request(
                {
                    "workforce_admission_enabled": True,
                    "workforce_bindings": {"local": _bindings()["local"]},
                },
                local=True,
                online=False,
            ),
            local_request=_formal_local_request(tmp_path),
        ),
        verifier=_verifier,
        learning=_learning,
    )

    local = receipt["local"]
    lineage = local["formal_local_runtime_lineage"]
    assert local["status"] == "FAILED"
    assert local["invoked"] is False
    assert local["gate_passed"] is False
    assert local["provider_call_count"] == 0
    assert local["model_call_count"] == 0
    assert lineage["gate_passed"] is False
    assert lineage["failure_reason"] == "local_model_provider_identity_mismatch"
    assert lineage["provider_call_count"] == 0
    assert lineage["model_call_count"] == 0
    assert local["response"]["provider_call_count"] == 0
    assert local["response"]["model_call_count"] == 0
    assert local["response"]["local_model_invoked"] is False


@pytest.mark.parametrize("tamper", ["missing", "malformed", "binding", "aggregate", "policy"])
def test_local_authority_failures_are_zero_call_and_identical_across_receipt_surfaces(
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    import nexus.services.unified_runtime as unified_runtime_module

    original = unified_runtime_module.evaluate_runtime_workforce_admission

    def tampered(*args, **kwargs):
        payload = original(*args, **kwargs).to_dict()
        if tamper == "missing":
            payload["records"] = []
        elif tamper == "malformed":
            payload["records"][0]["schema"] = "wrong.schema"
        elif tamper == "binding":
            payload["records"][0]["binding_hash"] = "0" * 64
        elif tamper == "aggregate":
            payload["aggregate_binding_hash"] = "0" * 64
        else:
            payload["policy_identity"]["policy_hash"] = "0" * 64
        return payload

    monkeypatch.setattr(
        unified_runtime_module,
        "evaluate_runtime_workforce_admission",
        tampered,
    )
    receipt, local = _local_case()

    authority = receipt["local_model_invocation_authority"]
    assert authority["gate_passed"] is False
    assert receipt["local"]["invoked"] is False
    assert receipt["local"]["local_model_call_count"] == 0
    assert receipt["local"]["model_call_count"] == 0
    assert receipt["local"]["provider_call_count"] == 0
    assert receipt["local"]["response"]["provider_call_count"] == 0
    assert local.calls == 0
    surfaces = (
        receipt["local_model_invocation_authority"],
        receipt["plan_payload"]["local_model_invocation_authority"],
        receipt["plan_payload"]["signal_snapshot"]["local_model_invocation_authority"],
        receipt["local"]["context_trace"]["local_model_invocation_authority"],
        receipt["context_trace"]["local_model_invocation_authority"],
    )
    assert all(surface == authority for surface in surfaces)


def test_ambiguous_local_records_are_zero_call() -> None:
    receipt, local = _local_case(
        demands=_demands(
            _demand("local", demand_id="local_one", mutation=False),
            _demand("local", demand_id="local_two", mutation=False),
        )
    )

    assert receipt["local_model_invocation_authority"]["gate_passed"] is False
    assert receipt["local_model_invocation_authority"]["failure_reason"] == (
        "workforce_admission_local_record_ambiguous"
    )
    assert receipt["local"]["invoked"] is False
    assert local.calls == 0


def test_admission_disabled_preserves_legacy_overlay_and_7b_normalization() -> None:
    planner = _Planner(selected=["local_model_executor"])
    local = _CapturingLocal()
    request = UnifiedRuntimeRequest(
        task_id="workforce-admission-runtime-test",
        workspace_revision="rev-workforce-admission",
        task_statement="legacy local overlay",
        task_type="bugfix",
        route={"recommended_flow": "direct"},
        local_enabled=True,
        online_enabled=False,
        local_request={
            "task_id": "workforce-admission-runtime-test",
            "planner_snapshot": {
                "executor_provider": "ollama",
                "executor_model": "qwen2.5-coder:7b",
                "execution_topology": "legacy-topology",
                "protocol_mode": "legacy-protocol",
            },
        },
    )
    receipt = UnifiedRuntime(planner=planner, local_service=local).run(
        request,
        verifier=_verifier,
        learning=_learning,
    )

    assert "local_model_invocation_authority" not in receipt
    assert local.seen_request["planner_snapshot"]["executor_provider"] == "ollama"
    assert local.seen_request["planner_snapshot"]["executor_model"] == "qwen2.5-coder:7b-instruct"
    assert local.seen_request["planner_snapshot"]["execution_topology"] == "legacy-topology"
    assert local.seen_request["planner_snapshot"]["protocol_mode"] == "legacy-protocol"


@pytest.mark.parametrize("enabled_flag", [None, False])
def test_flag_off_preserves_legacy_shape_and_does_not_load_policy(enabled_flag: bool | None) -> None:
    planner = _Planner()
    loader = _Loader()
    route: dict[str, object] = {"recommended_flow": "direct"}
    if enabled_flag is not None:
        route["workforce_admission_enabled"] = enabled_flag
    receipt = UnifiedRuntime(planner=planner, workforce_policy_loader=loader).run(
        _request(route),
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert loader.load_calls == 0
    assert "workforce_admission" not in receipt
    assert "plan_payload" not in receipt
    assert not any(stage["name"] == "workforce_admission" for stage in receipt["stages"])


def test_request_flags_are_mirrored_to_planner_without_route_flags() -> None:
    planner = _Planner()
    UnifiedRuntime(planner=planner).run(
        _request({"recommended_flow": "direct"}, local=True, online=False),
        verifier=_verifier,
        learning=_learning,
    )

    assert planner.routes == [{"recommended_flow": "direct", "local_enabled": True, "online_enabled": False}]


def test_allow_uses_exact_bindings_and_continues_without_extra_provider_calls() -> None:
    demands = _demands(
        _demand("local"),
        _demand(
            "online",
            role="main_engineering",
            autonomy="L3_HISTORICAL",
            context="nexus_bounded",
        ),
    )
    loader = _Loader()
    calls = {"online": 0, "verifier": 0, "learning": 0}

    def online(context):
        calls["online"] += 1
        return _online(context)

    def verifier(context):
        calls["verifier"] += 1
        return _verifier(context)

    def learning(context):
        calls["learning"] += 1
        return _learning(context)

    planner = _Planner(demands)
    request = _request(
        {
            "recommended_flow": "direct",
            "workforce_admission_enabled": True,
            "workforce_bindings": _bindings(),
        }
    )
    receipt = UnifiedRuntime(planner=planner, workforce_policy_loader=loader).run(
        request,
        online_invoker=online,
        verifier=verifier,
        learning=learning,
    )

    admission = receipt["workforce_admission"]
    assert admission["overall_decision"] == "ALLOW"
    assert receipt["plan_payload"]["workforce_admission"]["aggregate_binding_hash"] == admission["aggregate_binding_hash"]
    assert receipt["plan_payload"]["signal_snapshot"]["workforce_admission"]["aggregate_binding_hash"] == admission["aggregate_binding_hash"]
    assert receipt["stages"][1]["name"] == "workforce_admission"
    assert calls == {"online": 1, "verifier": 1, "learning": 1}
    assert loader.load_calls == 1
    assert [record["request"]["requested_worker_id"] for record in admission["records"]] == [
        "local_coder_7b",
        "codex_luna",
    ]


def test_block_stops_before_all_downstream_invocations_and_preserves_planner_authority(tmp_path: Path) -> None:
    planner = _Planner(
        _demands(_demand("local")),
        selected=["local_model_executor", "memory"],
    )
    loader = _Loader()
    calls = {"capability": 0, "local": 0, "online": 0, "verifier": 0, "learning": 0}
    receipt_path = tmp_path / "blocked.json"

    def never(*_args, **_kwargs):
        calls["capability"] += 1
        return {"invoked": True}

    class Local:
        def handle(self, *_args, **_kwargs):
            calls["local"] += 1
            return {}

    def online(*_args, **_kwargs):
        calls["online"] += 1
        return _online({"task_id": "workforce-admission-runtime-test"})

    def verifier(*_args, **_kwargs):
        calls["verifier"] += 1
        return _verifier({"task_id": "workforce-admission-runtime-test"})

    def learning(*_args, **_kwargs):
        calls["learning"] += 1
        return _learning({"task_id": "workforce-admission-runtime-test"})

    route = {
        "recommended_flow": "hybrid",
        "workforce_admission_enabled": True,
        "workforce_bindings": {"local": {"worker_id": "local_qwen35_9b"}},
    }
    receipt = UnifiedRuntime(
        planner=planner,
        local_service=Local(),
        workforce_policy_loader=loader,
    ).run(
        _request(route, local=True, online=True),
        capability_invokers={"memory": never},
        online_invoker=online,
        verifier=verifier,
        learning=learning,
        receipt_path=receipt_path,
    )

    assert receipt["terminal_status"] == "BLOCKED"
    assert receipt["receipt_complete"] is False
    assert receipt["workforce_admission"]["overall_decision"] == "BLOCK"
    assert calls == {"capability": 0, "local": 0, "online": 0, "verifier": 0, "learning": 0}
    assert receipt["local_call_count"] == receipt["online_call_count"] == 0
    assert receipt["verifier_call_count"] == receipt["learning_call_count"] == 0
    assert receipt["selected_capabilities"] == ["local_model_executor", "memory"]
    assert receipt["public_claim_allowed"] is False
    assert "receipt_base" in receipt
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt
    assert receipt["planner_decision_id"] == receipt["plan_hash"] == receipt["planner"]["plan_hash"]


def test_escalate_stops_before_all_downstream_invocations(tmp_path: Path) -> None:
    planner = _Planner(
        _demands(
            _demand(
                "local",
                role="compact_diagnosis",
                autonomy="L0.5",
                context="nexus_full",
                mutation=False,
            )
        ),
        selected=["local_model_executor"],
    )
    loader = _Loader()
    calls = {"local": 0, "online": 0, "verifier": 0, "learning": 0}

    class Local:
        def handle(self, *_args, **_kwargs):
            calls["local"] += 1
            return {}

    def count(name, result):
        def invoke(*_args, **_kwargs):
            calls[name] += 1
            return result

        return invoke

    receipt = UnifiedRuntime(
        planner=planner,
        local_service=Local(),
        workforce_policy_loader=loader,
    ).run(
        _request(
            {
                "workforce_admission_enabled": True,
                "workforce_bindings": {
                    "local": {
                        "worker_id": "local_advisor_3b",
                        "controls": ["fixed_schema", "compact_context", "deterministic_consumer"],
                    }
                },
            },
            local=True,
            online=True,
        ),
        online_invoker=count("online", _online({"task_id": "workforce-admission-runtime-test"})),
        verifier=count("verifier", _verifier({"task_id": "workforce-admission-runtime-test"})),
        learning=count("learning", _learning({"task_id": "workforce-admission-runtime-test"})),
    )

    assert receipt["terminal_status"] == "INCOMPLETE"
    assert receipt["receipt_complete"] is False
    assert receipt["workforce_admission"]["overall_decision"] == "ESCALATE"
    assert calls == {"local": 0, "online": 0, "verifier": 0, "learning": 0}
    assert receipt["invocation_counts"] == {
        "capability": 0,
        "local": 0,
        "online": 0,
        "verifier": 0,
        "learning": 0,
    }
    assert "receipt_base" in receipt


@pytest.mark.parametrize(
    "bindings",
    [{}, {"local": {"worker_id": "local_coder_7b", "controls": "malformed"}}],
)
def test_missing_or_malformed_bindings_fail_closed(bindings: dict[str, object]) -> None:
    planner = _Planner(_demands(_demand("local")))
    loader = _Loader()
    receipt = UnifiedRuntime(planner=planner, workforce_policy_loader=loader).run(
        _request(
            {
                "workforce_admission_enabled": True,
                "workforce_bindings": bindings,
            }
        ),
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert receipt["terminal_status"] == "BLOCKED"
    assert receipt["workforce_admission"]["overall_decision"] == "BLOCK"
    assert loader.load_calls == 1


def test_injected_loader_is_freshly_loaded_for_each_enabled_run() -> None:
    loader = _Loader()
    planner = _Planner(
        _demands(
            _demand(
                "online",
                role="main_engineering",
                autonomy="L3_HISTORICAL",
                context="nexus_bounded",
            )
        )
    )
    runtime = UnifiedRuntime(planner=planner, workforce_policy_loader=loader)
    route = {
        "workforce_admission_enabled": True,
        "workforce_bindings": {"online": _bindings()["online"]},
    }
    for _ in range(2):
        receipt = runtime.run(
            _request(route),
            online_invoker=_online,
            verifier=_verifier,
            learning=_learning,
        )
        assert receipt["workforce_admission"]["overall_decision"] == "ALLOW"

    assert loader.load_calls == 2
    assert loader.admit_calls == 2


def test_admission_does_not_change_pre_admission_plan_hash_or_decision_id() -> None:
    demands = _demands(_demand("local"))
    planner = _Planner(demands)
    receipt = UnifiedRuntime(planner=planner, workforce_policy_loader=_Loader()).run(
        _request(
            {
                "workforce_admission_enabled": True,
                "workforce_bindings": {"local": _bindings()["local"]},
            }
        ),
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    pre_admission_payload = CapabilityPlan(
        schema_version="nexus_capability_plan_v1",
        selected_capabilities=[],
        required_capabilities=[],
        optional_capabilities=[],
        conditional_capabilities=[],
        pending_capabilities=[],
        forbidden_capabilities=[],
        constraints=["claim_fail_closed"],
        decision_trace=[],
        replan_trace=[],
        score=1.0,
        signal_snapshot={"workforce_demands": demands},
    ).to_dict()
    expected_hash = hashlib.sha256(
        json.dumps(pre_admission_payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    assert receipt["planner"]["plan_hash"] == expected_hash
    assert receipt["planner_decision_id"] == expected_hash
    assert receipt["plan_payload"]["plan_hash"] == expected_hash
    assert receipt["plan_payload"]["signal_snapshot"]["planner_decision_id"] == expected_hash


@pytest.mark.parametrize(
    "route, expected_error",
    [
        ({"workforce_admission_enabled": 1}, "workforce_admission_enabled_must_be_boolean"),
        ({"workforce_rebind_authorized": "true"}, "workforce_rebind_authorized_must_be_boolean"),
        ({"workforce_rebind_authorized": True}, "workforce_rebind_reason_required"),
    ],
)
def test_malformed_workforce_route_controls_fail_before_planner_policy_or_downstream(
    route: dict[str, object], expected_error: str
) -> None:
    planner = _Planner()
    loader = _Loader()
    calls = {"online": 0, "verifier": 0, "learning": 0}

    def counted(name, result):
        def invoke(*_args, **_kwargs):
            calls[name] += 1
            return result

        return invoke

    with pytest.raises(ValueError, match=expected_error):
        UnifiedRuntime(planner=planner, workforce_policy_loader=loader).run(
            _request(route),
            online_invoker=counted("online", _online({"task_id": "workforce-admission-runtime-test"})),
            verifier=counted("verifier", _verifier({"task_id": "workforce-admission-runtime-test"})),
            learning=counted("learning", _learning({"task_id": "workforce-admission-runtime-test"})),
        )

    assert planner.plans == 0
    assert loader.load_calls == 0
    assert calls == {"online": 0, "verifier": 0, "learning": 0}


def test_first_admission_stamps_json_safe_lineage_into_shared_context_and_receipt() -> None:
    demands = _demands(_demand("online", role="main_engineering", autonomy="L3_HISTORICAL"))
    planner = _Planner(demands)
    loader = _Loader()
    captured: dict[str, object] = {}

    def online(context):
        captured["online"] = context["planner"]
        return _online(context)

    def verifier(context):
        captured["verifier"] = context["planner"]
        return _verifier(context)

    receipt = UnifiedRuntime(planner=planner, workforce_policy_loader=loader).run(
        _request(
            {
                "workforce_admission_enabled": True,
                "workforce_bindings": {"online": _bindings()["online"]},
            }
        ),
        online_invoker=online,
        verifier=verifier,
        learning=_learning,
    )

    lineage = receipt["workforce_admission_lineage"]
    assert lineage["schema"] == "nexus.runtime_workforce_admission_lineage.v1"
    assert lineage["attempt_number"] == 1
    assert lineage["status"] == "FIRST_ADMISSION"
    assert lineage["source_aggregate_binding_hash"] == ""
    assert lineage["binding_changed"] is False
    assert lineage["rebind_authorized"] is False
    assert lineage["current_planner_decision_id"] == receipt["planner_decision_id"]
    assert json.loads(json.dumps(lineage)) == lineage
    assert receipt["plan_payload"]["workforce_admission_lineage"] == lineage
    assert receipt["plan_payload"]["signal_snapshot"]["workforce_admission_lineage"] == lineage
    assert receipt["stages"][1]["workforce_admission_lineage"] == lineage
    assert captured["online"]["workforce_admission_lineage"] == lineage
    assert captured["verifier"]["workforce_admission_lineage"] == lineage
    assert receipt["context_trace"]["workforce_admission_lineage"] == lineage


def _online_authority_route() -> dict[str, object]:
    return {
        "workforce_admission_enabled": True,
        "workforce_bindings": {"online": _bindings()["online"]},
    }


def _gateway_fake_codex(tmp_path: Path) -> tuple[Path, Path]:
    script = tmp_path / "fake-codex"
    call_log = tmp_path / "fake-codex-call.json"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        f"pathlib.Path({str(call_log)!r}).write_text("
        "json.dumps({'argv': sys.argv}), encoding='utf-8')\n"
        "print('gateway workforce ok')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, call_log


def _gateway_workforce_request(
    tmp_path: Path,
    *,
    route_update: dict[str, object] | None = None,
    model_name: str | None = None,
) -> UnifiedRuntimeRequest:
    script, _ = _gateway_fake_codex(tmp_path)
    route: dict[str, object] = {
        "recommended_flow": "direct",
        "workforce_admission_enabled": True,
        "workforce_bindings": {"online": _bindings()["online"]},
        "online_policy": "auto",
        "online_command": str(script),
        "workspace_root": str(tmp_path),
    }
    if route_update:
        route.update(route_update)
    return UnifiedRuntimeRequest(
        task_id="gateway-workforce-admission-test",
        workspace_revision="rev-workforce-admission",
        task_statement="run gateway workforce admission through bounded runtime-closure transport",
        task_type="runtime-closure",
        route=route,
        online_enabled=True,
        online_model_name=model_name,
    )


def test_gateway_ask_unified_derives_physical_online_binding_from_workforce_admission(
    tmp_path: Path,
) -> None:
    from nexus.services.gateway import BattlesuitGateway

    request = _gateway_workforce_request(tmp_path)
    call_log = tmp_path / "fake-codex-call.json"
    receipt = BattlesuitGateway(project_root=tmp_path).ask_unified(
        request,
        verifier=_verifier,
        learning=_learning,
    )

    authority = receipt["gateway_invocation_authority"]
    assert authority["status"] == "ALLOW"
    assert authority["gate_passed"] is True
    assert authority["resolved_provider"] == "codex"
    assert authority["resolved_model"] == "gpt-5.6-luna"
    assert authority["route_provider"] == "codex"
    assert authority["transport_provider"] == "codex"
    assert authority["invoker_provider"] == "codex"
    assert authority["online_model_name"] == "gpt-5.6-luna"
    assert receipt["online"]["status"] == "SUCCEEDED"
    assert receipt["online"]["response"]["provider_call_count"] == 1
    assert receipt["online"]["context_trace"]["gateway_invocation_authority"] == authority
    assert receipt["context_trace"]["gateway_invocation_authority"] == authority
    called = json.loads(call_log.read_text(encoding="utf-8"))
    assert called["argv"][1:4] == ["exec", "-m", "gpt-5.6-luna"]


@pytest.mark.parametrize(
    ("route_update", "model_name", "expected_reason"),
    [
        ({"provider": "grok"}, None, "online_route_provider_mismatch"),
        (
            {"online_transport_binding": {"provider": "grok"}},
            None,
            "online_transport_provider_mismatch",
        ),
        ({"online_invoker_provider": "grok"}, None, "online_invoker_provider_ambiguous"),
        ({}, "gpt-5.6-luna-tampered", "online_model_name_mismatch"),
        ({"online_transport_binding": "malformed"}, None, "online_transport_binding_missing"),
    ],
)
def test_gateway_ask_unified_mismatch_denials_never_start_physical_transport(
    tmp_path: Path,
    route_update: dict[str, object],
    model_name: str | None,
    expected_reason: str,
) -> None:
    from nexus.services.gateway import BattlesuitGateway

    request = _gateway_workforce_request(
        tmp_path,
        route_update=route_update,
        model_name=model_name,
    )
    call_log = tmp_path / "fake-codex-call.json"
    receipt = BattlesuitGateway(project_root=tmp_path).ask_unified(
        request,
        verifier=_verifier,
        learning=_learning,
    )

    assert receipt["gateway_invocation_authority"]["gate_passed"] is False
    assert receipt["online"]["status"] == "FAILED"
    assert receipt["online"]["reason"] == expected_reason
    assert receipt["online"]["invoked"] is False
    assert receipt["online"]["response"]["provider_call_count"] == 0
    assert not call_log.exists()


def test_gateway_ask_unified_missing_workforce_binding_denies_before_physical_transport(
    tmp_path: Path,
) -> None:
    from nexus.services.gateway import BattlesuitGateway

    request = _gateway_workforce_request(
        tmp_path,
        route_update={"workforce_bindings": {}},
    )
    call_log = tmp_path / "fake-codex-call.json"
    receipt = BattlesuitGateway(project_root=tmp_path).ask_unified(
        request,
        verifier=_verifier,
        learning=_learning,
    )

    assert receipt["terminal_status"] == "BLOCKED"
    assert receipt["gateway_invocation_authority"]["gate_passed"] is False
    assert receipt["online"]["invoked"] is False
    assert receipt["online"]["response"]["provider_call_count"] == 0
    assert not call_log.exists()


def _run_online_authority_case(
    route: dict[str, object],
    *,
    invoker=_online,
    model_name: str | None = None,
) -> tuple[dict[str, object], int]:
    planner = _Planner(
        _demands(_demand("online", role="main_engineering", autonomy="L3_HISTORICAL"))
    )
    request = _request(route)
    if model_name is not None:
        request = replace(request, online_model_name=model_name)
    calls = 0

    def counted(context):
        nonlocal calls
        calls += 1
        return invoker(context)

    receipt = UnifiedRuntime(planner=planner, workforce_policy_loader=_Loader()).run(
        request,
        online_invoker=counted,
        verifier=_verifier,
        learning=_learning,
    )
    return receipt, calls


def test_missing_invocation_authority_fails_online_before_callable() -> None:
    calls = 0

    def online(_context):
        nonlocal calls
        calls += 1
        return _online(_context)

    request = _request({"workforce_admission_enabled": True})
    stage = UnifiedRuntime._run_online(
        request,
        online,
        {"task_id": request.task_id, "route": dict(request.route)},
    )

    assert stage["status"] == "FAILED"
    assert stage["invoked"] is False
    assert stage["gate_passed"] is False
    assert stage["response"]["provider_call_count"] == 0
    assert stage["reason"] == "workforce_admission_missing"
    assert calls == 0


def test_non_allow_admission_fails_online_before_callable() -> None:
    route = _online_authority_route()
    route["workforce_bindings"] = {
        "online": {
            "worker_id": "not_an_admitted_worker",
            "provider": "codex",
            "model": "gpt-5.6-luna",
            "controls": [],
        }
    }
    receipt, calls = _run_online_authority_case(route)
    online = receipt["online"]
    assert online["status"] == "FAILED"
    assert online["invoked"] is False
    assert online["gate_passed"] is False
    assert online["response"]["provider_call_count"] == 0
    assert online["reason"] == "workforce_admission_overall_decision_not_allow"
    assert calls == 0


@pytest.mark.parametrize(
    ("change", "expected_reason"),
    [
        ({"provider": "grok"}, "online_route_provider_mismatch"),
        (
            {"online_transport_binding": {"provider": "grok"}},
            "online_transport_provider_mismatch",
        ),
        ({"online_invoker_provider": "grok"}, "online_invoker_provider_mismatch"),
    ],
)
def test_provider_identity_mismatch_is_zero_call(
    change: dict[str, object], expected_reason: str
) -> None:
    route = _online_authority_route()
    route.update(change)
    receipt, calls = _run_online_authority_case(route)
    assert receipt["online"]["status"] == "FAILED"
    assert receipt["online"]["reason"] == expected_reason
    assert receipt["online"]["invoked"] is False
    assert receipt["online"]["gate_passed"] is False
    assert receipt["online"]["response"]["provider_call_count"] == 0
    assert calls == 0


def test_model_mismatch_is_zero_call() -> None:
    receipt, calls = _run_online_authority_case(
        _online_authority_route(), model_name="different-model"
    )
    assert receipt["online"]["reason"] == "online_model_name_mismatch"
    assert receipt["online"]["response"]["provider_call_count"] == 0
    assert calls == 0


def test_missing_invoker_provider_identity_is_zero_call() -> None:
    route = _online_authority_route()
    route["online_invoker_provider"] = None

    def untagged(context):
        return _online(context)

    receipt, calls = _run_online_authority_case(route, invoker=untagged)
    assert receipt["online"]["reason"] == "online_invoker_provider_missing"
    assert receipt["online"]["response"]["provider_call_count"] == 0
    assert calls == 0


def test_admission_hash_mismatch_is_zero_call(monkeypatch: pytest.MonkeyPatch) -> None:
    import nexus.services.unified_runtime as unified_runtime_module

    original = unified_runtime_module.evaluate_runtime_workforce_admission

    def tampered(*args, **kwargs):
        payload = original(*args, **kwargs).to_dict()
        payload["records"][0]["binding_hash"] = "0" * 64
        return payload

    monkeypatch.setattr(
        unified_runtime_module,
        "evaluate_runtime_workforce_admission",
        tampered,
    )
    receipt, calls = _run_online_authority_case(_online_authority_route())
    assert receipt["online"]["reason"] == "workforce_admission_record_binding_hash_mismatch"
    assert receipt["online"]["response"]["provider_call_count"] == 0
    assert calls == 0


def test_admitted_online_authority_is_exact_and_receipt_bound() -> None:
    receipt, calls = _run_online_authority_case(_online_authority_route())
    authority = receipt["gateway_invocation_authority"]
    record = next(
        item for item in receipt["workforce_admission"]["records"]
        if item["demand"]["execution_channel"] == "online"
    )
    assert authority["schema"] == "nexus.gateway_invocation_authority.v1"
    assert authority["status"] == "ALLOW"
    assert authority["gate_passed"] is True
    assert authority["resolved_worker_id"] == "codex_luna"
    assert authority["resolved_provider"] == "codex"
    assert authority["resolved_model"] == "gpt-5.6-luna"
    assert authority["policy_hash"] == receipt["workforce_admission"]["policy_identity"]["policy_hash"]
    assert authority["binding_hash"] == record["binding_hash"]
    assert authority["aggregate_binding_hash"] == receipt["workforce_admission"]["aggregate_binding_hash"]
    assert receipt["plan_payload"]["signal_snapshot"]["gateway_invocation_authority"] == authority
    assert receipt["online"]["context_trace"]["gateway_invocation_authority"] == authority
    assert receipt["context_trace"]["gateway_invocation_authority"] == authority
    assert receipt["receipt_base"]["receipt_hash"] == receipt["receipt_hash"]
    assert calls == 1


def test_evidence_seal_failure_preserves_admitted_online_authority_without_invoking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nexus.services.capability_evidence_bundle as evidence_bundle_module

    monkeypatch.setattr(
        evidence_bundle_module,
        "verify_capability_evidence_bundle",
        lambda _bundle: {"ok": False, "blockers": ["forced_seal_failure"]},
    )
    planner = _Planner(
        _demands(_demand("online", role="main_engineering", autonomy="L3_HISTORICAL")),
        selected=["memory"],
    )
    loader = _Loader()
    calls = 0
    capability_calls = 0

    def counted_memory(context):
        nonlocal capability_calls
        capability_calls += 1
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["capability:memory:workforce-admission:test"],
        }

    def counted_online(context):
        nonlocal calls
        calls += 1
        return _online(context)

    receipt = UnifiedRuntime(planner=planner, workforce_policy_loader=loader).run(
        _request(_online_authority_route()),
        online_invoker=counted_online,
        capability_invokers={"memory": counted_memory},
        verifier=_verifier,
        learning=_learning,
    )

    authority = receipt["gateway_invocation_authority"]
    assert receipt["terminal_status"] == "BLOCKED"
    assert receipt["online"]["reason"] == "blocked_by_evidence_seal"
    assert receipt["online"]["invoked"] is False
    assert receipt["online"]["provider_call_count"] == 0
    assert receipt["provider_call_count"] == 0
    assert receipt["online_call_count"] == 0
    assert receipt["local_call_count"] == 0
    assert receipt["verifier_call_count"] == 0
    assert receipt["learning_call_count"] == 0
    assert capability_calls == 1
    assert receipt["capability_results"]["memory"]["invoked"] is True
    assert receipt["capability_call_count"] == 1
    assert receipt["invocation_counts"] == {
        "capability": 1,
        "local": 0,
        "online": 0,
        "verifier": 0,
        "learning": 0,
    }
    assert authority["schema"] == "nexus.gateway_invocation_authority.v1"
    assert authority["status"] == "ALLOW"
    assert authority["gate_passed"] is True
    assert receipt["workforce_admission"]["overall_decision"] == "ALLOW"
    assert receipt["workforce_admission_lineage"] == receipt["plan_payload"]["workforce_admission_lineage"]
    authority_surfaces = (
        receipt["planner"]["plan_payload"]["gateway_invocation_authority"],
        receipt["plan_payload"]["signal_snapshot"]["gateway_invocation_authority"],
        receipt["online"]["context_trace"]["gateway_invocation_authority"],
        receipt["context_trace"]["gateway_invocation_authority"],
    )
    assert all(surface == authority for surface in authority_surfaces)
    assert calls == 0


def _replan_pair(
    *,
    route: dict[str, object],
    loader: _Loader,
    planner: _Planner,
    receipt_path: Path | None = None,
):
    runtime = UnifiedRuntime(planner=planner, workforce_policy_loader=loader)
    first = runtime.run(
        _request(route),
        online_invoker=_online,
        verifier=lambda _ctx: {
            "task_id": "workforce-admission-runtime-test",
            "status": "FAILED",
            "invoked": True,
            "gate_passed": False,
            "evidence": "replan required",
            "evidence_refs": ["verifier:replan-required"],
        },
        learning=_learning,
        receipt_path=receipt_path,
    )
    return runtime, first


def test_unchanged_binding_replan_freshly_loads_policy_and_runs_second_attempt() -> None:
    route = {
        "workforce_admission_enabled": True,
        "workforce_bindings": {"online": _bindings()["online"]},
    }
    loader = _Loader()
    planner = _Planner(_demands(_demand("online", role="main_engineering", autonomy="L3_HISTORICAL")))
    runtime, first = _replan_pair(route=route, loader=loader, planner=planner)
    calls = {"online": 0, "verifier": 0, "learning": 0}

    def counted(name, result):
        def invoke(context):
            calls[name] += 1
            return result(context) if callable(result) else result

        return invoke

    second = runtime.run_replan(
        first,
        _request(route),
        online_invoker=counted("online", _online),
        verifier=counted("verifier", _verifier),
        learning=counted("learning", _learning),
    )

    lineage = second["workforce_admission_lineage"]
    assert lineage["status"] == "UNCHANGED"
    assert lineage["source_aggregate_binding_hash"] == first["workforce_admission"]["aggregate_binding_hash"]
    assert lineage["current_aggregate_binding_hash"] == second["workforce_admission"]["aggregate_binding_hash"]
    assert lineage["binding_changed"] is False
    assert second["terminal_status"] == "SUCCEEDED"
    assert calls == {"online": 1, "verifier": 1, "learning": 1}
    assert loader.load_calls == 2
    assert second["execution_attempt"]["attempt_number"] == 2


def test_admission_can_be_enabled_on_replan_from_legacy_receipt() -> None:
    legacy_route = {"recommended_flow": "direct"}
    admitted_route = {
        "workforce_admission_enabled": True,
        "workforce_bindings": {"online": _bindings()["online"]},
    }
    loader = _Loader()
    planner = _Planner(_demands(_demand("online", role="main_engineering", autonomy="L3_HISTORICAL")))
    runtime = UnifiedRuntime(planner=planner, workforce_policy_loader=loader)
    first = runtime.run(
        _request(legacy_route),
        online_invoker=_online,
        verifier=lambda _ctx: {
            "task_id": "workforce-admission-runtime-test",
            "status": "FAILED",
            "invoked": True,
            "gate_passed": False,
            "evidence": "enable admission on replan",
            "evidence_refs": ["verifier:enable-admission"],
        },
        learning=_learning,
    )

    second = runtime.run_replan(
        first,
        _request(admitted_route),
        online_invoker=_online,
        verifier=_verifier,
        learning=_learning,
    )

    assert "workforce_admission" not in first
    assert second["workforce_admission_lineage"]["status"] == "ENABLED_ON_REPLAN"
    assert second["workforce_admission_lineage"]["source_aggregate_binding_hash"] == ""
    assert second["terminal_status"] == "SUCCEEDED"
    assert loader.load_calls == 1


@pytest.mark.parametrize("disabled_value", [False, None])
def test_prior_admission_cannot_be_disabled_or_omitted_before_second_planner(
    disabled_value: bool | None,
) -> None:
    route = {
        "workforce_admission_enabled": True,
        "workforce_bindings": {"online": _bindings()["online"]},
    }
    loader = _Loader()
    planner = _Planner(_demands(_demand("online", role="main_engineering", autonomy="L3_HISTORICAL")))
    runtime, first = _replan_pair(route=route, loader=loader, planner=planner)
    downgraded = dict(route)
    if disabled_value is None:
        downgraded.pop("workforce_admission_enabled")
    else:
        downgraded["workforce_admission_enabled"] = disabled_value

    with pytest.raises(ValueError, match="replan_workforce_admission_required"):
        runtime.run_replan(
            first,
            _request(downgraded),
            online_invoker=_online,
            verifier=_verifier,
            learning=_learning,
        )

    assert planner.plans == 1
    assert loader.load_calls == 1


def test_changed_binding_without_authorization_blocks_after_admission_with_zero_second_attempt_calls() -> None:
    first_binding = _bindings()["local"]
    changed_binding = {
        "worker_id": "local_qwen3_8b",
        "provider": "ollama",
        "model": "qwen3:8b",
        "controls": ["bounded_context", "parser", "focused_tests", "external_verifier"],
    }
    route = {
        "workforce_admission_enabled": True,
        "workforce_bindings": {"local": first_binding},
    }
    loader = _Loader()
    planner = _Planner(_demands(_demand("local", mutation=False)))
    runtime, first = _replan_pair(route=route, loader=loader, planner=planner)
    changed_route = dict(route)
    changed_route["workforce_bindings"] = {"local": changed_binding}
    calls = {"online": 0, "verifier": 0, "learning": 0}

    def counted(name, result):
        def invoke(*_args, **_kwargs):
            calls[name] += 1
            return result

        return invoke

    second = runtime.run_replan(
        first,
        _request(changed_route),
        online_invoker=counted("online", _online({"task_id": "workforce-admission-runtime-test"})),
        verifier=counted("verifier", _verifier({"task_id": "workforce-admission-runtime-test"})),
        learning=counted("learning", _learning({"task_id": "workforce-admission-runtime-test"})),
    )

    workforce_stage = next(stage for stage in second["stages"] if stage["name"] == "workforce_admission")
    assert second["terminal_status"] == "BLOCKED"
    assert second["receipt_complete"] is False
    assert workforce_stage["status"] == "BLOCKED"
    assert workforce_stage["gate_passed"] is False
    assert workforce_stage["decision"] == "BLOCK"
    assert workforce_stage["reason"] == "workforce_rebind_not_authorized"
    assert workforce_stage["effective_decision"] == "BLOCK"
    assert workforce_stage["effective_reason"] == "workforce_rebind_not_authorized"
    assert workforce_stage["result"]["overall_decision"] == "ALLOW"
    assert second["workforce_admission"]["overall_decision"] == "ALLOW"
    assert second["workforce_admission_lineage"]["status"] == "BLOCKED_REBIND"
    assert second["workforce_admission_lineage"]["binding_changed"] is True
    assert "runtime:workforce_rebind:BLOCKED_REBIND:not_authorized" in second["evidence_refs"]
    assert calls == {"online": 0, "verifier": 0, "learning": 0}
    assert second["local"]["reason"] == "blocked_by_workforce_rebind"
    assert all(
        not (stage["name"] == "workforce_admission" and stage.get("gate_passed"))
        for stage in second["stages"]
    )


def test_authorized_changed_binding_continues_as_rebound_and_preserves_source_receipt(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "attempt-1.json"
    second_path = tmp_path / "attempt-2.json"
    route = {
        "workforce_admission_enabled": True,
        "workforce_bindings": _bindings(),
    }
    loader = _Loader()
    planner = _Planner(
        _demands(
            _demand("local", mutation=False),
            _demand(
                "online",
                role="main_engineering",
                autonomy="L3_HISTORICAL",
                mutation=False,
            ),
        )
    )
    runtime, first = _replan_pair(
        route=route,
        loader=loader,
        planner=planner,
        receipt_path=first_path,
    )
    source_bytes = first_path.read_bytes()
    changed_route = dict(route)
    changed_route.update(
        {
            "workforce_rebind_authorized": True,
            "workforce_rebind_reason": "approved worker rotation",
            "workforce_bindings": {
                "local": {
                    "worker_id": "local_qwen3_8b",
                    "provider": "ollama",
                    "model": "qwen3:8b",
                    "controls": [
                        "bounded_context",
                        "parser",
                        "focused_tests",
                        "external_verifier",
                    ],
                },
                "online": _bindings()["online"],
            },
        }
    )
    captured: dict[str, object] = {}

    def online(context):
        captured["online"] = context["planner"]["workforce_admission_lineage"]
        return _online(context)

    second = runtime.run_replan(
        first,
        _request(changed_route),
        online_invoker=online,
        verifier=lambda context: _verifier(context),
        learning=_learning,
        receipt_path=second_path,
    )

    lineage = second["workforce_admission_lineage"]
    assert second["terminal_status"] == "SUCCEEDED"
    assert lineage["status"] == "REBOUND"
    assert lineage["rebind_authorized"] is True
    assert lineage["rebind_reason"] == "approved worker rotation"
    assert lineage["source_receipt_hash"] == first["receipt_hash"]
    assert lineage["source_run_anchor_hash"] == first["run_anchor_hash"]
    assert lineage["source_replan_request_id"] == first["execution_replan_request"]["replan_request_id"]
    assert lineage["current_planner_decision_id"] == second["planner_decision_id"]
    assert captured["online"] == lineage
    assert second["context_trace"]["workforce_admission_lineage"] == lineage
    assert json.loads(second_path.read_text(encoding="utf-8"))["workforce_admission_lineage"] == lineage
    assert source_bytes == first_path.read_bytes()
    assert second["planner"]["plan_hash"] == second["planner_decision_id"]
    assert second["plan_payload"]["plan_hash"] == second["planner_decision_id"]
