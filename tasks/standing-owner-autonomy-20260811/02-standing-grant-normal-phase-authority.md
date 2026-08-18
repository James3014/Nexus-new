---
artifact_authority: current
owner: James Chen
status: active
source_issue: "#163"
supersedes:
  - tasks/github-issue-163-merge-authority-20260813/INDEX.md
  - tasks/github-issue-163-merge-authority-20260813/00-owner-merge-slot-canonicalization.md
  - tasks/github-issue-163-standing-grant-decision-20260813/INDEX.md
  - tasks/github-issue-163-standing-grant-decision-20260813/00-standing-grant-decision.md
AUTO_CHAIN: false
---

# Current standing-grant normal-phase authority

The current Owner standing grant is machine-bound to the exact repository,
Goal, coordinator, source thread, allowed GitHub actions, issuance, expiry, and
revocation state. A valid grant that explicitly covers normal GitHub protected
merge remains valid across the ordinary phases from Task Card through main
readback and Issue reconciliation. Reaching the merge phase alone is not a
new authority boundary and must not trigger redundant Owner authorization.

The grant authorizes only the exact covered action. Independent acceptance,
exact PR/head/base binding, required checks, branch protection,
scope/deletion checks, review resolution, and expected-head/CAS remain separate
mandatory verification gates. Expiry, revocation, tampering, wrong repository,
Goal, coordinator, thread, or action, scope widening, security weakening,
release/production effects, new irreversible effects, and genuine external
platform approval requirements fail closed and require the corresponding new
decision. External platform approval is reported as
`PLATFORM_APPROVAL_REQUIRED`, not as a grant mismatch.

`MERGE_INTENT` is immutable evidence and does not replace verification. This
artifact authorizes no delegated-worker self-merge, approval, integration,
protected-ref push, release, or production/public claim.
