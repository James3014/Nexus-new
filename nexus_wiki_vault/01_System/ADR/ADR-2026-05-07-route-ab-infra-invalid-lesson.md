---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR-2026-05-07 Route A/B Infra Invalid Lesson

## Context

On 2026-05-07 we ran a 3-task same-model Flash A/B for route-cost validation:

- `nexus-value-hidden-001`
- `nexus-value-repair-002`
- `nexus-value-gov-001`

The `with_nexus` arm completed successfully on all three tasks, but the `without_nexus` arm produced only infra-invalid outcomes:

- `quota_exhausted`
- `timeout_before_model_call`

This means the run was not eligible to support a public before/after claim, even though the Nexus arm itself remained healthy.

## Lesson

Same-model A/B should not be interpreted as a product win unless both arms are eligible.

Infra-invalid bare-arm failures create a false sense of improvement if we only look at the Nexus side completing successfully. The correct interpretation is:

- route/runtime closure stayed healthy
- public A/B evidence is incomplete

## Decision

For route-cost and route-quality validation:

1. Treat any `infra_invalid_reason` in either arm as a blocked public claim.
2. Require a quota and timeout preflight before launching the bare arm.
3. Prefer a small Nexus-only self-test first, then run same-model A/B only when the bare arm is likely to be callable.
4. Do not expand task count when the first A/B attempt is infra-invalid; rerun under restored quota first.

## Operational Follow-up

- Keep Nexus self-test as the first gate for route tuning.
- Add a rerun checklist item for bare-arm availability before same-model A/B.
- Continue reporting `infra_invalid_reason` explicitly in route-cost reports.
- Keep `git add` and `git commit` sequential in the same repository to avoid transient `.git/index.lock` collisions during closeout.
