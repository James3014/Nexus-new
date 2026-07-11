# ADR-2026-07-11: N30R-V2.1 Local Model Latency Profiling & spec_gen Optimization

## Status
ACCEPTED

## Context

Following N30R-V2 correctness recovery (Armor 4/4 = Bare 4/4, ARMOR_RECOVERED_NEUTRAL), the V2.1 task
investigated the latency overhead of Nexus Armor on local Qwen 7B model execution.

Observed canonical summary before this ADR:
```
Bare mean wall time:  5.66s
Armor mean wall time: 20.42s
Observed ratio:       3.61x (OBSERVED_MIXED_BOUNDARY_LATENCY_RATIO)
```

The measurement boundary was asymmetric: Bare timer stopped after model response, Armor timer
covered full pipeline (planner → context → model → parse → apply → verifier → receipt).

## Investigation

Fair profiling baseline (4 tasks × 2 arms × 3 repeats = 24 rows, run_id=1783770466, v5):

| Phase | Median | Note |
|-------|--------|------|
| `planning` | 5.052s | LLM call (INTUITIVE tasks only; syntax uses FAST) |
| `patch_synthesis` | 9.105s | **2 hidden LLM calls**: spec_gen + patch gen |
| `verification` | 0.040s | Negligible |
| `localization` | 0.001s | Negligible |

**Root cause**: `PatchSynthesisPhase.run` contained an undocumented LLM call at line ~118
to generate a "repair specification" (`spec_gen`) using `LocalModelPolicy.select_model(phase="planning")`.
This call:
- Added ~5s per task (one full Qwen 7B inference)
- Was executed **every** task unconditionally (when `repair_specification` was not pre-populated)
- Was **not counted** in `model_call_count` (hardcoded as `1 + semantic_retry_count`)
- Was **overwritten** in `_last_provider_diag` by the subsequent patch gen call
- Made the latency instrumentation misleading (prov_wall only captured the final call)

True call sequence per task:
- INTUITIVE tasks (anchor, semantic, multi): planning LLM + spec_gen LLM + patch gen LLM = 3 calls
- FAST tasks (syntax): spec_gen LLM + patch gen LLM = 2 calls
- Bare: 1 call

## Decision

### Optimization Implemented: NEXUS_DISABLE_SPEC_GEN gate (Commit F: 9f99ded14)

Added `os.environ.get("NEXUS_DISABLE_SPEC_GEN", "0") == "1"` gate in
`nexus/services/local_heal/phases/patch_synthesis.py`.

Rationale:
- When `PlanningPhase` already produces a `repair_strategy`, spec_gen is redundant second inference
- `repair_specification` is advisory-only in `PromptBuilder.build_patch_user_prompt` (adds a hint section)
- Skipping it when plan exists reduces pipeline from 3→2 LLM calls (INTUITIVE) or 2→1 (FAST tasks)

Default: OFF (preserves existing behaviour). Set `NEXUS_DISABLE_SPEC_GEN=1` to enable fast-path.

Also fixed: shadowed `import os` at line 362 causing `UnboundLocalError` when NEXUS_DISABLE_SPEC_GEN
was evaluated before Python bound the local name.

### Optimization Rejected: NEXUS_FAST_MODE=1 (skip planning LLM)

Tested in v7 baseline (run_id=1783772357):
- `n30r_smoke_multi` failed all 3 repeats (9/12 = 75% solve rate)
- `DeterministicSymbolExtractor` cannot produce sufficient `repair_strategy` for recursive logic bugs
- Planning LLM call is architecturally necessary for INTUITIVE-mode tasks

## Consequences

### v5 → v6 benchmark (NEXUS_DISABLE_SPEC_GEN=1):

| Metric | v5 (baseline) | v6 (optimized) | Delta |
|--------|--------------|----------------|-------|
| Core solved | 12/12 ✅ | 12/12 ✅ | zero regression |
| Core median E2E | 15.803s | 13.662s | **-2.14s (-13.5%)** |
| Fair E2E ratio | 5.387x | 4.554x | **-0.833x** |
| phase_synthesis | 9.105s | 5.526s | **-3.58s (-39.3%)** |
| phase_planning | 5.052s | 5.068s | ≈ same |

### Remaining overhead (honest accounting)

After spec_gen removal, remaining Core overhead over Bare:
```
planning LLM call:    ~5.07s  (3/4 tasks; FAST-mode syntax skips)
patch gen LLM call:   ~5.53s  (all 4 tasks, measured as provider_wall)
non-model overhead:   ~2.06s  (localization, apply, receipt, verifier)
─────────────────────────────
Total Core median:    13.66s
Bare median:           3.00s
Remaining ratio:       4.554x
```

### No further safe optimization exists at current architecture

The remaining 4.554x ratio consists of:
1. **~1.87x** from provider call duration difference (Core prompt is ~5× larger: 445 vs 89 tokens)
2. **~1.0x** from additional planning LLM call (architecturally required)
3. **~0.3x** from deterministic overhead (apply, verifier, receipt)

Any further ratio reduction requires either:
- Prompt compression (reduce Core prompt tokens without harming solve rate)
- Parallelizing planning + patch gen (major architectural change)
- Smaller model for planning (but 7B is already smallest viable)

## Lessons

1. **Hidden LLM calls must be instrumented**: `model_call_count = 1 + semantic_retry_count` was
   incorrect; it masked 2-3 actual calls per task. Always track per-phase call counts explicitly.
2. **`_last_provider_diag` overwrites**: Tracking only the last provider response obscures multi-call
   pipelines. Future: accumulate `provider_elapsed_sec` across all calls.
3. **FAST mode is not free**: `DeterministicSymbolExtractor` works for simple symbol-lookup bugs
   but fails on algorithmic/recursive bugs. `ReasoningRouter` keyword matching must be expanded
   carefully before broadening FAST mode scope.
4. **spec_gen was architectural dead weight**: The `repair_specification` prompt section was advisory
   ("verify against code"), making spec_gen a costly extra inference with minimal benefit when a
   plan already existed. Pattern: if a feature is advisory-only, gate it behind a latency flag.

## Files Changed

- `nexus/services/local_heal/phases/patch_synthesis.py` — NEXUS_DISABLE_SPEC_GEN gate + local import fix
- `nexus/services/local_heal/local_model_capability_executors.py` — phase timing standardization
- `docs/bench/n30r/v2_latency/` — v5 (run 1783770466) and v6 (run 1783771402) baseline data
