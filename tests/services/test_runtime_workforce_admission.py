from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from nexus.contracts.workforce_admission import AdmissionDecision, WorkforceAdmissionDecision
from nexus.services.model_workforce_policy import WorkforcePolicyLoader
from nexus.services.runtime_workforce_admission import (
    RuntimeWorkforceAdmissionResult,
    _decision_dict,
    evaluate_runtime_workforce_admission,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "nexus/config/model_workforce.yaml"


def demand(
    demand_id: str = "d1",
    *,
    channel: str = "local",
    role: str = "bounded_code_candidate",
    autonomy: str = "L1",
    context: str = "nexus_bounded",
    mutation: bool = True,
) -> dict[str, object]:
    return {
        "schema": "nexus.workforce_demand.v1",
        "demand_id": demand_id,
        "execution_channel": channel,
        "requested_role": role,
        "minimum_autonomy": autonomy,
        "context_class": context,
        "mutation_intent": mutation,
        "external_verification_required": True,
        "route_authority": "CapabilityPlanner",
    }


def demands(*items: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "nexus.workforce_demands.v1",
        "route_authority": "CapabilityPlanner",
        "demands": list(items),
    }


def evaluate(raw: dict[str, object], bindings: dict[str, object]):
    return evaluate_runtime_workforce_admission(raw, bindings, WorkforcePolicyLoader(POLICY))


class CountingLoader:
    def __init__(self, *, load_error: Exception | None = None, admit_error: Exception | None = None):
        self.real = WorkforcePolicyLoader(POLICY)
        self.load_error = load_error
        self.admit_error = admit_error
        self.load_calls = 0
        self.admit_calls: list[object] = []
        self.snapshot = None

    def load(self):
        self.load_calls += 1
        if self.load_error:
            raise self.load_error
        self.snapshot = self.real.load()
        return self.snapshot

    def admit(self, request, snapshot) -> WorkforceAdmissionDecision | dict[str, object]:
        self.admit_calls.append((request, snapshot))
        if self.admit_error:
            raise self.admit_error
        return self.real.admit(request, snapshot)


def test_local_coder_7b_allows_with_required_controls():
    result = evaluate(
        demands(demand()),
        {
            "local": {
                "worker_id": "local_coder_7b",
                "provider": "ollama",
                "model": "qwen2.5-coder:7b-instruct",
                "controls": ["focused_tests", "compile", "parser", "small_scope", "reversible_application"],
            }
        },
    )

    assert result.overall_decision == AdmissionDecision.ALLOW
    assert result.records[0].decision["decision"] == "ALLOW"
    assert result.records[0].decision["missing_controls"] == []


def test_local_qwen35_9b_blocks():
    result = evaluate(
        demands(demand(role="bounded_second_opinion", autonomy="L0")),
        {"local": {"worker_id": "local_qwen35_9b"}},
    )
    assert result.overall_decision == AdmissionDecision.BLOCK
    assert result.records[0].decision["decision"] == "BLOCK"


def test_local_advisor_nexus_full_escalates():
    result = evaluate(
        demands(
            demand(
                role="compact_diagnosis",
                autonomy="L0.5",
                context="nexus_full",
                mutation=False,
            )
        ),
        {
            "local": {
                "requested_worker_id": "local_advisor_3b",
                "controls": ["fixed_schema", "compact_context", "deterministic_consumer"],
            }
        },
    )
    assert result.overall_decision == AdmissionDecision.ESCALATE
    assert result.records[0].decision["decision"] == "ESCALATE"


def test_online_codex_luna_allows_main_engineering_historical_bounded():
    result = evaluate(
        demands(
            demand(
                channel="online",
                role="main_engineering",
                autonomy="L3_HISTORICAL",
                context="nexus_bounded",
            )
        ),
        {
            "online": {
                "worker_id": "codex_luna",
                "provider": "codex",
                "model": "gpt-5.6-luna",
                "provided_controls": ["receipt", "independent_verification", "governed_adapter"],
            }
        },
    )
    assert result.overall_decision == AdmissionDecision.ALLOW
    assert result.records[0].decision["admitted_role"] == "main_engineering"


def test_missing_binding_and_missing_identity_are_synthetic_blocks_without_admit():
    loader = CountingLoader()
    raw = demands(demand("missing"), demand("empty", channel="online"))
    result = evaluate_runtime_workforce_admission(
        raw,
        {"online": {"controls": ["anything"]}},
        loader,
    )

    assert loader.load_calls == 1
    assert loader.admit_calls == []
    assert result.overall_decision == AdmissionDecision.BLOCK
    assert len(result.records) == 2
    assert all(record.decision["decision"] == "BLOCK" for record in result.records)


def test_malformed_binding_is_explicit_block_without_admit():
    loader = CountingLoader()
    result = evaluate_runtime_workforce_admission(
        demands(demand()),
        {"local": {"worker_id": "local_coder_7b", "controls": "not-a-list"}},
        loader,
    )
    assert loader.load_calls == 1
    assert loader.admit_calls == []
    assert result.overall_decision == AdmissionDecision.BLOCK
    assert "malformed" not in result.overall_reasons[0].lower()
    assert "controls" in result.overall_reasons[0]


def test_malformed_demands_block_without_loading_or_admitting():
    loader = CountingLoader()
    result = evaluate_runtime_workforce_admission(
        demands({**demand(), "execution_channel": "gpu"}),
        {"gpu": {"worker_id": "local_coder_7b"}},
        loader,
    )
    assert loader.load_calls == 0
    assert loader.admit_calls == []
    assert result.overall_decision == AdmissionDecision.BLOCK
    assert result.records == ()
    assert "Demand parsing failed" in result.overall_reasons[0]


def test_loader_exception_is_explicit_block_and_never_raises():
    loader = CountingLoader(load_error=RuntimeError("fresh policy unavailable"))
    result = evaluate_runtime_workforce_admission(
        demands(demand()),
        {"local": {"worker_id": "local_coder_7b"}},
        loader,
    )
    assert loader.load_calls == 1
    assert loader.admit_calls == []
    assert result.overall_decision == AdmissionDecision.BLOCK
    assert "Policy load failed" in result.overall_reasons[0]


def test_admit_exception_is_explicit_block_and_never_raises():
    loader = CountingLoader(admit_error=RuntimeError("admit exploded"))
    result = evaluate_runtime_workforce_admission(
        demands(demand()),
        {"local": {"worker_id": "local_coder_7b"}},
        loader,
    )
    assert loader.load_calls == 1
    assert len(loader.admit_calls) == 1
    assert result.overall_decision == AdmissionDecision.BLOCK
    assert "Admission failed" in result.records[0].decision["decision_reasons"][0]


def test_hybrid_block_precedence_retains_all_records():
    result = evaluate(
        demands(
            demand("local", channel="local"),
            demand("online", channel="online", role="main_engineering", autonomy="L3_HISTORICAL"),
        ),
        {
            "local": {"worker_id": "local_qwen35_9b"},
            "online": {"worker_id": "codex_luna", "controls": ["governed_adapter", "independent_verification", "receipt"]},
        },
    )
    assert result.overall_decision == AdmissionDecision.BLOCK
    assert [record.demand["demand_id"] for record in result.records] == ["local", "online"]
    assert [record.decision["decision"] for record in result.records] == ["BLOCK", "ALLOW"]


def test_exact_binding_identity_is_passed_without_substitution():
    loader = CountingLoader()
    result = evaluate_runtime_workforce_admission(
        demands(demand()),
        {"local": {"worker_id": "local_coder_7b", "provider": "not-ollama", "model": "not-the-model"}},
        loader,
    )
    request, _snapshot = loader.admit_calls[0]
    assert request.requested_worker_id == "local_coder_7b"
    assert request.provider == "not-ollama"
    assert request.model == "not-the-model"
    assert result.records[0].request["provider"] == "not-ollama"
    assert result.records[0].request["model"] == "not-the-model"
    assert result.overall_decision == AdmissionDecision.BLOCK


def test_result_is_frozen_and_json_safe():
    result = evaluate(
        demands(demand()),
        {"local": {"worker_id": "local_coder_7b", "controls": ["small_scope", "parser", "compile", "focused_tests", "reversible_application"]}},
    )
    assert isinstance(result, RuntimeWorkforceAdmissionResult)
    with pytest.raises(AttributeError):
        result.schema = "changed"  # type: ignore[misc]
    assert json.loads(json.dumps(result.to_dict()))["schema"] == "nexus.runtime_workforce_admission.v1"
    assert result.to_dict()["records"][0]["schema"] == "nexus.runtime_workforce_admission_record.v1"


def test_hash_is_deterministic_across_mapping_and_control_order():
    raw = demands(demand())
    first = evaluate(raw, {"local": {"worker_id": "local_coder_7b", "controls": ["parser", "compile", "small_scope", "focused_tests", "reversible_application"]}})
    second = evaluate(raw, {"local": {"controls": ["reversible_application", "focused_tests", "small_scope", "compile", "parser"], "worker_id": "local_coder_7b"}})
    assert first.records[0].binding_hash == second.records[0].binding_hash
    assert first.aggregate_binding_hash == second.aggregate_binding_hash


class DecisionLoader(CountingLoader):
    def __init__(self, decision: WorkforceAdmissionDecision, *, policy_hash: str | None = None):
        super().__init__()
        self.fixed_decision = decision
        self.policy_hash = policy_hash

    def load(self):
        snapshot = super().load()
        if self.policy_hash is not None:
            snapshot = replace(snapshot, policy_hash=self.policy_hash)
            self.snapshot = snapshot
        return snapshot

    def admit(self, request, snapshot):
        self.admit_calls.append((request, snapshot))
        return self.fixed_decision


def decision(**changes) -> WorkforceAdmissionDecision:
    values = {
        "decision": AdmissionDecision.ALLOW,
        "resolved_worker_id": "local_coder_7b",
        "resolved_provider": "ollama",
        "resolved_model": "qwen2.5-coder:7b-instruct",
        "requested_role": "bounded_code_candidate",
        "admitted_role": "bounded_code_candidate",
        "requested_autonomy": "L1",
        "admitted_autonomy": "L1",
        "requested_context": "nexus_bounded",
        "admitted_context": "nexus_bounded",
        "required_controls": ("compile",),
        "missing_controls": (),
        "route_authority": "CapabilityPlanner",
        "decision_reasons": ("ok",),
    }
    values.update(changes)
    return WorkforceAdmissionDecision(**values)


@pytest.mark.parametrize(
    "change",
    [
        {"policy_hash": "different-policy"},
        {"resolved_worker_id": "other-worker"},
        {"admitted_role": "other-role"},
        {"admitted_context": "nexus_full"},
        {"required_controls": ("different-control",)},
        {"missing_controls": ("missing-control",)},
    ],
)
def test_each_binding_identity_or_admission_field_changes_hash(change):
    base = DecisionLoader(decision())
    changed = DecisionLoader(
        decision(**{key: value for key, value in change.items() if key != "policy_hash"}),
        policy_hash=change.get("policy_hash"),
    )
    raw = demands(demand())
    bindings = {"local": {"worker_id": "local_coder_7b"}}
    first = evaluate_runtime_workforce_admission(raw, bindings, base)
    second = evaluate_runtime_workforce_admission(raw, bindings, changed)
    assert first.records[0].binding_hash != second.records[0].binding_hash


def test_demand_id_and_requested_identity_change_hash():
    loader1 = DecisionLoader(decision())
    loader2 = DecisionLoader(decision())
    first = evaluate_runtime_workforce_admission(
        demands(demand("one")),
        {"local": {"worker_id": "local_coder_7b"}},
        loader1,
    )
    second = evaluate_runtime_workforce_admission(
        demands(demand("two")),
        {"local": {"worker_id": "other-worker"}},
        loader2,
    )
    assert first.records[0].binding_hash != second.records[0].binding_hash


def test_decision_dict_rejects_forged_raw_mapping_values_fail_closed():
    forged = [
        "FORGED",
        "allow",
        "",
        None,
        0,
        True,
        [],
        {"decision": "ALLOW"},
    ]
    for value in forged:
        with pytest.raises(ValueError, match="invalid decision value"):
            _decision_dict({"decision": value})


def test_decision_dict_accepts_only_canonical_decision_values():
    for member in (AdmissionDecision.ALLOW, AdmissionDecision.BLOCK, AdmissionDecision.ESCALATE):
        result = _decision_dict({"decision": member.value})
        assert result["decision"] == member.value
    enum_result = _decision_dict({"decision": AdmissionDecision.ESCALATE})
    assert enum_result["decision"] == "ESCALATE"


class ForgedDecisionLoader(CountingLoader):
    def __init__(self, decision_value: object):
        super().__init__()
        self.decision_value = decision_value

    def admit(self, request, snapshot) -> dict[str, object]:
        self.admit_calls.append((request, snapshot))
        return {"decision": self.decision_value, "resolved_worker_id": "forged"}


@pytest.mark.parametrize(
    "forged_value",
    [
        "FORGED",
        "allow",
        None,
        0,
        {"nested": "object"},
    ],
)
def test_forged_raw_mapping_decision_is_synthetic_block_and_never_raises(forged_value):
    loader = ForgedDecisionLoader(forged_value)
    result = evaluate_runtime_workforce_admission(
        demands(demand()),
        {"local": {"worker_id": "local_coder_7b"}},
        loader,
    )
    assert len(loader.admit_calls) == 1
    assert result.overall_decision == AdmissionDecision.BLOCK
    assert result.records[0].decision["decision"] == "BLOCK"
    assert "Admission failed" in result.records[0].decision["decision_reasons"][0]


def test_valid_raw_mapping_decision_still_serializes_canonically():
    class RawLoader(CountingLoader):
        def admit(self, request, snapshot) -> dict[str, object]:
            self.admit_calls.append((request, snapshot))
            return {
                "decision": "ALLOW",
                "resolved_worker_id": "local_coder_7b",
                "resolved_provider": "ollama",
                "resolved_model": "qwen2.5-coder:7b-instruct",
            }

    result = evaluate_runtime_workforce_admission(
        demands(demand()),
        {"local": {"worker_id": "local_coder_7b"}},
        RawLoader(),
    )
    assert result.overall_decision == AdmissionDecision.ALLOW
    assert result.records[0].decision["decision"] == "ALLOW"
