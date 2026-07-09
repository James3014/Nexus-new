# P3-M5 Real Provider Approval Checklist ADR

## Status
**ADR-DRAFT — NO APPROVAL GRANTED**

## Purpose
Define conditions for future real-provider experiment. No approval granted by this ADR.

## Required Preconditions

| Precondition | Status |
|--------------|--------|
| M1 strict schema pass | ✅ Complete |
| M2 executor hook strict tests pass | ✅ Complete |
| M3 strict evidence matrix pass | ✅ Complete |
| M4 provider readiness contract pass | ✅ Complete |
| P6 handoff contract reviewed | Pending |
| P2 Apply/Hash/Anchor Truth required | ✅ Complete |
| P4 verifier/claim gate required | ✅ Complete |

## Required Human Approvals

| Approval | Required |
|----------|----------|
| Provider kind | Yes |
| Model name | Yes |
| API key handling | Yes |
| Network boundary | Yes |
| Cost budget | Yes |
| Timeout budget | Yes |
| Data redaction policy | Yes |
| Rollback plan | Yes |
| Test-only task set | Yes |

## First Experiment Allowed Shape

1. Env-guarded only
2. Dry-run first
3. One synthetic provider fixture
4. Then one human-approved network smoke
5. No patch apply
6. No solved claim
7. No public claim

## Required Abort Triggers

| Trigger | Action |
|---------|--------|
| Provider/network invoked without guard | Abort |
| API key logged | Abort |
| Runtime behavior changed | Abort |
| Patch apply invoked | Abort |
| public_claim_allowed=true | Abort |
| production_ready=true | Abort |
| Verifier/claim gate not required | Abort |
| Cost/timeout exceeded | Abort |

## Explicit Non-Claims

- Not provider implemented
- Not cloud_with_local_assist implemented
- Not production ready
- Not public claim eligible

## Next Recommended Package
**P3-N1 Synthetic Provider Fixture** — only after approval
