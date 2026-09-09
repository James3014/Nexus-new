---
campaign_id: github-issue-130-work-consumption-20260814
issue: 130
repository: James3014/Nexus-new
status: ACTIVE
baseline_main: eb668fb76f0c30d8f025db42cdb8e320d556c037
current_frontier: 00-read-only-claimable-work-projection.md
readiness_marker: 130A_READY_FOR_GOVERNED_CANDIDATE_PUBLICATION
claim_ceiling: WORK_CONSUMPTION_READ_ONLY_PROJECTION_CANDIDATE_PR_ONLY
AUTO_CHAIN: false
authorized_deletions: []
rejected_candidate: d2a6d1ce594131bb5b057eb868e911e98a179875
repair_candidate: 3b83b9e517b7946d6cd03519a62242d5bbd8b502
owner_waiver:
  waiver_id: OWNER_WAIVER
  head: 3b83b9e517b7946d6cd03519a62242d5bbd8b502
  receipt_requirement: WAIVED_FOR_THIS_CANDIDATE_ONLY
  acceptance: EXTERNAL_PENDING
---

# Issue #130 — bounded work-consumption slice

The physical atomic work-claim prerequisite from Issue #129 is present on
`main` at `eb668fb76f0c30d8f025db42cdb8e320d556c037` through PR #235. This
readiness applies only to `130A_READ_ONLY_CLAIMABLE_WORK_PROJECTION`; the full
Issue #130 API remains outside this slice.

- Current frontier: `00-read-only-claimable-work-projection.md`
- Durable readiness marker: `130A_READY_FOR_GOVERNED_CANDIDATE_PUBLICATION`
- Implementation scope: exactly two source/test files named by the active card.
- Listing is read-only and must never acquire ownership.
- `AUTO_CHAIN=false`.
- Claim ceiling: `WORK_CONSUMPTION_READ_ONLY_PROJECTION_CANDIDATE_PR_ONLY`.
- Owner waiver: `OWNER_WAIVER` at exact PR head
  `3b83b9e517b7946d6cd03519a62242d5bbd8b502`,
  `receipt_requirement=WAIVED_FOR_THIS_CANDIDATE_ONLY`; original rejected
  candidate `d2a6d1ce…`, repair candidate `3b83b9e5…`, acceptance external and
  pending.
