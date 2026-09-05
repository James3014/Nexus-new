# Task Card: G7 Nexus-Governed Coexistence Live Acceptance

artifact_authority: current
task_id: `g7-nexus-governed-coexistence-20260906`
owner: James Chen
status: ACTIVE
contract_kind: TRACKED_TASK_CARD
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Objective

Close G7 by proving that DevSpace `OWNER_DIRECT` and `NEXUS_GOVERNED` authority modes coexist without silent fallback or global locking. A fresh canonical Nexus grant must authorize exactly one read-only governed attempt while invalid governed evidence fails closed before worker launch and unrelated direct attempts remain independently admissible.

## Bound live attempt

- attempt_id: `g7-governed-live-attempt-20260906-01`
- target DevSpace base: `8e8e02911c888d4c8a4667d4b5dd13df85c20cfd`
- profile: `opencode-muse-high-review`
- dispatch_intent_hash: `85a40b7cd9ce7eb7a5b157ffbce1895d064d0de57f03fbdc7c30f82651ee9d10`
- read scope: `AGENTS.md`
- write scope: empty
- effect ceiling: `READ_ONLY`
- claim ceiling: `RESULT_RETURNED`

## Dispatch intent

```json
{"taskId":"g7-nexus-governed-coexistence-20260906","attemptId":"g7-governed-live-attempt-20260906-01","objective":"Read one bounded repository artifact and return evidence under fresh canonical Nexus authority.","roleIntent":"EVIDENCE_COLLECTOR","readScope":["AGENTS.md"],"writeScope":[],"exclusiveOwnership":false,"forbiddenChanges":["Do not modify files or claim verification, acceptance, merge, release, or production authority."],"acceptanceCriteria":["Return the collaboration repository identifier and default branch from AGENTS.md without modifying the workspace."],"verificationRequired":false,"expectedEvidence":["durable agent status","physical workspace reconciliation"],"claimCeiling":"RESULT_RETURNED"}
```

## Allowed authority artifacts

- `tasks/dev-mcp-governed-coexistence-g7-20260906/INDEX.md`
- `tasks/dev-mcp-governed-coexistence-g7-20260906/00-g7-nexus-governed-coexistence.md`
- `tasks/dev-mcp-governed-coexistence-g7-20260906/g7-execution-grant-contract.json`

No repository implementation file is authorized for mutation by the governed live attempt.

## Acceptance

1. The exact Task Card and execution grant are tracked on current GitHub `main`.
2. DevSpace independently resolves current GitHub `main`, fetches the exact tracked grant and this authority artifact, verifies their SHA-256 bytes, and accepts the bound `NEXUS_GOVERNED` attempt before worker launch.
3. The governed attempt is bound to the exact task/attempt/base/profile/DispatchIntent/write scope/effect ceiling/claim ceiling and cannot silently downgrade to `OWNER_DIRECT`.
4. A tampered or mismatched grant reference is rejected before worker launch and creates no durable governed worker.
5. An unrelated `OWNER_DIRECT` attempt remains independently admissible; Nexus authority failure must not globally lock DevSpace.
6. Physical reconciliation for the governed attempt shows no workspace mutation.
7. Provider completion is execution evidence only. A provider-layer terminal error after successful governed admission does not mint acceptance authority and does not invalidate the authority-mode coexistence witness when no mutation occurred.

## Forbidden scope

- No source-code, schema, migration, lifecycle, Planner, Workforce Admission, standing-grant, deployment, release, or production mutation.
- No governed-to-direct fallback.
- No worker approval, integration, merge, release, or production authority.
- No widening of the grant beyond this one read-only attempt.

## Exit criterion

`G7_NEXUS_GOVERNED_COEXISTENCE_COMPLETE` only after current-main readback, positive governed admission, bad-grant pre-launch rejection, direct-lane coexistence evidence, and physical no-mutation reconciliation are all observed.
