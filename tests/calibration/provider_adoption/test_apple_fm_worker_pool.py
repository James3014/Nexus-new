"""Tests for the bounded experimental Apple FM worker pool."""

import json
import subprocess
import time

import pytest

from nexus.calibration.provider_adoption.apple_fm_worker_pool import (
    MAX_CONCURRENCY,
    AppleFMReadOnlyTask,
    AppleFMReadOnlyWorkerPool,
    AppleFMTaskKind,
)


def _ok_preflight():
    return False, ""


def _completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=["fm"], returncode=returncode, stdout=stdout, stderr="")


def _classification(task_id: str, prompt: str, *labels: str):
    return AppleFMReadOnlyTask(
        task_id,
        AppleFMTaskKind.CLASSIFICATION,
        prompt,
        allowed_outputs=labels or ("OK",),
    )


def _extraction(task_id: str, prompt: str, pattern: str = r"\d+"):
    return AppleFMReadOnlyTask(
        task_id,
        AppleFMTaskKind.LITERAL_EXTRACTION,
        prompt,
        output_pattern=pattern,
    )


def test_pool_defaults_to_two_and_caps_at_four():
    pool = AppleFMReadOnlyWorkerPool(environment_preflight=_ok_preflight)
    assert pool.default_concurrency == 2
    assert pool.max_concurrency == 4
    assert MAX_CONCURRENCY == 4
    with pytest.raises(ValueError):
        AppleFMReadOnlyWorkerPool(max_concurrency=5, environment_preflight=_ok_preflight)


def test_batch_rejects_known_high_risk_semantic_tag_before_execution():
    called = 0

    def runner(*args, **kwargs):
        nonlocal called
        called += 1
        return _completed("4")

    pool = AppleFMReadOnlyWorkerPool(
        command_runner=runner,
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    task = AppleFMReadOnlyTask(
        task_id="T1",
        kind=AppleFMTaskKind.LITERAL_EXTRACTION,
        prompt="Return only the retry count.",
        risk_tags=("retry_attempt_semantics",),
    )
    with pytest.raises(ValueError, match="not eligible"):
        pool.run_batch([task])
    assert called == 0


def test_batch_rejects_non_enum_task_kind_before_execution():
    called = 0

    def runner(*args, **kwargs):
        nonlocal called
        called += 1
        return _completed("OK")

    pool = AppleFMReadOnlyWorkerPool(
        command_runner=runner,
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    task = AppleFMReadOnlyTask("BAD-KIND", "classification", "Return OK")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="kind must be an AppleFMTaskKind"):
        pool.run_batch([task])
    assert called == 0


def test_batch_rejects_duplicate_ids_and_out_of_range_concurrency():
    pool = AppleFMReadOnlyWorkerPool(
        command_runner=lambda *a, **k: _completed("OK"),
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    task = _classification("same", "Return OK", "OK")
    with pytest.raises(ValueError, match="duplicate task_id"):
        pool.run_batch([task, task])
    with pytest.raises(ValueError, match="between 1 and 4"):
        pool.run_batch([task], concurrency=5)


def test_pool_runs_tasks_concurrently_preserves_input_order_and_no_fallback():
    def runner(argv, **kwargs):
        prompt = argv[-1]
        if prompt == "slow":
            time.sleep(0.03)
            return _completed("SLOW")
        if prompt == "fast":
            time.sleep(0.005)
            return _completed("FAST")
        return _completed("", returncode=64)

    pool = AppleFMReadOnlyWorkerPool(
        command_runner=runner,
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    tasks = [
        _classification("A", "slow", "SLOW"),
        _classification("B", "fast", "FAST"),
        _classification("C", "fail", "EXPECTED"),
    ]
    receipt = pool.run_batch(tasks, concurrency=2)
    assert [result.task_id for result in receipt.results] == ["A", "B", "C"]
    assert [result.output_text for result in receipt.results] == ["SLOW", "FAST", ""]
    assert receipt.contract_valid_tasks == 2
    assert receipt.contract_invalid_tasks == 1
    assert receipt.results[2].needs_escalation is True
    assert receipt.automatic_fallback == "DISABLED"
    assert receipt.claim_ceiling == "EXPERIMENT_ONLY"


def test_nonempty_wrong_classification_label_fails_output_contract():
    calls = 0

    def runner(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _completed("MADE_UP_LABEL")

    pool = AppleFMReadOnlyWorkerPool(
        command_runner=runner,
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    result = pool.run_batch([
        _classification("WRONG", "classify", "RATE_LIMIT", "AUTH_ERROR")
    ]).results[0]
    assert result.ok is False
    assert result.output_contract_valid is False
    assert result.semantic_correctness_status == "NOT_EVALUATED"
    assert result.error_code == "OUTPUT_NOT_IN_ALLOWED_SET"
    assert result.needs_escalation is True
    assert calls == 1


def test_literal_extraction_shape_mismatch_fails_output_contract():
    pool = AppleFMReadOnlyWorkerPool(
        command_runner=lambda *a, **k: _completed("status 503"),
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    result = pool.run_batch([_extraction("E1", "extract", r"\d{3}")]).results[0]
    assert result.ok is False
    assert result.error_code == "OUTPUT_PATTERN_MISMATCH"
    assert result.needs_escalation is True


def test_structured_json_requires_schema_and_parses_output():
    schema = {
        "type": "object",
        "properties": {"code": {"type": "integer"}},
        "required": ["code"],
        "additionalProperties": False,
    }

    def runner(argv, **kwargs):
        assert "--schema" in argv
        return _completed(json.dumps({"code": 503}))

    pool = AppleFMReadOnlyWorkerPool(
        command_runner=runner,
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    task = AppleFMReadOnlyTask(
        "S1",
        AppleFMTaskKind.STRUCTURED_JSON,
        "Extract code",
        schema=schema,
    )
    receipt = pool.run_batch([task], concurrency=1)
    assert receipt.results[0].ok is True
    assert receipt.results[0].output_contract_valid is True

    with pytest.raises(ValueError, match="requires a schema"):
        AppleFMReadOnlyWorkerPool(
            command_runner=runner,
            environment_preflight=_ok_preflight,
            require_network_denial=False,
        ).run_batch([AppleFMReadOnlyTask("S2", AppleFMTaskKind.STRUCTURED_JSON, "Extract code")])


def test_structured_json_schema_violation_fails_closed():
    schema = {
        "type": "object",
        "properties": {"code": {"type": "integer"}},
        "required": ["code"],
        "additionalProperties": False,
    }
    calls = 0

    def runner(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _completed(json.dumps({"code": "503"}))

    pool = AppleFMReadOnlyWorkerPool(
        command_runner=runner,
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    result = pool.run_batch([
        AppleFMReadOnlyTask("SV1", AppleFMTaskKind.STRUCTURED_JSON, "Extract", schema=schema)
    ]).results[0]
    assert result.ok is False
    assert result.output_contract_valid is False
    assert result.error_code == "SCHEMA_VIOLATION"
    assert result.needs_escalation is True
    assert calls == 1


def test_invalid_structured_schema_is_rejected_before_execution():
    calls = 0

    def runner(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _completed("{}")

    pool = AppleFMReadOnlyWorkerPool(
        command_runner=runner,
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    with pytest.raises(ValueError, match="invalid JSON schema"):
        pool.run_batch([
            AppleFMReadOnlyTask(
                "BAD-SCHEMA",
                AppleFMTaskKind.STRUCTURED_JSON,
                "Extract",
                schema={"type": "not-a-json-schema-type"},
            )
        ])
    assert calls == 0


def test_invalid_json_and_timeout_fail_closed_without_retry():
    calls = 0

    def invalid_json_runner(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _completed("not-json")

    pool = AppleFMReadOnlyWorkerPool(
        command_runner=invalid_json_runner,
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    schema = {"type": "object"}
    result = pool.run_batch([
        AppleFMReadOnlyTask("J1", AppleFMTaskKind.STRUCTURED_JSON, "json", schema=schema)
    ]).results[0]
    assert result.ok is False
    assert result.error_code == "INVALID_JSON"
    assert result.needs_escalation is True
    assert calls == 1

    timeout_calls = 0

    def timeout_runner(*args, **kwargs):
        nonlocal timeout_calls
        timeout_calls += 1
        raise subprocess.TimeoutExpired(cmd=["fm"], timeout=1)

    timeout_pool = AppleFMReadOnlyWorkerPool(
        command_runner=timeout_runner,
        environment_preflight=_ok_preflight,
        require_network_denial=False,
        timeout_s=1,
    )
    timeout_result = timeout_pool.run_batch([
        _classification("T", "classify", "RATE_LIMIT")
    ]).results[0]
    assert timeout_result.error_code == "PROVIDER_TIMEOUT"
    assert timeout_result.needs_escalation is True
    assert timeout_calls == 1


def test_network_denial_is_injected_into_physical_command():
    seen = []

    def runner(argv, **kwargs):
        seen.append(argv)
        return _completed("RATE_LIMIT")

    pool = AppleFMReadOnlyWorkerPool(
        command_runner=runner,
        environment_preflight=_ok_preflight,
        sandbox_exec_path="/bin/sh",
        require_network_denial=True,
    )
    receipt = pool.run_batch(
        [_classification("N1", "classify", "RATE_LIMIT")],
        concurrency=1,
    )
    assert receipt.results[0].ok is True
    assert seen[0][:4] == [
        "/bin/sh",
        "-p",
        "(version 1)(allow default)(deny network*)",
        "/usr/bin/fm",
    ]


def test_prompt_length_is_bounded():
    pool = AppleFMReadOnlyWorkerPool(
        command_runner=lambda *a, **k: _completed("OK"),
        environment_preflight=_ok_preflight,
        require_network_denial=False,
    )
    with pytest.raises(ValueError, match="bounded small-task limit"):
        pool.run_batch([
            AppleFMReadOnlyTask(
                "LONG",
                AppleFMTaskKind.CLASSIFICATION,
                "x" * 4001,
            )
        ])
