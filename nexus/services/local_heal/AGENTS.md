# LocalHeal Pipeline — Agent Contracts
# SCOPE: All agents touching nexus/services/local_heal/
# SSOT: nexus/services/local_heal/

## 1. HealContext V1/V2 Round-Trip

`HealPipeline.run()` returns a **legacy flat `HealContext`** (dataclass from `pipeline.py`).
It has NO `.op` sub-object. Accessing `.op` raises `AttributeError`.

```python
# ❌ WRONG — AttributeError at runtime
pipeline_result_ctx.op.micro_verify_context_present

# ✅ CORRECT
getattr(pipeline_result_ctx, "micro_verify_context_present", False)
```

`sync_from_v2()` MUST use unconditional `setattr` — no `hasattr` guard:

```python
# ❌ WRONG — silently drops dynamic attrs (C8 telemetry, etc.)
for attr, value in v2.op.__dict__.items():
    if hasattr(self, attr):
        setattr(self, attr, value)

# ✅ CORRECT
for attr, value in v2.op.__dict__.items():
    setattr(self, attr, value)
```

Dynamic attributes set on `ctx.op` inside phases (e.g., `ctx.op.micro_verify_context_present = True`)
exist in `op.__dict__` but are NOT declared dataclass fields. `hasattr` on the legacy ctx
returns `False` for them and silently drops them. Unconditional `setattr` is required.

## 2. `localheal_pipeline` No-Provider-Fallback (C9 Contract)

In `localheal_pipeline` topology, `LocalModelExecutor` **never** falls back to direct
provider generation if `pipeline_final_patch` is empty.

```
pipeline_final_patch != ""  →  candidate_patch = pipeline_final_patch
pipeline_final_patch == ""  →  candidate_patch = ""
                               reasoning_summary = "pipeline_failed_empty"
```

Tests MUST NOT assert `candidate_patch.strip() != ""` unless pipeline is mocked to deliver a patch.
Check `reasoning_summary in ("pipeline_result", "pipeline_failed_empty")` instead.

## 3. Verifier Evidence Requirements

Verifier failure evidence can come from any of:
- `stdout` / `stderr`
- `verifier_error` field
- non-zero exit code

`stdout_tail` being non-empty is **not a hard requirement**. Evidence gates should check
the union of available evidence fields, not require a specific field to be non-empty.

## 4. Test Seam Rules

### 4a. Unit tests for PatchSynthesisPhase (C7/C8)

C7 (output classification) and C8 (micro-verify context) checks run **inside**
`PatchSynthesisPhase.run()`, after `apply_and_validate` returns success.

To reach C7/C8 in a unit test, mock `apply_and_validate`:

```python
from nexus.services.local_heal.patch_applier import PatchApplicationResult
mock_apply = MagicMock(return_value=PatchApplicationResult(
    success=True, applied_diffs=["+++ b/file.py\nnew\n"], error_reason="",
))
with patch.object(phase.patch_applier, "apply_and_validate", mock_apply):
    output = phase.run(inp)
    # C7/C8 block now reachable
```

PatchSynthesis recovery paths quarantine verifier-command projection. A missing
`verifier_command` must not alter PatchSynthesis control flow. Do not infer a
PatchSynthesis failure reason solely from verifier-command presence or absence.
Assert the exact branch contract under test.

### 4b. Verifier mock strategy

Use `side_effect = [fail_receipt, pass_receipt]` **only** when the test explicitly exercises
a fail→retry→pass flow. Tests that expect a single consistent outcome may use
`return_value` without `side_effect`.

```python
# For retry-flow tests only:
mock_verify.side_effect = [fail_receipt, pass_receipt]

# For single-outcome tests (acceptable):
mock_verify.return_value = pass_receipt
```

### 4c. Pipeline isolation in unit tests

Unit tests that do not intend to test `HealPipeline` internals should mock `HealPipeline.run`
to return a pre-configured context. Integration tests may run the real pipeline, but must
use bounded, git-backed fixture directories.

## 5. `PatchSynthesisInput` Mutation (frozen dataclass)

`PatchSynthesisInput` is `frozen=True`. To inject `route_context` at test time:

```python
object.__setattr__(inp, "route_context", {"verifier_command": ["python3", "verify.py"]})
```

## 6. Correct Class Names

| Wrong | Correct | Location |
|-------|---------|----------|
| `PatchApplyResult` | `PatchApplicationResult` | `nexus.services.local_heal.patch_applier` |
| `HealContextV2` (from pipeline) | `HealContext` (legacy flat ctx) | `nexus.services.local_heal.pipeline` |
