# Nexus Governance Lane Decision (Flash + Pro) - 2026-05-03

## Dataset
- Task set: `scripts/bench/public_benchmark_nexus_value_v1.json` (6 tasks)
- A/B: same model `with_nexus` vs `without_nexus`
- Hidden verifier: enabled

## Flash (`gemini-3-flash-preview`)

| Lane | with_nexus solve | with_nexus semantic | with_nexus trust mismatch | with_nexus wall(s) | without_nexus solve | without_nexus wall(s) |
|---|---:|---:|---:|---:|---:|---:|
| Baseline (`capability_lift_r5b`) | 1.0000 | 1.0000 | 0.0000 | 60.1919 | 0.6667 | 30.5694 |
| Full optimized (`full_governance_opt_r1`) | 1.0000 | 1.0000 | 0.0000 | 66.2918 | 0.6667 | 34.7840 |
| Lean optimized (`lean_governance_opt_r1`) | 1.0000 | 1.0000 | 0.0000 | 42.8234 | 0.6000* | 32.7457 |

\* `without_nexus eligible_n=5` due one parse_error infra row.

Flash conclusion:
- Full lane preserves quality but is slower than baseline.
- Lean lane preserves with_nexus quality and improves wall time by ~28.9% vs baseline.

## Pro (`gemini-3.1-pro-preview`)

| Lane | with_nexus solve | with_nexus semantic | with_nexus trust mismatch | with_nexus wall(s) | without_nexus solve | without_nexus wall(s) |
|---|---:|---:|---:|---:|---:|---:|
| Lean optimized (`lean_governance_opt_r1`) | 1.0000 | 1.0000 | 0.0000 | 50.5510 | 0.3333 | 15.5924 |
| Full optimized (`full_governance_opt_r2_fix`) | 1.0000 | 1.0000 | 0.0000 | 72.2629 | 0.3333 | 19.8369 |

Pro conclusion:
- Lean lane remains healthy and shows strong capability uplift.
- Full lane has been remediated and is now public-claim safe on the 6-task set.

## Decision
1. **Production benchmark default lane**: `Lean Governance`  
   - Rationale: best speed/quality tradeoff on both Flash and Pro.
2. **Public trust-max lane**: `Full Governance` is now recovered on Pro and can be used for trust-max claims when latency budget allows.

## Completed remediation proof
1. Root causes fixed in hidden-verifier mutation path (`merge_limits`, `remaining_ms`).
2. Targeted tests added and passed in `tests/research/test_sprint_service.py`.
3. Pro Full rerun (`full_governance_opt_r2_fix`) now meets:
   - solve == 1.0
   - semantic == 1.0
   - trust_mismatch == 0.0
