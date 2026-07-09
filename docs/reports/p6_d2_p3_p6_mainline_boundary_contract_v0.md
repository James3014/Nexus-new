# P6-D2 P3/P6 Mainline Boundary Contract

## Status: P6_D2_P3_P6_MAINLINE_BOUNDARY_CONTRACT_PASS

## Boundary Table

| P6 Can Do | Value |
|-----------|-------|
| influence_candidate_count | true (env guard only) |
| disable_cloud | true (env guard only) |
| force_local_only | true (env guard only) |
| mark_solved | **false** |
| mark_claim_eligible | **false** |
| set_public_claim_allowed | **false** |
| override_p4_verifier | **false** |
| override_p3_topology | **false** |
| override_p5_selection | **false** |

## Required Infrastructure

- env_guard=true
- receipt=true
- monitor=true
- canary_gate=true

## Statements

- P6 cannot set solved/claim_eligible/public_claim_allowed
- P6 cannot override P4/P3/P5
- No P3 files changed
- No runtime behavior changed
