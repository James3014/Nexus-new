# N30R-V2.1 Latency Profiling — Final Report

**Date**: 2026-07-11
**Branch**: fix/n30r-genuine-production-executor
**Run IDs**: v5=1783770466, v6=1783771402, v7=1783772357

---

## Executive Summary

| State | Value |
|-------|-------|
| Correctness | **ARMOR_RECOVERED_NEUTRAL** (4/4 = Bare 4/4) |
| Pre-profiling ratio | 3.61x (OBSERVED_MIXED_BOUNDARY_LATENCY_RATIO) |
| Fair baseline ratio (v5) | **5.387x** |
| After spec_gen opt (v6) | **4.554x** |
| FAST_MODE attempt (v7) | ❌ REJECTED — 9/12 solve rate |

---

## Measurement Methodology

**Fair Boundary Definition**:
- **Bare**: `start_timer → model_call → stop_timer`. Parser, verifier outside timer.
- **Core**: `start_timer → planner → context → model(s) → parse → apply → verifier → receipt → stop_timer`

Both arms now use identical boundary: full pipeline from problem receipt to verified solve decision.

**Run configuration**: 4 smoke tasks × 2 arms (BARE/CORE) × 3 repeats = 24 rows per run.
Model: `qwen2.5-coder:7b-instruct` (Ollama local). Environment parity: single host, alternating AB/BA order.

---

## Baseline v5 — Pre-optimization (spec_gen ON)

**run_id**: 1783770466

| Metric | Bare | Core |
|--------|------|------|
| Solved | 12/12 | 12/12 |
| Median E2E | 2.934s | 15.803s |
| Fair E2E ratio | — | **5.387x** |
| Provider ratio | — | **2.057x** |
| Non-provider overhead | — | 9.788s |

### Phase breakdown (Core, median):
| Phase | Duration | LLM calls |
|-------|----------|-----------|
| reproduction | 0.0s | 0 |
| planning | 5.052s | 1 (INTUITIVE) / 0 (FAST) |
| localization | 0.001s | 0 |
| **patch_synthesis** | **9.105s** | **2 (spec_gen + patch)** |
| verification | 0.040s | 0 |

---

## Root Cause: spec_gen Hidden LLM Call

`PatchSynthesisPhase.run` (line ~118) called `self.llm_client.generate` to produce a
"repair specification" before every patch generation attempt. This call:

1. Used `LocalModelPolicy.select_model(phase="planning")` → `num_ctx=16384, num_predict=512`
2. Was NOT gated by any feature flag
3. Was NOT counted in `model_call_count` (masked by hardcoded formula `1 + semantic_retry_count`)
4. Was overwritten in `_last_provider_diag` telemetry (only final call captured)

True LLM call count per task type:
- INTUITIVE (anchor, semantic, multi): **3 calls** → planning + spec_gen + patch
- FAST (syntax): **2 calls** → spec_gen + patch
- Bare: **1 call**

---

## Baseline v6 — After NEXUS_DISABLE_SPEC_GEN=1

**run_id**: 1783771402

| Metric | Bare | Core | vs v5 |
|--------|------|------|-------|
| Solved | 12/12 | **12/12** ✅ | zero regression |
| Median E2E | 3.000s | **13.662s** | **-2.14s (-13.5%)** |
| Fair E2E ratio | — | **4.554x** | **-0.833x** |
| Provider ratio | — | 1.867x | -0.190x |
| Non-provider overhead | — | 6.968s | -2.82s |

### Phase breakdown delta (Core, median):
| Phase | v5 | v6 | Delta |
|-------|----|----|-------|
| planning | 5.052s | 5.068s | ≈ 0 |
| **patch_synthesis** | **9.105s** | **5.526s** | **-3.58s (-39.3%)** |
| verification | 0.040s | 0.041s | ≈ 0 |

**Result**: `patch_synthesis` reduced by 39.3% — exactly one Qwen 7B call removed.

---

## Baseline v7 — NEXUS_FAST_MODE=1 (REJECTED)

**run_id**: 1783772357

| Metric | Bare | Core |
|--------|------|------|
| Solved | 12/12 | **9/12 (75%)** ❌ |
| Median E2E | 2.379s | 11.404s |
| Fair E2E ratio | — | 4.794x |
| phase_planning | — | 0.0001s |
| phase_synthesis | — | 4.891s |

**Failure**: `n30r_smoke_multi` failed all 3 repeats (VERIFIED_FAIL).
`DeterministicSymbolExtractor` cannot generate adequate `repair_strategy` for recursive
flatten logic. Planning LLM call is architecturally required for INTUITIVE-mode tasks.

**Decision**: NEXUS_FAST_MODE=1 globally is REJECTED. The `ReasoningRouter` correctly
identifies simple tasks (syntax/typo/rename/missing) for FAST mode; complex logic bugs
require LLM planning.

---

## Remaining Overhead Decomposition (v6 canonical)

```
Core overhead breakdown (median, 4-task smoke suite):

  Planning LLM call (provider):      ~5.07s   [3/4 tasks; syntax skips via FAST]
  Patch gen LLM call (provider):     ~5.45s   [all 4 tasks]
  Non-model deterministic overhead:  ~2.74s   [context build, apply, verifier, receipt]
  ─────────────────────────────────────────
  Core median E2E:                   13.66s
  Bare median E2E:                    3.00s
  Fair ratio:                        4.554x

  Provider ratio (Core vs Bare):     1.867x
  Cause: Core prompt is ~5× larger (445 vs 89 tokens median)
         Core makes 2 provider calls vs Bare's 1 (INTUITIVE tasks)
```

### No further safe optimization at current architecture

| Optimization | Impact | Safety | Decision |
|-------------|--------|--------|---------|
| Skip spec_gen (NEXUS_DISABLE_SPEC_GEN=1) | -3.58s synthesis | ✅ 12/12 | **IMPLEMENTED** |
| Skip planning LLM (NEXUS_FAST_MODE=1) | -5s planning | ❌ 9/12 | REJECTED |
| Compress Core prompt | -1-2s (estimate) | Unknown | Future work |
| Parallel planning + patch gen | -5s (estimate) | Unknown | Future work (major arch) |
| Smaller model for planning | -1-2s | Unknown | Future work |

---

## Files

| File | Purpose |
|------|---------|
| `nexus/services/local_heal/phases/patch_synthesis.py` | NEXUS_DISABLE_SPEC_GEN gate |
| `nexus/services/local_heal/local_model_capability_executors.py` | Phase timing instrumentation |
| `docs/bench/n30r/v2_latency/1783770466/` | v5 raw data (24 rows) |
| `docs/bench/n30r/v2_latency/1783771402/` | v6 raw data (24 rows) |
| `docs/bench/n30r/v2_latency/1783772357/` | v7 raw data (24 rows, rejected) |
| `nexus_wiki_vault/01_System/ADR/ADR-2026-07-11-n30r-v21-latency-profiling-spec-gen-opt.md` | ADR |

---

## Status: CLOSED

Optimization scope exhausted under correctness constraint.
Next milestone: prompt compression or parallel planning (requires separate task).
