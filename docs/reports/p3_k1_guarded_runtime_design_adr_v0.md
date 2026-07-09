# P3-K1 Guarded Runtime Design ADR

## Status
**ADR-DRAFT**

## Decision
P3 may proceed only to guarded runtime design. No runtime execution is enabled by this ADR. No default behavior changes are allowed. No production claim is allowed.

## Runtime Authority Model

| Authority | Description | Allowed |
|-----------|-------------|---------|
| `shadow_only` | P3 components produce metadata only | Current state |
| `env_guarded_dry_run` | P3 components run with env flag, dry-run only | Future candidate |
| `env_guarded_runtime_candidate` | P3 components run with env flag, limited runtime | Future candidate |
| `blocked` | P3 execution blocked | Safety state |
| `rollback_required` | P3 behavior was changed unsafely | Safety state |

## Required Env Guard

Future runtime must require explicit env flag:
- `NEXUS_P3_CLOUD_WITH_LOCAL_ASSIST=1` (or similar)
- Flag-off must preserve current behavior (shadow_only)
- No implicit rollout
- No silent promotion
- Flag must be checked at every P3 execution entry point

## Required Provider Seam

Cloud provider interface must be:
- Pure contract first (no implementation)
- No API key required during contract phase
- No network call during contract phase
- Provider unavailable must fail closed
- Provider contract must be versioned

## Required Verification Chain

| Requirement | Status |
|-------------|--------|
| P2 hash/apply truth | Remains required |
| P4 verifier | Remains final authority |
| P4 claim gate | Remains required |
| P3 can mark solved | **Never** |
| P3 can set public_claim_allowed | **Never** |

## Required Coordination with P6

- P6 can degrade quota/candidate count only under its own guard
- P6 cannot override P3 topology
- P3 cannot override P6 quota fail-closed
- Both must preserve P4 authority

## Promotion Blockers

The following conditions must block P3 runtime promotion:

1. `cloud_call_invoked` without env guard
2. `local_model_call_invoked` without env guard
3. `patch_apply_invoked` by P3
4. `claim_eligible=true` from P3
5. `public_claim_allowed=true` from P3
6. `full_verifier_required=false`
7. `claim_gate_required=false`
8. `default_runtime_behavior_changed=true`

## Next Package
P3-K2 Runtime Env Guard Contract
