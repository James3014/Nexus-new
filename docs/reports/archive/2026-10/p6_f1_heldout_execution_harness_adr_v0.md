# P6-F1 Heldout Execution Harness ADR

## Decision

P6 heldout execution requires human approval. Current task is design-only. No heldout tasks are executed. No runtime default changes.

## Preconditions

- E1 validator passes
- E2 normalized fixture exists and passes
- E3 monitor gates pass on synthetic evidence
- E4 canary severity mapping exists
- E5 P3 handoff contract exists
- P4 verifier/claim gate remains final authority

## Heldout Execution Modes

1. plan_only — offline planning only
2. dry_run — deterministic offline execution
3. stubbed_execution — mock execution for validation
4. human_approved_real_execution — requires explicit approval

## Hard Abort Criteria

- public_claim_allowed=true
- production_ready=true
- solved=true without P4 verifier/claim gate
- unknown quota treated as healthy
- cloud allowed in disallowed states
- constrained candidate count below 2
- runtime mutation without env guard
- missing receipt

## Non-Authorities

- P6 cannot mark solved
- P6 cannot mark claim eligible
- P6 cannot set public claim
- P6 cannot override P3 topology
- P6 cannot override P4 verifier
- P6 cannot override P5 selection
