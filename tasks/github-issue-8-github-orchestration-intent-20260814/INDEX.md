# Issue #8 GitHub orchestration intent (M4)

status: ACTIVE
authority: Owner-authorized external bootstrap
auto_chain: false
base: a74d838cc6bb14af47ce79207181c12a1aed1d35
allowed_files: exactly six new files
forbidden: network, subprocess, GitHub mutation, merge/push to main, governance/lifecycle/workforce changes
claim_ceiling: m4_merge_eligible_and_intent_ready_only

The implementation is pure and intent-only. It binds immutable repository,
pull-request, evidence, review, check, diff, acceptance and impact hashes and
fails closed on freshness or scope drift.
