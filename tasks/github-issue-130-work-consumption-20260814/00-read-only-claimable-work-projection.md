---
task_id: github-issue-130-read-only-claimable-work-projection
issue: 130
repository: James3014/Nexus-new
baseline_revision: eb668fb76f0c30d8f025db42cdb8e320d556c037
status: ACTIVE
readiness_marker: 130A_READY_FOR_GOVERNED_CANDIDATE_PUBLICATION
AUTO_CHAIN: false
claim_ceiling: WORK_CONSUMPTION_READ_ONLY_PROJECTION_CANDIDATE_PR_ONLY
implementation_files:
  - nexus/orchestrator/work_consumption.py
  - tests/nexus/orchestrator/test_work_consumption.py
governance_files:
  - tasks/github-issue-130-work-consumption-20260814/INDEX.md
  - tasks/github-issue-130-work-consumption-20260814/00-read-only-claimable-work-projection.md
allowed_files:
  - nexus/orchestrator/work_consumption.py
  - tests/nexus/orchestrator/test_work_consumption.py
  - tasks/github-issue-130-work-consumption-20260814/INDEX.md
  - tasks/github-issue-130-work-consumption-20260814/00-read-only-claimable-work-projection.md
max_files: 4
authorized_deletions: []
worker_may_commit: false
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
worker_may_merge: false
external_candidate:
  worker: opencode_deepseek_v4_flash
  model: opencode/deepseek-v4-flash-free
  lane: bounded_candidate_generation
  mutation_intent: false
  diff_sha256: eb6938826d5517f36c9eb0617d560f0b4ac9a641748ff9e123d5beaf74fec674
---

# 130A — read-only claimable-work projection

## Authority and prerequisite

Current Owner authority freezes this single bounded slice. PR #235's atomic
Issue #129 primitive is physically present on baseline `main`; PR #241's
terminal metadata is not a semantic prerequisite for this read-only slice.
The delegated external Candidate cannot approve, integrate, merge, close, or
claim runtime, release, or production truth.

## Objective

Implement only the read-only normalized claimable-work discovery/filtering
slice of Issue #130.

## Required semantics

- Consume a normalized work-item projection, never raw GitHub prose.
- Hard eligibility only: `READY_NOW`, compatible role, autonomous claim intent,
  `REPO_ENFORCED`, prerequisites satisfied, admission not forbidden, no active
  claim/PR/mutation owner, and realm/provider not blocked.
- Unknown or malformed input fails closed.
- Listing creates no ownership, state write, or lock and never calls
  `acquire_work_claim()` or `claim_work()`.
- Ordering is explicit direct successor, then `P0 > P1 > P2`; unresolved
  equal-priority items remain tied.
- No learned score, scheduler, Router, or Planner change.

## Forbidden

- Changing Issue #129 claim authority.
- New lock, store, scheduler, or router.
- Worker-specific GitHub parser authority.
- Review claiming or `candidate_ready`.
- Approval, integration, merge, Issue closure, runtime, or release.
- Scope widening or file deletion.

## Verification

```text
uv run pytest -q tests/nexus/orchestrator/test_work_consumption.py
git diff --check
```

Audit the exact four allowed files, zero deletions, and prove listing never
invokes `acquire_work_claim` or `claim_work`.

## Exit

A GitHub Candidate PR containing exactly two governance files and the two
frozen implementation files, with zero deletions and the external
implementation diff unchanged. Independent acceptance remains pending.

`AUTO_CHAIN=false`. Claim ceiling:
`WORK_CONSUMPTION_READ_ONLY_PROJECTION_CANDIDATE_PR_ONLY`.
