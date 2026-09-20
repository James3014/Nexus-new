# Task Card: Issue #982 Wave B3 — governed OpenCode runtime witness

artifact_authority: current
task_id: `issue-982-wave-b3-governed-opencode-witness-20260919`
campaign_id: `github-issue-982-wave-b-20260919`
owner: James Chen
status: BLOCKED_PENDING_B1_B2
contract_kind: TRACKED_TASK_CARD
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Source Spec

- path: `docs/specs/ISSUE_982_WAVE_B_GOVERNED_TOOL_AUTHORITY_001.md`
- contract-branch blob SHA: `a402d709800aad4d4282b6006343d5d4c4ca65aa`
- Issue: `James3014/Nexus-new#982`

## Objective

After the accepted Nexus-new B1 implementation and accepted DevSpace B2 implementation are both integrated and the live DevSpace runtime is rebound to the accepted source, prove one real `NEXUS_GOVERNED` OpenCode tool-authority intervention and one fail-closed widening control.

This card authorizes only the Wave B evidence closure. It does not authorize G4.

## Hard prerequisites

Before any canary effect:

1. B1 Nexus governed tool-authority source is merged on canonical Nexus-new main.
2. B2 DevSpace grant/tool cross-validation source is merged on canonical DevSpace main.
3. live DevSpace source/build is cryptographically/factually rebound to the accepted B2 source.
4. current authoritative DevSpace role is converged with no unresolved cutover.
5. current OpenCode catalog/preflight lists `opencode/big-pickle` as usable.
6. current Nexus main containing this card, the authority artifact, and the exact tracked grant is bound by DevSpace grant resolution.
7. no unresolved earlier canary effect with the same task/attempt identity exists.

## Allowed Nexus-new artifact paths

Only Wave B canary authority/evidence artifacts under:

- `tasks/github-issue-982-wave-b-20260919/canary/`

Expected tracked grant path:

- `tasks/github-issue-982-wave-b-20260919/canary/opencode-readonly-grant.json`

The grant must be generated from the accepted B1 deterministic builder/policy, not hand-edited after hashing.

The authority path for the grant is this Task Card unless a later explicit contract delta names another tracked authority artifact.

## Positive arm contract

Provider/model:

- provider: `opencode`
- model: `opencode/big-pickle`
- authorityMode: `NEXUS_GOVERNED`

Authorized ceiling:

- `workspace.read`
- `workspace.search_text`
- `workspace.search_paths`
- `workspace.list`

The task statement must be an explicit single-file/read-only request so the accepted canonical JIT implementation selects exactly:

- `workspace.read`

Manifest:

- schema: `devspace.tool_projection_manifest.v1`
- namespace: `devspace.tool_intent.v1`
- authority: `NEXUS_GOVERNED / nexus`
- candidateTools: exact four-tool READ_ONLY ceiling
- selectedTools: `workspace.read`
- orderingMode: `ORDER_INDEPENDENT`

No `workspace.mutate` or `process.execute` intent is authorized.

## Required positive evidence

Capture and bind:

- canonical Nexus main revision;
- tracked grant path and raw SHA-256;
- authority path and raw SHA-256;
- Planner decision hash / plan hash / tool policy hash from tracked grant tool authority;
- DevSpace GitHub accepted revision;
- live DevSpace source/build/server/capability manifest;
- exact OpenCode catalog generation;
- DevSpace durable agent id;
- exact provider session id;
- exact persisted `NEXUS_GOVERNED` execution contract;
- exact persisted grant ref;
- exact four-tool authorized ceiling;
- exact one-tool selected set;
- provider-owned OpenCode native permission construction showing `read=allow` and excluded search/list capabilities denied;
- reconciliation proving no repository mutation.

## Negative widening control

Using a fresh attempt identity and the same tracked grant authority:

- submit an execution ceiling and/or manifest that contains an intent outside the tracked grant `toolAuthority.authorizedToolCeiling`;
- DevSpace must reject before semantic provider execution;
- no provider session may start;
- no repository mutation may occur;
- no governed-to-direct fallback is allowed.

Do not widen the tracked grant itself merely to create the negative test.

## Exit

Wave B may be marked complete only when:

```text
B1_NEXUS_SOURCE_MERGED=TRUE
B2_DEVSPACE_SOURCE_MERGED=TRUE
DEVSPACE_RUNTIME_BOUND_TO_B2=TRUE
NEXUS_GOVERNED_OPENCODE_POSITIVE_WITNESS=TRUE
GOVERNED_TOOL_AUTHORITY_WIDENING_FAIL_CLOSED=TRUE
CANARY_REPOSITORY_MUTATION=NONE
WAVE_B=COMPLETE
G4=NOT_STARTED
AUTO_CHAIN=false
```

Write one durable #982 receipt with exact evidence, then STOP.
