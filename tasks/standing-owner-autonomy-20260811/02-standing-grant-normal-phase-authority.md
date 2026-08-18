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

# Current standing-grant normal-phase authority contract

This file is a normative CURRENT AUTHORITY CONTRACT. It does not itself attest
that a standing grant exists or issue a grant. It does not itself authorize a merge. A standing
grant is current and valid only when a separate physical, machine-bound Owner receipt contains all of these exact bindings: `grant_id`, `owner`, `primary coordinator`, `repository`, `source_thread`, `Goal`, an allowed action set explicitly including `GITHUB_MERGE` for a protected merge, `issued_at`, `expiry`, `revocation_state` (or an equivalent revocation rule), and `context_hash`. The receipt must be independently read back and verified
against the current execution context; this document is not that receipt.

After that exact receipt matches, a valid grant that explicitly covers normal
GitHub protected merge remains valid across the ordinary phases from Task Card through main readback and Issue reconciliation. Reaching the merge phase alone
is not a new authority boundary and must not trigger redundant Owner
authorization. This contract does not authorize a merge by itself: the exact
merge gate and all independent acceptance, repository/PR/head/base, checks,
branch-protection, scope, deletion, and expected-head/CAS evidence remain
mandatory.

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
