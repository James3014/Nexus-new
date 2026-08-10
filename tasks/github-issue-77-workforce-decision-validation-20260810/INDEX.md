---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-77-workforce-decision-validation-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/77
baseline_main: 84eaa6886e0388a4e15f5b837c89e37768b14307
ordered_cards:
  - 01-fail-closed-admission-decision.md
current_frontier: null
completed_cards:
  - 01-fail-closed-admission-decision.md
blocked_cards: []
AUTO_CHAIN: false
---

# Issue 77 WorkforceAdmissionDecision Fail-Closed Validation

Make `WorkforceAdmissionDecision` fail closed when `decision` is not an
`AdmissionDecision` enum value, at both the constructor and raw-mapping
runtime boundaries.

Pre-mutation card SHA-256:
`586ddf57eb470430666a87954e651416197f9917ed3892ff16eefc112c48e71c`.

Owner directive comment:
https://github.com/James3014/Nexus-new/issues/77#issuecomment-5235662125

Terminal marker: `WORKFORCE_ADMISSION_DECISION_VALIDATION_PROVEN`.

Completion receipt:

- Task Card authorization commit: `24bc0cc6c`
- implementation head: `95f2b0d56`
- PR: https://github.com/James3014/Nexus-new/pull/PENDING
- constructor boundary fails closed on forged `decision` values
- raw-mapping `_decision_dict` boundary fails closed on malformed mappings
- valid ALLOW/BLOCK/ESCALATE behavior unchanged
- 35 focused + 84 Golden/contract/loader/unified + 36 #7 admission/dispatch
  orchestrator tests pass; contracts/services sweep identical failure sets
  (117 pre-existing env) base vs Candidate
- Ruff zero net-new; Pyright prod/runtime 0 errors, test 1 = base 1
- `git diff --check` clean; reached `CANDIDATE_PR_READY`

