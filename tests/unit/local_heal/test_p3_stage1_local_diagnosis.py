"""P3-I3: Stage 1 Local Diagnosis + Compact Prompt Tests."""
from __future__ import annotations

import pytest
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    _p3_stage1_local_diagnosis,
)
from nexus.services.local_heal.receipt import build_repair_receipt


def test_stage1_diagnosis_extracts_error_context():
    """P3-I3: Diagnosis extracts problem statement as error context."""
    req = LocalModelExecutorRequest(
        task_id="p3-s1-1",
        problem_statement="Fix zeta function evaluation by replacing 'a is S.One' with 'a == S.One'",
        repo_root="/tmp",
        target_file="sympy/functions/special/zeta_functions.py",
        selected_capabilities=(),
        evidence_refs=("patch.diff", "repro.log"),
        route_context={
            "signal_snapshot": {
                "target_symbol": "eval",
            }
        },
    )
    result = _p3_stage1_local_diagnosis(req)
    assert result["stage1_diagnosis_performed"] is True
    assert "zeta function" in result["stage1_error_context"].lower()
    assert result["stage1_diagnosis_model"] == "deterministic"


def test_stage1_diagnosis_compact_prompt_respects_limit():
    """P3-I3: Compact prompt is ≤500 chars."""
    long_problem = "x" * 1000
    req = LocalModelExecutorRequest(
        task_id="p3-s1-2",
        problem_statement=long_problem,
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {"target_symbol": "bar"}},
    )
    result = _p3_stage1_local_diagnosis(req)
    assert len(result["stage1_compact_prompt"]) <= 500


def test_stage1_diagnosis_includes_target_info():
    """P3-I3: Compact prompt includes file and symbol."""
    req = LocalModelExecutorRequest(
        task_id="p3-s1-3",
        problem_statement="fix bug",
        repo_root="/tmp",
        target_file="src/main.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {"target_symbol": "process"}},
    )
    result = _p3_stage1_local_diagnosis(req)
    assert "src/main.py" in result["stage1_compact_prompt"]
    assert "process" in result["stage1_compact_prompt"]


def test_executor_shadow_runs_stage1():
    """P3-I3: Executor runs stage1 diagnosis in shadow topology."""
    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = ""
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = False
                model_called = False
                model_name = ""
            return R()

    req = LocalModelExecutorRequest(
        task_id="p3-s1-4",
        problem_statement="Fix zeta function",
        repo_root="/tmp",
        target_file="zeta.py",
        selected_capabilities=(),
        evidence_refs=("patch.diff",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "cloud_with_local_assist",
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "target_symbol": "eval",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    meta = resp.raw_model_metadata
    assert meta.get("stage1_diagnosis_performed") is True
    assert meta.get("stage1_diagnosis_model") == "deterministic"
    assert "stage1_local_diagnosis" in meta.get("assist_stages_activated", [])
    assert meta.get("p3_route_status") == "shadow_stage2_complete"
    assert meta.get("local_assist_used") is True


def test_stage1_receipt_fields():
    """P3-I3: Receipt contains stage1 diagnosis fields."""
    class FakeCtx:
        instance_id = "p3-s1-5"
        stage1_diagnosis_performed = True
        stage1_diagnosis_summary = "Stage1 diagnosis: target=foo.py"
        stage1_compact_prompt = "File: foo.py | Symbol: bar"
        stage1_error_context = "fix bug in foo.py"
        stage1_diagnosis_model = "deterministic"

    receipt = build_repair_receipt(FakeCtx())
    assert receipt["stage1_diagnosis_performed"] is True
    assert receipt["stage1_diagnosis_model"] == "deterministic"
    assert "foo.py" in receipt["stage1_compact_prompt"]


def test_stage1_empty_problem_statement():
    """P3-I3: Diagnosis handles empty problem statement."""
    req = LocalModelExecutorRequest(
        task_id="p3-s1-6",
        problem_statement="",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={"signal_snapshot": {}},
    )
    result = _p3_stage1_local_diagnosis(req)
    assert result["stage1_diagnosis_performed"] is True
    assert result["stage1_error_context"] == ""
