from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

import pytest

from scripts.bench.capability_ab_runner import write_evidence_bundle, write_jsonl
from scripts.bench.evidence_bundle_fidelity import extract_telemetry_fidelity_snapshot


VOLATILE_KEY_MARKERS = (
    "created_at",
    "timestamp",
    "trace_id",
    "updated_at",
    "uuid",
    "run_id",
)
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NestedCanonicalComparator:
    rel_tol: float = 1e-5
    abs_tol: float = 1e-5

    def assert_equal(self, left: Any, right: Any) -> None:
        self._compare(self._canonicalize(left), self._canonicalize(right), "$")

    def _canonicalize(self, value: Any, key: str = "") -> Any:
        if key and any(marker in key.lower() for marker in VOLATILE_KEY_MARKERS):
            return "<VOLATILE>"
        if isinstance(value, dict):
            return {
                item_key: self._canonicalize(item_value, item_key)
                for item_key, item_value in sorted(value.items())
            }
        if isinstance(value, list):
            items = [self._canonicalize(item, key) for item in value]
            if all(self._is_sortable_item(item) for item in items):
                return sorted(items, key=self._stable_sort_key)
            return items
        if isinstance(value, str):
            normalized = value.replace("\r\n", "\n")
            if UUID_RE.match(normalized):
                return "<VOLATILE>"
            return normalized
        return value

    def _compare(self, left: Any, right: Any, path: str) -> None:
        if self._is_number(left) and self._is_number(right):
            assert math.isclose(
                float(left),
                float(right),
                rel_tol=self.rel_tol,
                abs_tol=self.abs_tol,
            ), f"{path}: {left!r} != {right!r}"
            return
        assert type(left) is type(right), f"{path}: type {type(left).__name__} != {type(right).__name__}"
        if isinstance(left, dict):
            assert left.keys() == right.keys(), f"{path}: keys {left.keys()} != {right.keys()}"
            for key in left:
                self._compare(left[key], right[key], f"{path}.{key}")
            return
        if isinstance(left, list):
            assert len(left) == len(right), f"{path}: list length {len(left)} != {len(right)}"
            for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
                self._compare(left_item, right_item, f"{path}[{index}]")
            return
        assert left == right, f"{path}: {left!r} != {right!r}"

    def _stable_sort_key(self, value: Any) -> str:
        if isinstance(value, dict):
            for key in ("task_id", "id", "name", "path"):
                if key in value:
                    return f"{key}:{value[key]}"
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)

    def _is_sortable_item(self, value: Any) -> bool:
        return isinstance(value, (str, int, float, dict)) and not isinstance(value, bool)

    def _is_number(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)


def test_nested_canonical_comparator_accepts_order_and_volatile_drift():
    before = {
        "run_id": "8e573cf8-87af-4ea7-bf31-b03bebdc10e4",
        "timestamp": "2026-05-22T00:00:00Z",
        "loaded_paths": ["b.json", "a.json"],
        "scores": [0.2, 0.1],
        "rows": [
            {"task_id": "task_b", "wall_sec": 1.000001, "tokens": 2},
            {"task_id": "task_a", "wall_sec": 0.500001, "tokens": 1},
        ],
        "stderr": "line one\r\nline two\r\n",
    }
    after = {
        "run_id": "ed348c13-cc12-493e-98fc-4ec4d5a42e99",
        "timestamp": "2026-05-22T01:00:00Z",
        "loaded_paths": ["a.json", "b.json"],
        "scores": [0.1, 0.2],
        "rows": [
            {"task_id": "task_a", "wall_sec": 0.5, "tokens": 1},
            {"task_id": "task_b", "wall_sec": 1.0, "tokens": 2},
        ],
        "stderr": "line one\nline two\n",
    }

    NestedCanonicalComparator().assert_equal(before, after)


def test_nested_canonical_comparator_rejects_float_drift_outside_tolerance():
    with pytest.raises(AssertionError, match="wall_sec"):
        NestedCanonicalComparator().assert_equal(
            {"row": {"wall_sec": 1.0}},
            {"row": {"wall_sec": 1.001}},
        )


def test_nested_canonical_comparator_rejects_semantic_list_drift():
    with pytest.raises(AssertionError):
        NestedCanonicalComparator().assert_equal(
            {"loaded_paths": ["a.json", "b.json"]},
            {"loaded_paths": ["a.json", "c.json"]},
        )


def _route_policy(reason_codes: list[str] | None = None) -> dict[str, object]:
    return {
        "reason_codes": list(reason_codes or []),
        "pre_model_deterministic_rescue_allowed": False,
    }


def test_public_benchmark_telemetry_snapshot_is_stable_for_fixed_mock_rows(tmp_path):
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/telemetry",
        "trial_index": 1,
        "task_type": "public_test_repair",
        "expected_capabilities": ["ddtree"],
        "status": "SUCCESS",
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "token_measured": True,
        "provider_token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "total_tokens": 90,
        "model_calls": 1,
        "wall_duration_sec": 9.0,
        "gateway_total_sec": 8.0,
        "hidden_verifier_wall_sec": 1.0,
        "hidden_verifier_passed": True,
        "hidden_verifier_file": "hidden_test.py",
        "gateway_stats_present": True,
        "prompt_system_instruction_chars": 50,
        "prompt_task_constraint_chars": 20,
        "prompt_source_payload_chars": 30,
        "prompt_test_payload_chars": 40,
        "prompt_candidate_payload_chars": 10,
        "prompt_nexus_control_chars": 0,
        "prompt_governance_contract_chars": 0,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
        "route_execution_policy": _route_policy(),
        "capability_receipts": [
            {
                "name": "ddtree",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "public_claim_safe": True,
                "evidence_refs": ["saved_steps:2"],
            }
        ],
        "expected_capability_receipt_coverage": {
            "expected": ["ddtree"],
            "missing": [],
            "all_public_safe": True,
        },
        "expected_capability_invocation_coverage": {
            "expected": ["ddtree"],
            "missing": [],
            "all_invoked_with_evidence": True,
        },
        "rubric_contract_status": "PASS",
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/telemetry",
        "trial_index": 1,
        "task_type": "public_test_repair",
        "status": "SUCCESS",
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "token_measured": True,
        "provider_token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "total_tokens": 100,
        "model_calls": 1,
        "wall_duration_sec": 10.0,
        "gateway_total_sec": 10.0,
        "gateway_stats_present": True,
    }
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))

    NestedCanonicalComparator().assert_equal(
        extract_telemetry_fidelity_snapshot(payload),
        {
            "schema": "nexus_telemetry_fidelity_snapshot_v1",
            "telemetry_completeness": {
                "token_measured_rate_without": 1.0,
                "token_measured_rate_with": 1.0,
                "provider_token_measured_rate_without": 1.0,
                "provider_token_measured_rate_with": 1.0,
                "gateway_stats_source_rate_without": 1.0,
                "gateway_stats_source_rate_with": 1.0,
            },
            "nexus_wearing": {
                "valid_rate": 1.0,
                "gemini_uses_nexus_rate": 1.0,
                "model_uses_nexus_rate": 1.0,
                "nexus_context_delivered_rate": 1.0,
                "nexus_usage_valid_rate": 1.0,
                "claim_verified_rate": 1.0,
            },
            "public_gate_checks": {
                "hidden_verifier_mode": True,
                "nexus_wearing_valid_rate": 1.0,
                "model_uses_nexus_rate": 1.0,
                "nexus_context_delivered_rate": 1.0,
                "nexus_usage_valid_rate": 1.0,
                "claim_verified_rate": 1.0,
                "route_decision_present_rate": 1.0,
                "provider_token_measured_rate_with": 1.0,
                "provider_token_measured_rate_without": 1.0,
                "wall_cost_ratio_with_over_without": 0.9,
                "token_cost_ratio_with_over_without": 0.9,
                "model_call_ratio_with_over_without": 1.0,
            },
            "wall_ledger_conservation": {
                "telemetry_invalid": False,
                "with_conserved_rate": 1.0,
                "without_conserved_rate": 1.0,
                "with_reason_codes": [],
                "without_reason_codes": [],
            },
            "posture": {
                "public_claim_gate": "PASS",
                "public_verified_delivery_claim_gate": "PASS",
                "public_cost_claim_gate": "PASS",
                "public_cost_efficiency_claim_gate": "IMPROVED",
                "valid_comparison_readiness_gate": "PASS",
                "public_claim_posture_key": "promising_but_insufficient_sample",
                "training_eligibility_status": "OBSERVATION_ONLY_SAMPLE_INSUFFICIENT",
            },
        },
    )
