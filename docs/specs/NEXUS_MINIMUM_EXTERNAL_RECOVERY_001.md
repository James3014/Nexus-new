---
artifact_authority: implementation_contract
owner: James Chen
status: active
issue: 1218
mode: brownfield
---

# Nexus Minimum External Recovery 001

## Purpose

This contract defines the smallest recovery seam used only when the normal
governance plane is itself unavailable. It is not a second governance system
and it does not execute effects.

FAILED_NORMAL_GOVERNANCE -> fresh external Owner exact grant -> independent
exact-subject evidence -> one bounded effect -> physical readback -> normal
governance restored.

## Mandatory inputs

A recovery decision requires exact repository, subject and effect identity; a
fresh external Owner grant; one-shot and expiry bounds; independent evidence
for the same subject/effect; proof that normal governance is unavailable; and
durable prior-effect state.

The evaluator returns only DENY, RECONCILE_ONLY, or
ALLOW_ONE_BOUNDED_EFFECT. OUTCOME_UNKNOWN is always RECONCILE_ONLY and never
retry authority. A consumed identity is replay-denied.

## Explicit non-dependencies

The recovery contract does not require Task Card bootstrap, standing-grant
issuance, model probe, Workforce Admission, CapabilityPlanner, normal
merge-lane gate, Gateway mutation authority, or a Core mutation session.
Those components remain unchanged for normal work.

## Non-authority

The evaluator does not mutate source, Git refs, GitHub policy, merge state,
runtime, routing, Workforce, Task Cards, Gateway/Core state, or standing
grants. ALLOW_ONE_BOUNDED_EFFECT is only a bounded precondition result for the
external effect named in the grant.

## G0 fixtures

G0 contains one negative-control fixture covering missing, mismatched, expired,
consumed and ambiguous prior-effect variants; one positive controlled fixture
where normal governance is unavailable and exact Owner grant plus independent
evidence permits one bounded effect; and a normal-path control proving recovery
is denied when normal governance is available.

No permanent emergency integration subsystem is introduced.
