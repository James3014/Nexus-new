# Task Card: G7 Nexus-Governed Coexistence Fresh Authority Rebind

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

G7-1 rebind: re-establish a fresh, verifiable, current GitHub `main`-bound `NEXUS_GOVERNED` read-only authority bundle for the G7 `NEXUS_GOVERNED / OWNER_DIRECT` coexistence campaign, under execution-time fresh canonical base, forming an isolated Candidate for later live gates. This round only creates the authority-artifact Candidate and stops; it does not launch a governed worker, run the bad-grant live attempt, run the OWNER_DIRECT witness, reconcile physically, or mark G7 complete.

## Bound live attempt (fresh rebind)

- attempt_id: `g7-governed-live-attempt-20260907-01`
- target DevSpace base (devspaceBaseRevision): `491660f2a95eb04e68683e1648c2f9a20744a52a`
- profile: `opencode-muse-high-review`
- dispatch_intent_hash: `e10f08fc344823a6d77899d33d7ee215d8a580c5e614efb572be25fd66740d07`
- read scope: `AGENTS.md`
- write scope: empty
- effect ceiling: `READ_ONLY`
- claim ceiling: `RESULT_RETURNED`

## Dispatch intent

```json
{"taskId":"g7-nexus-governed-coexistence-20260906","attemptId":"g7-governed-live-attempt-20260907-01","objective":"Read one bounded repository artifact and return evidence under fresh canonical Nexus authority.","roleIntent":"EVIDENCE_COLLECTOR","readScope":["AGENTS.md"],"writeScope":[],"exclusiveOwnership":false,"forbiddenChanges":["Do not modify files or claim verification, acceptance, merge, release, or production authority."],"acceptanceCriteria":["Return the collaboration repository identifier and default branch from AGENTS.md without modifying the workspace."],"verificationRequired":false,"expectedEvidence":["durable agent status","physical workspace reconciliation"],"claimCeiling":"RESULT_RETURNED"}
```

## Allowed authority artifacts

- `tasks/dev-mcp-governed-coexistence-g7-20260906/INDEX.md`
- `tasks/dev-mcp-governed-coexistence-g7-20260906/00-g7-nexus-governed-coexistence.md`
- `tasks/dev-mcp-governed-coexistence-g7-20260906/g7-execution-grant-contract.json`

No repository implementation file is authorized for mutation by the governed live attempt, and no such file is mutated by this rebind round.

## Negative-control contract (next gate)

The bad-grant negative control must be a single-variable tamper of `grantSha256` only, so that the only failing binding is the stored grant bytes reference. It MUST:

- keep attempt binding lawful: `attemptKey == dispatchIntent.attemptId`
- keep task, attempt, base, profile, authority path/hash, time, repository, and dispatchIntent all lawful (not the failure variable)
- tamper only `grantSha256` in the voter/ref used at pre-launch
- expect `PRE_LAUNCH_REJECT` via the exact bad-grant hash validation branch
- produce zero provider launch, zero durable governed worker, zero workspace mutation

Do NOT fake the bad-grant rejection with attempt mismatch, stale HEAD, expired grant, wrong profile, or wrong task.

## No-fallback contract

- `NEXUS_GOVERNED` admission failure => fail closed; it is NOT a fallback trigger to `OWNER_DIRECT`.
- `NEXUS_GOVERNED` failure != `OWNER_DIRECT` fallback.
- An unrelated, independently authorized `OWNER_DIRECT` attempt must remain independently admissible; Nexus authority failure must not globally lock DevSpace.

## Acceptance

1. The exact Task Card and execution grant are tracked on current GitHub `main` at `491660f2a95eb04e68683e1648c2f9a20744a52a` (fresh execution-time canonical base).
2. DevSpace independently resolves current GitHub `main`, fetches the exact tracked grant and this authority artifact, verifies their SHA-256 bytes, and accepts the bound `NEXUS_GOVERNED` attempt before worker launch.
3. The governed attempt is bound to the exact task/attempt/base/profile/DispatchIntent/write scope/effect ceiling/claim ceiling and cannot silently downgrade to `OWNER_DIRECT`.
4. A tampered or mismatched grant reference (single-variable `grantSha256` tamper) is rejected before worker launch and creates no durable governed worker and no workspace mutation.
5. An unrelated `OWNER_DIRECT` attempt remains independently admissible; Nexus authority failure must not globally lock DevSpace.
6. Physical reconciliation for the governed attempt shows no workspace mutation.
7. Authority admission PASS is separate from provider result PASS and from gate COMPLETE. A provider timeout or protocol error MAY preserve evidence that admission previously passed but MUST NOT mint `G7 COMPLETE`; it is not an acceptance-conflation.

## Forbidden scope

- No source-code, schema, migration, lifecycle, Planner, Workforce Admission, standing-grant, deployment, release, or production mutation.
- No governed-to-direct fallback.
- No worker approval, integration, merge, release, or production authority.
- No widening of the grant beyond this one read-only attempt.
- This rebind round performs NO live worker launch, NO negative-control execution, NO OWNER_DIRECT witness, NO physical live reconciliation, and NO G7 final completion.

## Exit criterion

This round completes when a fresh G7 authority Candidate exists whose base equals execution-time current GitHub `main`, all authority artifacts are internally hash-consistent, focused validation is green, and non-main branch/PR evidence is available when authorized. Marking the full campaign `G7 COMPLETE` is deferred to the later independent gates: G7-2 current-main authority readback, G7-3 positive `NEXUS_GOVERNED` admission, G7-4 bad-grant single-variable rejection, G7-5 `OWNER_DIRECT` coexistence witness, G7-6 no silent fallback, G7-7 physical reconciliation / no unexpected mutation.
