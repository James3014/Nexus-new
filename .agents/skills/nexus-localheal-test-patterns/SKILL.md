---
name: nexus-localheal-test-patterns
description: >
  Nexus LocalHeal pipeline test authoring cheatsheet.
  Load when writing or debugging unit tests under tests/unit/local_heal/ or tests/benchmark/,
  especially for PatchSynthesisPhase (C7/C8), LocalHealPipelineCapabilityExecutor,
  or LocalModelExecutor with localheal_pipeline topology.
  Covers correct class names, mock setups, and architectural contracts.
capability: localheal-testing
load_when:
  - writing or debugging LocalHeal unit tests
  - testing localheal_pipeline projection
  - testing committee or delegated retry transitions
do_not_load_when:
  - non-LocalHeal tasks
  - repository cleanup
  - Wiki, CLI, Rust or cloud-agent work
cost_tier: light
evidence_required:
  - source contract checked
  - focused tests executed
replacement_rule:
  - update when LocalHeal contracts or test seams change
---

# Nexus LocalHeal Test Patterns

## 1. Correct Class Names

| Wrong (causes ImportError) | Correct |
|---------------------------|---------|
| `PatchApplyResult` | `PatchApplicationResult` from `nexus.services.local_heal.patch_applier` |
| `HealContextV2` from `pipeline` | `HealContext` from `nexus.services.local_heal.pipeline` (legacy flat ctx) |

### `PatchApplicationResult` fields
```python
from nexus.services.local_heal.patch_applier import PatchApplicationResult

result = PatchApplicationResult(
    success=True,
    applied_diffs=["+++ b/file.py\nnew\n"],  # list of diff strings
    error_reason="",                          # None or str
    syntax_gate_passed=True,
    preflight_telemetry={},
    errors=[],
)
```

---

## 2. PatchSynthesisPhase Unit Tests (C7/C8)

### Problem
C7 (output classification) and C8 (micro-verify context) checks run **after**
`apply_and_validate` succeeds. Without mocking, real filesystem access hits
`FILE_NOT_FOUND` and the test exits early — C7/C8 block is never reached.

### Required Mock Setup
```python
from unittest.mock import patch, MagicMock
from nexus.services.local_heal.patch_applier import PatchApplicationResult

phase = PatchSynthesisPhase(parser, patcher, llm_client=MockLLM())

mock_apply = MagicMock(return_value=PatchApplicationResult(
    success=True,
    applied_diffs=["+++ b/file.py\nnew\n"],
    error_reason="",
))
with patch.object(phase.patch_applier, "apply_and_validate", mock_apply):
    output = phase.run(inp)
    # Now C7/C8 block is reachable
```

### To reach C8 verifier pass
```python
from nexus.services.local_heal.micro_verifier import MicroVerifyResult

with patch.object(phase.patch_applier, "apply_and_validate", mock_apply), \
     patch("nexus.services.local_heal.micro_verifier.MicroVerifier.verify") as mock_v:
    mock_v.return_value = MicroVerifyResult(
        passed=True, syntax_ok=True, import_ok=True, task_scoped=True
    )
    output = phase.run(inp)
    assert output.success is True
```

### Verifier command and PatchSynthesis control flow
- Missing `verifier_command` must not alter PatchSynthesis control flow.
- Recovery paths may intentionally leave verifier context projection unset.

### Setting task-scoped verifier_command on frozen PatchSynthesisInput
```python
# PatchSynthesisInput is frozen=True; use object.__setattr__
object.__setattr__(inp, "route_context", {
    "verifier_command": ["python3", "/path/to/verify.py"]
})
```

---

## 3. LocalModelExecutor-Level C7/C8 Telemetry Tests

### Problem
`LocalModelExecutor.run()` with `localheal_pipeline` topology invokes the real pipeline,
which requires real filesystem. C7/C8 fields in `raw_meta` come from `repair_exec.telemetries`.
Real pipeline produces `output_class == "UNKNOWN"` in unit test environment.

### Correct Pattern: Mock `LocalHealPipelineCapabilityExecutor.execute`
```python
from unittest.mock import patch
from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult

with patch(
    "nexus.services.local_heal.local_model_capability_executors"
    ".LocalHealPipelineCapabilityExecutor.execute"
) as mock_exec:
    mock_exec.return_value = CapabilityExecutionResult(
        name="repair_loop", selected=True, invoked=True,
        gate_passed=False, outcome_contributed=False,
        evidence_present=True, failure_reason="FENCED_OUTPUT_STOP_GATE",
        telemetries={
            "pipeline_final_patch": "",
            "pipeline_solve_eligible": False,
            "pipeline_failure_reason": "FENCED_OUTPUT_STOP_GATE",
            # C7 fields
            "output_class": "FENCED_SEARCH_REPLACE",
            "contains_markdown_fence": True,
            "output_excerpt_first_500": "...",
            # C8 fields (optional — only assert what your test covers)
            "micro_verify_context_present": False,
            "bare_python_rejected": True,
        }
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    assert meta.get("output_class") == "FENCED_SEARCH_REPLACE"
```

All keys in `telemetries` are spread into `raw_meta`.

---

## 4. C9 No-Fallback Contract

```
localheal_pipeline topology invariant:
  pipeline_final_patch != ""  →  candidate_patch = pipeline_final_patch
  pipeline_final_patch == ""  →  candidate_patch = ""  (NO provider fallback)
  reasoning_summary values: "pipeline_result" | "pipeline_failed_empty"
```

### Test Assertion Pattern
```python
# WRONG — assumes provider fallback still exists
assert result.candidate_patch.strip() != ""

# CORRECT — check the contract
assert result.reasoning_summary in ("pipeline_result", "pipeline_failed_empty")

# CORRECT — when pipeline is mocked to return a real patch
assert result.candidate_patch != ""
assert result.raw_model_metadata.get("pipeline_result_projected") is True
```

---

## 5. Verifier Mock Strategy

Use `side_effect` **only** for fail→retry→pass flow tests:

```python
# Only for tests that exercise the retry transition:
mock_verify.side_effect = [fail_receipt, pass_receipt]
```

For single-outcome tests, static `return_value` is acceptable:

```python
# Acceptable for tests expecting one consistent result:
mock_verify.return_value = pass_receipt
```

Verifier failure evidence can come from `stdout`, `stderr`, `verifier_error`, or
non-zero exit code. `stdout_tail` being non-empty is not a hard requirement.

---

## 6. HealContext V1/V2 Round-Trip

- `HealPipeline.run()` returns **legacy `HealContext`** (flat dataclass, no `.op`)
- `HealContextV2` only exists during pipeline execution inside `HealOrchestrator`

```python
# WRONG — AttributeError
val = pipeline_result_ctx.op.micro_verify_context_present

# CORRECT
val = getattr(pipeline_result_ctx, "micro_verify_context_present", False)
```

`sync_from_v2()` uses unconditional `setattr` to carry dynamic attrs from `v2.op.__dict__`
back to the legacy ctx. Do not add `hasattr` guards — they drop telemetry.

---

## 7. Benchmark Run Command

```bash
timeout 180 uv run python scripts/bench/m1_real_local_solve_benchmark.py
```
