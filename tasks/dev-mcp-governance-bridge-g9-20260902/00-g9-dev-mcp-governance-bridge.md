# Task Card 00: G9 Dev MCP Governance Bridge

## Identity

- task_id: `g9-dev-mcp-governance-bridge-20260902`
- campaign_id: `dev-mcp-governance-bridge-g9-20260902`
- artifact_authority: current
- status: COMPLETE
- owner: James Chen
- authorization: owner explicitly instructed the controller on 2026-09-02 to continue until G10 is complete and to resolve intermediate blockers without stopping
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Implement the G9 Nexus-to-Dev-MCP governance bridge so DevSpace can consume one immutable, already-authorized Nexus execution grant and mechanically enforce it for `NEXUS_GOVERNED` execution without becoming a planner, Workforce Admission authority, verifier, acceptance authority, merge authority, release authority, or a second grant issuer.

The bridge must fail closed on missing, stale, revoked, tampered, mismatched, or non-canonical Nexus evidence and must never silently fall back from `NEXUS_GOVERNED` to `OWNER_DIRECT`.

## Current bound baselines

- Nexus canonical GitHub main at card creation: `9dffad79ea30d6f2a1b8bee64ac1048e1ae59f35`
- DevSpace implementation base: `db7d063681364c06e0ac3425451f53af887ca490`
- Live Dev MCP observed build/source before implementation: `devspace-1.0.7-db7d0636` / `db7d063681364c06e0ac3425451f53af887ca490`
- Existing Nexus standing grant remains unchanged and is not widened by this card.

## Allowed external DevSpace files

Only these DevSpace source paths may be changed for the G9 Candidate:

- `/Users/jameschen/Workspace/devspace-chatgpt-mcp/src/execution-protocol.ts`
- `/Users/jameschen/Workspace/devspace-chatgpt-mcp/src/execution-protocol.test.ts`
- `/Users/jameschen/Workspace/devspace-chatgpt-mcp/src/local-agent-contract.ts`
- `/Users/jameschen/Workspace/devspace-chatgpt-mcp/src/local-agent-sessions.ts`
- `/Users/jameschen/Workspace/devspace-chatgpt-mcp/src/local-agent-execution-contract.test.ts`
- `/Users/jameschen/Workspace/devspace-chatgpt-mcp/src/server.ts`
- `/Users/jameschen/Workspace/devspace-chatgpt-mcp/src/server.test.ts`

No other DevSpace path may be changed. The existing dirty canonical checkout files `src/durable-operations.ts` and `src/durable-operations.test.ts` belong to an unrelated recovery-authority effort and must not be absorbed, reverted, reformatted, or used as G9 Candidate payload.

## Required authority model

1. Nexus remains the only governance authority. DevSpace receives only a controller-supplied immutable execution grant/evidence object and validates it mechanically.
2. The grant must bind at minimum: schema/version, grant identity/hash, Nexus issuer identity, task id, attempt id, exact DevSpace target base revision, dispatch-intent hash, authorized profile/worker identity where applicable, authorized write scope, issued/expiry time, revocation state, and claim/effect ceiling.
3. DevSpace must recompute the canonical grant hash instead of trusting a caller-supplied hash.
4. `NEXUS_GOVERNED` must require validated Nexus evidence before worker execution starts. Missing or mismatched evidence is a typed fail-closed error.
5. A governed grant may narrow DevSpace execution; it may not widen the controller dispatch intent, write paths, effect ceiling, claim ceiling, or worker/profile binding.
6. `OWNER_DIRECT` behavior remains backward compatible and does not acquire synthetic Nexus fields.
7. DevSpace does not mutate Nexus standing-grant state, does not issue/renew/revoke Nexus grants, and does not infer approval/merge/release authority.
8. No governed-to-direct fallback is permitted.

## Verification requirements

Run at the exact Candidate revision:

```bash
npx tsx src/execution-protocol.test.ts
npx tsx src/local-agent-execution-contract.test.ts
npx tsx src/server.test.ts
npm run typecheck
git diff --check
```

Also run negative controls proving at least: missing grant rejected; bad hash rejected; expired/revoked grant rejected; task/attempt mismatch rejected; target base mismatch rejected; write-scope widening rejected; profile mismatch rejected; dispatch-intent mismatch rejected; and no governed-to-direct fallback.

## Independent acceptance

A reviewer distinct from the implementer must inspect the exact Candidate diff, changed paths, tests, typed errors, authority boundaries, and the absence of changes to unrelated dirty recovery files. Worker success is not acceptance.

## Closure evidence

- Exact G9 DevSpace Candidate: `24cfc855ac907c68e32390160b87cd1b96880824`, tree `d21cc09c4ad4d2d321099c019753d24e0ae8837c`, from implementation base `db7d063681364c06e0ac3425451f53af887ca490`.
- Candidate verification recorded on DevSpace PR #26: execution protocol `7/7 PASS`; local-agent lifecycle/execution-contract `88/88 PASS`; MCP server seam `29/29 PASS`; TypeScript typecheck PASS; `git diff --check` PASS.
- Independent read-only Agy review on the exact Candidate reported `NO_BLOCKING_FINDINGS`; physical reviewer reconciliation recorded `changedPaths=[]`.
- DevSpace PR #26 merged the reviewed G1-G8 lineage plus the G9 bridge as `5212252bacfe8ae37747282211aff66594452426` on 2026-09-02. The promoted authority properties include pre-launch `NEXUS_GOVERNED` validation, canonical Nexus revision and tracked grant/Task-Card byte binding, task/attempt/base/profile/DispatchIntent/write-scope/claim/time/revocation checks, continuation revalidation, and no governed-to-direct fallback.
- Subsequent G10 durable closure independently bound the live Dev MCP to source `5212252bacfe8ae37747282211aff66594452426` / build `devspace-1.0.7-5212252b` and completed a live `NEXUS_GOVERNED` execution through that G9 runtime.
- The G10 positive run preserved the authorized target HEAD and changed only `g10-governed-canary.txt`; reconciliation reported `unexpectedPaths=[]` and `scopeState=WITHIN_SCOPE`.
- The G10 negative authority control intentionally supplied a bad tracked grant SHA-256. Dev MCP rejected it before worker launch with `Tracked Nexus execution grant bytes do not match grantSha256.` The negative workspace had no durable agent and no Git mutation. This supplies the live fail-closed witness required by the G9 exit criteria.
- G9 closure is a bookkeeping reconciliation only. It changes no DevSpace source/runtime, Nexus standing grant, Planner, Workforce Admission, lifecycle implementation, approval, merge, release, or production authority.

## Claim ceiling

`G9_GOVERNANCE_BRIDGE_COMPLETE`. This closure proves the bounded G9 governance bridge and its live cutover. It does not by itself claim G10, release, production readiness, or general Nexus governance correctness; those remain separately evidenced.

## Exit criteria

COMPLETE. The independently reviewed G9 Candidate was promoted and cut over to the live Dev MCP as source `5212252bacfe8ae37747282211aff66594452426`; fresh live runtime evidence subsequently bound that source/build; and a governed negative authority control proved invalid canonical evidence fails closed before worker launch with no fallback to `OWNER_DIRECT`. G10 remains a separately tracked and completed live end-to-end pilot gate.
