# P3-L1 Env-Guarded Dry-Run Hook ADR

## Status
**ADR-DRAFT**

## Decision
Allow P3 dry-run metadata hook only under explicit env guard. Flag-off behavior must be byte-for-byte/default semantically unchanged. No provider invocation. No network. No local model invocation. No patch apply. No solved/claim/public claim.

## Env Guard
- Use existing K2 guard flag: `NEXUS_P3_CLOUD_WITH_LOCAL_ASSIST`
- No new default-on flag
- Missing flag downgrades to shadow_only
- Flag must be checked at every P3 execution entry point

## Hook Placement
Future hook may be attached only at LocalModelExecutor metadata/receipt layer:
- Hook must not choose route
- Hook must not change topology
- Hook must not mutate candidate selection
- Hook must only attach metadata to existing response

## Receipt Fields Required

| Field | Description |
|-------|-------------|
| `p3_l_enabled` | Whether P3-L hook is active |
| `p3_l_authority` | Hook authority level |
| `p3_l_env_guard_present` | Whether env guard is set |
| `p3_l_dry_run_only` | Whether hook is dry-run only |
| `p3_l_provider_request_built` | Whether provider request was built |
| `p3_l_provider_invoked` | Whether provider was invoked |
| `p3_l_network_invoked` | Whether network was invoked |
| `p3_l_local_model_invoked` | Whether local model was invoked by P3 |
| `p3_l_patch_apply_invoked` | Whether patch was applied by P3 |
| `p3_l_runtime_behavior_changed` | Whether runtime behavior changed |
| `p3_l_full_verifier_required` | Whether full verifier is required |
| `p3_l_claim_gate_required` | Whether claim gate is required |
| `p3_l_claim_eligible` | Whether claim is eligible |
| `p3_l_public_claim_allowed` | Whether public claim is allowed |
| `p3_l_production_ready` | Whether production ready |
| `p3_l_blocked_reasons` | List of blocked reasons |

## Blockers

The following must block P3-L hook:

1. `provider_invoked=true`
2. `network_invoked=true`
3. `local_model_invoked=true`
4. `patch_apply_invoked=true`
5. `runtime_behavior_changed=true`
6. `claim_eligible=true`
7. `public_claim_allowed=true`
8. `production_ready=true`
9. `full_verifier_required=false`
10. `claim_gate_required=false`

## Next Package
P3-L2 Dry-Run Receipt Block Builder
