# P3-N1 Synthetic Provider Fixture ADR

## Status
**ADR-DRAFT**

## Decision
Allow synthetic provider fixture for P3 testing only. Synthetic provider may generate deterministic candidate-like payloads. Synthetic provider must not call network. Synthetic provider must not use API keys. Synthetic provider must not import cloud SDKs. Synthetic provider must not apply patches. Synthetic provider must not mark solved.

## Authority

| Authority | Description |
|-----------|-------------|
| `synthetic_provider_only` | Only synthetic fixtures allowed |
| `dry_run_only` | No real provider execution |
| `env_guarded_test_only` | Tests only under env guard |
| `blocked` | Synthetic provider blocked |
| `rollback_required` | Unsafe synthetic behavior detected |

## Required Receipt Fields

| Field | Value |
|-------|-------|
| `p3_n_provider_kind` | `"synthetic"` |
| `p3_n_provider_invoked` | `false` (normal dry-run) |
| `p3_n_synthetic_provider_invoked` | `true` (only in fixture tests) |
| `p3_n_real_provider_invoked` | `false` |
| `p3_n_network_invoked` | `false` |
| `p3_n_api_key_used` | `false` |
| `p3_n_patch_apply_invoked` | `false` |
| `p3_n_runtime_behavior_changed` | `false` |
| `p3_n_candidate_is_synthetic` | `true` (only for fixture rows) |
| `p3_n_full_verifier_required` | `true` |
| `p3_n_claim_gate_required` | `true` |
| `p3_n_claim_eligible` | `false` |
| `p3_n_public_claim_allowed` | `false` |
| `p3_n_production_ready` | `false` |

## Required Blockers

- `real_provider_invoked=true`
- `network_invoked=true`
- `api_key_used=true`
- Real provider kind used
- `patch_apply_invoked=true`
- `runtime_behavior_changed=true`
- `claim_eligible=true`
- `public_claim_allowed=true`
- `production_ready=true`
- `full_verifier_required=false`
- `claim_gate_required=false`

## Non-Claims
- Not real provider
- Not cloud_with_local_assist implementation
- Not solve-rate evidence
- Not production-ready
- Not public-claim eligible

## Next Package
P3-N2 Synthetic Provider Contract
