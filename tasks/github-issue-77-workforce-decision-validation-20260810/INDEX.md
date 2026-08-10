---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-77-workforce-decision-validation-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/77
baseline_main: 84eaa6886e0388a4e15f5b837c89e37768b14307
ordered_cards:
  - 01-fail-closed-admission-decision.md
current_frontier: 01-fail-closed-admission-decision.md
completed_cards: []
blocked_cards: []
AUTO_CHAIN: false
---

# Issue 77 WorkforceAdmissionDecision Fail-Closed Validation

Make `WorkforceAdmissionDecision` fail closed when `decision` is not an
`AdmissionDecision` enum value, at both the constructor and raw-mapping
runtime boundaries.

Pre-mutation card SHA-256: `586ddf57eb470430666a87954e651416197f9917ed3892ff16eefc112c48e71c`.

Owner directive comment:
https://github.com/James3014/Nexus-new/issues/77#issuecomment-5235662125

Terminal marker: `WORKFORCE_ADMISSION_DECISION_VALIDATION_PROVEN`.
