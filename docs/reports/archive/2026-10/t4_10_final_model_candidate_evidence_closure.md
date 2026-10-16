# T4.10 Final Model-Candidate Evidence Closure

**Date**: 2026-06-18
**Verdict**: GREEN

---

## Executive Summary

T3.0–T4.10 10-task sequence completed. Fixture-backed verified candidates = 4. Historical-only preserved = 4. CI validation GREEN. No public claim. No attribution pollution.

## Timeline

| Task | Verdict | Achievement |
|------|---------|-------------|
| T3.0 | YELLOW | D0 6/6, M1/M2 blocked |
| T3.1 | YELLOW | Qwen14B callable |
| T3.2 | GREEN | First model_patch_reward=1.0 |
| T3.3 | YELLOW | 1/3 M2 |
| T3.4 | YELLOW | Near-miss |
| T3.5 | GREEN | Context-aware syntax gate |
| T3.6 | GREEN | 4/4 M2 |
| T3.7 | GREEN | 5/6 M2 |
| T3.8 | RED | No-op guard + indentation |
| T3.9 | RED | Source anchoring |
| T4.0 | YELLOW | Source revision |
| T4.1 | YELLOW | Evidence freeze |
| T4.2 | RED | 2/6 eligible |
| T4.3 | YELLOW | 2/6 fixture-ready |
| T4.4 | GREEN | 2/2 fixture replay |
| T4.5 | GREEN | CI validation 14/14 |
| T4.6 | RED | Indentation syntax |
| T4.7 | YELLOW | Root cause found |
| T4.8 | GREEN | Indentation adapter + 2 probes |
| T4.9 | GREEN | 4/4 consolidation |
| T4.10 | GREEN | Final closure |

## Final Candidate Table

| instance_id | status | first_success | fixture_ready | fresh_reward | projection |
|-------------|--------|---------------|---------------|--------------|------------|
| astropy-13236 | fixture_backed_verified | T3.2 | YES | 1.0 | NO |
| sympy-13852 | fixture_backed_verified | T3.8 | YES | 1.0 | NO |
| astropy-12907 | fixture_backed_verified | T4.8 | YES | 1.0 | YES |
| astropy-14182 | fixture_backed_verified | T4.8 | YES | 1.0 | YES |

## Historical-Only Table

| instance_id | preserved | exclusion | not_model_failure |
|-------------|-----------|-----------|-------------------|
| sympy-12419 | YES | source_stale | YES |
| sympy-13647 | YES | source_stale | YES |
| astropy-14365 | YES | source_stale | YES |
| astropy-14309 | YES | source_stale | YES |

## Attribution Summary

| Check | Status |
|-------|--------|
| model_calls>0 for fresh success | ✓ |
| R0 not counted as fresh | ✓ |
| deterministic fallback not counted | ✓ |
| no-op not counted | ✓ |
| truth/manual patch not counted | ✓ |
| model-generated SEARCH not used | ✓ |
| indentation projection safe | ✓ |
| verification required | ✓ |

## Non-Claims

This is NOT:
- A public benchmark
- A Qwen solve rate
- Comparable to official SWE-bench
- Production-ready autonomous patcher
- Generalized solve rate

This IS:
- Internal controlled model-candidate evidence
- CI-validated fixture-backed replay path
- Human review required before training/export

## Next-Stage Options

**Option A**: T5 small controlled expansion (fixture-first protocol)
**Option B**: S0 StrategyEnvelope MVP (recommended)
**Option C**: Product/PoC packaging (deterministic report generation only)

**Recommended**: Option B — S0 StrategyEnvelope MVP. Patch/replay substrate stable enough to add strategy layer. Public claim remains blocked.

## Files Produced

1. configs/model_candidates/t4_10_final_model_candidate_registry.yaml
2. configs/model_candidates/t4_10_final_replay_fixture_manifest.yaml
3. docs/reports/t4_10_final_model_candidate_evidence_closure.md
4. docs/reports/t4_10_internal_capability_statement.md
5. docs/reports/t4_10_training_export_readiness_dossier.md
6. docs/reports/s0_strategy_envelope_readiness_bridge.md
