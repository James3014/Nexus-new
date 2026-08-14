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
  diff_sha256: bca5018bc196f187d99d65ccb32c62369d40be684c8d19de9fbca2e63e64e3b7
rejected_candidate: d2a6d1ce594131bb5b057eb868e911e98a179875
repair_candidate: 3b83b9e517b7946d6cd03519a62242d5bbd8b502
owner_waiver:
  waiver_id: OWNER_WAIVER
  head: 3b83b9e517b7946d6cd03519a62242d5bbd8b502
  receipt_requirement: WAIVED_FOR_THIS_CANDIDATE_ONLY
  acceptance: EXTERNAL_PENDING
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

## Owner waiver and candidate lineage

Owner explicitly issued: `OWNER_WAIVER` for PR #271 at exact head
`3b83b9e517b7946d6cd03519a62242d5bbd8b502` with
`receipt_requirement=WAIVED_FOR_THIS_CANDIDATE_ONLY`. The receipt requirement
is waived for this candidate only; acceptance remains external and pending.

- Original rejected candidate: `d2a6d1ce594131bb5b057eb868e911e98a179875`.
- Repair candidate (current PR head): `3b83b9e517b7946d6cd03519a62242d5bbd8b502`.
- Final implementation-only diff SHA-256 (recomputed, method: `git diff
  <base> <head> -- nexus/orchestrator/work_consumption.py
  tests/nexus/orchestrator/test_work_consumption.py | shasum -a 256` over base
  `eb668fb76f0c30d8f025db42cdb8e320d556c037`):
  `bca5018bc196f187d99d65ccb32c62369d40be684c8d19de9fbca2e63e64e3b7`.
- The previously recorded value `eb6938826d5517f36c9eb0617d560f0b4ac9a641748ff9e123d5beaf74fec674`
  was the external harness artifact hash for the rejected candidate and is not
  reproducible from git objects alone; it is preserved here as historical
  evidence, not asserted as the current head binding.

`AUTO_CHAIN=false`. Claim ceiling:
`WORK_CONSUMPTION_READ_ONLY_PROJECTION_CANDIDATE_PR_ONLY`.
