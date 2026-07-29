from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.model_workforce_policy import WorkforcePolicyLoader
from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest


ROOT = Path(__file__).resolve().parents[2]
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
    return UnifiedRuntimeRequest(
        task_id="workforce-admission-runtime-test",
        workspace_revision="rev-workforce-admission",
        task_statement="run the bounded runtime admission seam",
        task_type="bugfix",
        route=route,
        local_enabled=local,
        online_enabled=online,
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
