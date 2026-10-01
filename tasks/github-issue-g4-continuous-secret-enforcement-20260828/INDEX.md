# G4 Continuous Secret Enforcement — Campaign Index

- Repository: `James3014/Nexus-new`
- Source Issue: #659
- Security Gate: G4
- Status: `ACTIVE`
- Current frontier: `TASK-G4-659-01`
- Baseline: `45d39c6ca7940ac42752d2c6e5bba41bf6b968da`
- Claim ceiling: `G4_CONTINUOUS_SECRET_ENFORCEMENT_CANDIDATE_ONLY`
- `AUTO_CHAIN=false`

## Scope

This campaign implements only the G4 carve-out explicitly left by G2/#598: continuous triggering of the existing full published-history secret audit and, after independent acceptance/merge plus exact-main audit success, addition of the stable audit check to the existing `main` ruleset without removing existing requirements.

## Task graph

`TASK-G4-659-01` has no task dependency and is the only active implementation card. Protected merge, ruleset mutation, Issue closure, release/runtime claims, and credential rotation are not worker authority.

## Completion boundary

G4 is complete only after the source Candidate is independently accepted and protected-merged, the exact merged `main` revision passes the Git History Secret Audit, the current `main` ruleset requires that observed audit check in addition to its pre-existing checks, and both ruleset and `main` are read back. Residual risk remains `HISTORICAL_CREDENTIAL_ROTATION_UNVERIFIED`.