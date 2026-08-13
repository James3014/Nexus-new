---
campaign_id: github-issue-129-atomic-work-claim-20260813
issue: 129
repository: James3014/Nexus-new
baseline_main: a74d838cc6bb14af47ce79207181c12a1aed1d35
status: ACTIVE
current_frontier: 00-atomic-work-claim.md
AUTO_CHAIN: false
owner: James Chen
owner_authorization: direct Owner authorization for persistent claim subrecord/recovery under existing SelfHostedTaskService .state.lock
shared_file_gate: SERIALIZE_MUTATION_AFTER_PR226
implementation_status: CARD_ONLY_REBOUND
claim_ceiling: CLAIM_PROTOCOL_CANDIDATE_PR_ONLY
---

# Issue #129 atomic Ready-Issue work claim

Only `00-atomic-work-claim.md` is active. The campaign stops at a verified
Candidate PR. It does not activate Issue #130 or authorize acceptance, merge,
runtime activation, release, or production claims.

The card is rebound to exact `main` `a74d838cc6bb14af47ce79207181c12a1aed1d35`.
Implementation remains blocked until the coordinator releases the shared
`nexus/orchestrator/self_hosted_task_service.py` and
`tests/nexus/orchestrator/test_self_hosted_task_service.py` gate after PR226;
this rebind changes no production or test file.
