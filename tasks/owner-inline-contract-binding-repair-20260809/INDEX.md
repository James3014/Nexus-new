# Campaign Index: owner-inline-contract-binding-repair-20260809

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Repair the exact OWNER_INLINE approval identity seam that currently binds
Candidate approval and integration to the service task-contract hash instead of
the canonical nested Owner Inline contract hash. Preserve tracked Task Card
behavior and every existing approval/integration gate.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `OWNER-INLINE-CONTRACT-BINDING-REPAIR-01` | `00-OWNER-INLINE-CONTRACT-BINDING-REPAIR-01.md` | REJECTED | accepted P4 Candidate `2373deb1666db581932a4f19d6d0d1812cc680f8` |
| 1 | `OWNER-INLINE-CONTRACT-BINDING-REPAIR-02` | `01-OWNER-INLINE-CONTRACT-BINDING-REPAIR-02.md` | REJECTED | rejected Candidate `30c01b759ea5f6b466abd8d7330fd77a4ab8e3ea` |
| 2 | `OWNER-INLINE-CONTRACT-BINDING-REPAIR-03` | `02-OWNER-INLINE-CONTRACT-BINDING-REPAIR-03.md` | ACTIVE | rejected Candidate `f5104f5a8b42be7850c3c6ca4d1adb5b22c497ce` |

## Governance

- This is a prerequisite repair for the already accepted P4 Candidate; it does
  not supersede or modify that Candidate.
- Card 01 was formally rejected because it changed no tests and omitted direct
  service approval revalidation; its durable state and Candidate ref remain
  forensic evidence.
- Card 02 was formally rejected because its partial-approval detection broke
  legacy TRACKED_TASK_CARD architecture flows and its tests did not exercise
  all six production seams with divergent service and Owner Inline hashes.
- The worker may create one scoped Candidate commit only.
- Approval, integration, Gateway reload, cleanup, push, and release remain
  primary/Owner authorities.
- `AUTO_CHAIN=false`.
