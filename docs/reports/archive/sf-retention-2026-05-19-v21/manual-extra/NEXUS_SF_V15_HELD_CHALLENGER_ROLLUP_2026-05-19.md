# NEXUS SF V15 Held Challenger Rollup

- Status: PASS
- Live rows: 21/21 PASS, return_count=0
- Runtime apply-ready: 4
- Held tradeoff: 1
- Blocked no effective skill: 2

| capability | decision | winner | token delta | wall delta sec | reason |
|---|---|---|---:|---:|---|
| autonomic_router | approve_runtime_apply_ready | sf2-autonomic_router-route-fit-spec | -8572 | -54.6421 | current_best_effective_and_cost_dominates_no_skill |
| benchmark_meta_opt | hold_tradeoff | nexus-benchmark-continuous-optimization | 580 | -11.0481 | effective_skill_has_token_or_wall_tradeoff |
| delivery_acceptance_gate | blocked_no_effective_skill |  |  |  | no_skill_arm_reached_effective_outcome_contribution |
| mempalace | approve_runtime_apply_ready | sf2-mempalace-route-fit-spec | -3670 | -57.1491 | current_best_effective_and_cost_dominates_no_skill |
| policy_capability_gate | blocked_no_effective_skill |  |  |  | no_skill_arm_reached_effective_outcome_contribution |
| registry_skills_sync | approve_runtime_apply_ready | sf2-registry_skills_sync-route-fit-spec | -10393 | -75.0396 | current_best_effective_and_cost_dominates_no_skill |
| sandbox_replay | approve_runtime_apply_ready | sf2-sandbox_replay-route-fit-spec | -7784 | -37.9476 | current_best_effective_and_cost_dominates_no_skill |

## Boundary

Cheaper challengers with `effective_rows=0` were rejected instead of promoted. Public benchmark remains blocked.
