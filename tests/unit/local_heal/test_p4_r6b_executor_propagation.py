"""P4-R6b: Executor P4 result propagation test."""
from __future__ import annotations

import os
import hashlib
import pytest

from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)


@pytest.fixture(autouse=True)
def _setup_env():
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    yield
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def test_p4_r6b_executor_propagates_all_fields_with_stateful_provider():
    """P4-R6b: Executor P4 path propagates all receipt fields into raw_meta.

    Stateful fake provider:
      - call 1 (main model generation) → empty output → stage4 retry fails
      - call 2+ (P4 default committee producer) → valid unified diff

    Asserts every P4 field is populated (not None) in raw_meta.
    """
    call_count = [0]

    class StatefulFakeProvider:
        def generate(self, req):
            call_count[0] += 1
            if call_count[0] == 1:
                output = ""
            else:
                output = (
                    "--- a/foo.py\n"
                    "+++ b/foo.py\n"
                    "@@ -1,3 +1,3 @@\n"
                    " def foo():\n"
                    "-    pass\n"
                    "+    return 42\n"
                )

            class R:
                pass
            r = R()
            r.output_text = output
            r.output_truncated = False
            r.error = ""
            r.timed_out = False
            r.requested_timeout_sec = 120.0
            r.effective_timeout_sec = 120.0
            r.elapsed_sec = 0.1
            r.provider_invoked = True
            r.model_called = True
            r.model_name = "test-model"
            return r

    signal_snapshot = {
        "execution_topology": "cloud_with_local_assist",
        "protocol_mode": "anchored_edit",
        "model_call_allowed": True,
        "executor_model": "test-model",
        "executor_provider": "ollama",
        "target_symbol": "eval",
        "difficulty": "hard",
        "task_difficulty": "hard",
        "proposer_specs": [
            {"model": "a", "role": "primary"},
            {"model": "b", "role": "secondary"},
        ],
        "judge_model": "judge",
        "mutation_allowed": True,
        "verifier_allowed": True,
    }

    req = LocalModelExecutorRequest(
        task_id="p4-r6b-propagation",
        problem_statement="Fix the function",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": signal_snapshot},
        dry_run=False,
        mutation_allowed=True,
        verifier_allowed=True,
    )

    resp = LocalModelExecutor.run(req, provider=StatefulFakeProvider())
    meta = resp.raw_model_metadata

    # --- P4 was invoked ---
    assert meta.get("p4_committee_gate_evaluated") is True
    assert meta.get("p4_committee_invocation_allowed") is True
    assert meta.get("p4_committee_invoked") is True

    # --- Producer invoked and produced a candidate ---
    assert meta.get("p4_candidate_producer_present") is True
    assert meta.get("p4_candidate_producer_invoked") is True
    assert meta.get("p4_candidate_producer_name", "") != ""
    assert meta.get("p4_raw_candidate_count", 0) > 0

    # --- All P4 receipt fields populated, None forbidden ---
    required_fields = [
        "p4_committee_candidate_count",
        "p4_canonical_candidate_count",
        "p4_winner_found",
        "p4_selected_candidate_hash",
        "p4_selected_candidate_model",
        "p4_selected_candidate_apply_status",
        "p4_selected_candidate_verifier_status",
        "p4_selected_candidate_hash_matches_applied",
        "p4_committee_claim_gate_passed",
        "p4_solved_by_committee",
        "p4_fail_closed",
    ]
    for field in required_fields:
        assert field in meta, f"Missing P4 field in raw_meta: {field}"
        assert meta[field] is not None, f"P4 field is None in raw_meta: {field}"

    # --- Fail-closed by verifier (diff written to .py → syntax error) ---
    assert meta["p4_solved_by_committee"] is False
    assert meta["p4_fail_closed"] is True

    # Provider was called at least twice (stage4 + P4 producer)
    assert call_count[0] >= 2

    # --- P3 stages activated trace ---
    stages = meta.get("assist_stages_activated", [])
    assert "stage1_local_diagnosis" in stages
    assert "stage2_cloud_candidate" in stages
    assert "stage3_local_cheap_verifier" in stages
    assert "stage4_local_retry" in stages
    assert "stage5_escalation_stub" in stages
    assert "committee_routed_tool" in stages

    # --- Stage4 retry failed (empty provider output) ---
    assert meta.get("stage4_local_retry_success") is False
    assert meta.get("stage5_escalation_recommended") is True
