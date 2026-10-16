# Local Model Sprint C15-4B: Delegated Retry Proof Probe

**Date**: 2026-07-04  
**Status**: `C15_4B_PARTIAL_PROBE_CONSOLIDATED` — benchmark-only controls committed; live delegated-retry solve still NOT_PROVEN.

## 1. Objective

```text
Produce bounded live evidence that distinguishes:
1. first_pass solved
2. pipeline_semantic_retry solved
3. delegated_retry solved

Target for C15-4B:
toy-math-forced-delegated-retry should reach solve_mechanism=delegated_retry.
```

## 2. Changes Implemented

### Files changed

```text
nexus/services/local_heal/orchestrator.py
nexus/services/local_heal/local_model_capability_executors.py
nexus/services/local_heal/pipeline.py
scripts/bench/m1_real_local_solve_benchmark.py
tests/benchmark/test_m1_real_local_solve_benchmark.py
tests/unit/local_heal/test_retry_metadata.py
tests/unit/local_heal/test_local_model_executor.py
```

### What changed

```text
1. Added benchmark-only route_context control:
   disable_primary_semantic_retry=true

2. Added solve_mechanism projection in M1 benchmark rows:
   - first_pass
   - pipeline_semantic_retry
   - delegated_retry
   - *_unresolved variants

3. Added bounded live probe task:
   toy-math-forced-delegated-retry

4. Added benchmark-only repair_specification injection path so the probe can
   steer the first patch attempt without changing global runtime policy.

5. Fixed two latent runtime issues exposed by the probe:
   - local_model_capability_executors.py unbound local:
     semantic_retry_telemetry
   - pipeline.py legacy HealContext missing repair_specification propagation
```

## 3. Verification

Commands:

```bash
python3 -m py_compile \
  nexus/services/local_heal/pipeline.py \
  nexus/services/local_heal/local_model_capability_executors.py \
  nexus/services/local_heal/orchestrator.py \
  scripts/bench/m1_real_local_solve_benchmark.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py \
  tests/unit/local_heal/test_retry_metadata.py \
  tests/unit/local_heal/test_local_model_executor.py
```

```bash
uv run pytest \
  tests/benchmark/test_m1_real_local_solve_benchmark.py \
  tests/unit/local_heal/test_retry_metadata.py \
  tests/unit/local_heal/test_local_model_executor.py \
  -k "repair_specification_to_v2 or test_retry_metadata or test_m1_real_local_solve_benchmark" \
  -q
```

Result:

```text
30 passed, 145 deselected
```

Live probe:

```bash
uv run python scripts/bench/m1_real_local_solve_benchmark.py \
  --task-id toy-math-forced-delegated-retry
```

## 4. Live Outcomes

### 4.1 New controls behaved as designed

Observed:

```text
disable_primary_semantic_retry was accepted through route_context.
solve_mechanism is now emitted by benchmark rows.
repair_specification can be passed into the LocalHeal legacy wrapper.
```

### 4.2 Latent bugs found and fixed

Bug A:

```text
cannot access local variable 'semantic_retry_telemetry'
where it is not associated with a value
```

Fix:

```text
Initialize semantic_retry_telemetry={} before the pipeline_result_ctx branch.
```

Bug B:

```text
pipeline_instantiation_error after adding repair_specification
```

Root cause:

```text
pipeline.py legacy HealContext lacked a repair_specification field,
so benchmark-only steering could not cross the legacy wrapper boundary.
```

Fix:

```text
Add repair_specification to legacy HealContext and propagate it into v2 op context.
```

### 4.3 Delegated retry solved still not proven

Latest live row:

```text
task_id=toy-math-forced-delegated-retry
solved=true
solve_mechanism=first_pass
protocol_retry_attempted=false
semantic_retry_invoked=false
pipeline_retry_delegated=false
delegated_retry_stage=not_invoked
retry_not_invoked_reason=already_solved
```

Meaning:

```text
Even with:
- disable_primary_semantic_retry=true
- explicit repair_specification forcing x * 4 first

the local model still emitted the correct x * 3 patch directly.
So the delegated retry branch still did not become the solving mechanism.
```

## 5. Current Truth

Proven now:

```text
- Claim gate can distinguish first_pass vs pipeline_semantic_retry vs delegated_retry.
- Benchmark-only controls can suppress primary semantic retry.
- Benchmark-only controls can inject repair specification through the legacy wrapper.
- The probe no longer fails from projection/wrapper bugs.
```

Not proven:

```text
- delegated_retry solved on a live bounded task
```

## 6. New Blocker

Current blocker:

```text
The local model can still solve the probe directly on patch_attempt_1.
That means delegated retry is bypassed for a better reason than before:
not semantic retry preemption, not protocol retry preemption,
but direct first-pass correctness.
```

Interpretation:

```text
C15-4B now has a cleaner blocker:
the harness can ask for delegated proof, but it cannot force the first live
patch to be wrong without crossing into artificial result control.
```

## 7. Next Recommended Step

```text
C15-4C Delegated Retry First-Attempt Isolation Design
```

Need:

```text
Design a bounded task where the first patch cannot reasonably infer the final
correct repair from the initial problem statement alone, but delegated retry can
infer it from verifier evidence.
```

Acceptable directions:

```text
1. verifier emits corrective evidence unavailable in the initial prompt
2. first attempt uses a bounded wrong spec hidden from the retry stage
3. benchmark-only control that freezes first-pass patch policy without faking the retry output
```

Forbidden directions:

```text
- hardcoding delegated retry success
- altering verifier authority
- altering candidate isolation rules
- changing route authority away from CapabilityPlanner
```

---

## 8. C15-4B-INTEGRITY-CHECK Consolidation Summary (2026-07-04)

**Status**: `C15_4B_PARTIAL_PROBE_CONSOLIDATED`

**Commit**: `d17b030ec` test(localheal): consolidate C15-4B delegated retry proof probe controls

**Files committed**:
- `nexus/services/local_heal/local_model_capability_executors.py`
- `nexus/services/local_heal/orchestrator.py`
- `nexus/services/local_heal/pipeline.py`
- `scripts/bench/m1_real_local_solve_benchmark.py`
- `tests/benchmark/test_m1_real_local_solve_benchmark.py`
- `tests/unit/local_heal/test_local_model_executor.py`
- `tests/unit/local_heal/test_retry_metadata.py`
- `docs/reports/local_model_sprint_c15_4b_delegated_retry_proof_probe.md`

**Commands run**:
- `python3 -m py_compile` — 7 files, no errors
- `uv run pytest` — 160 passed, 30 focused passed

**Current claim boundary**:
- delegated_retry solved = NOT_PROVEN
- solve_mechanism=first_pass is not delegated_retry
- benchmark-only controls are proof harness, not Nexus full capability
- production_ready=false
- public_claim_allowed=false

**Next recommended task**: C15-4C-1 Controlled Verifier Failure Task Spec
