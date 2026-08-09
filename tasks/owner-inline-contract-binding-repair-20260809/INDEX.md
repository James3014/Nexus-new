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
| 0 | `OWNER-INLINE-CONTRACT-BINDING-REPAIR-01` | `00-OWNER-INLINE-CONTRACT-BINDING-REPAIR-01.md` | ACTIVE | accepted P4 Candidate `2373deb1666db581932a4f19d6d0d1812cc680f8` |

## Governance

- This is a prerequisite repair for the already accepted P4 Candidate; it does
  not supersede or modify that Candidate.
- The worker may create one scoped Candidate commit only.
- Approval, integration, Gateway reload, cleanup, push, and release remain
  primary/Owner authorities.
- `AUTO_CHAIN=false`.
