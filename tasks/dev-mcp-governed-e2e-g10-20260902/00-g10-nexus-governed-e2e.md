# Task Card 00: G10 Nexus-Governed End-to-End Pilot

## Identity

- task_id: `g10-nexus-governed-e2e-20260902`
- campaign_id: `dev-mcp-governed-e2e-g10-20260902`
- artifact_authority: current
- status: ACTIVE
- owner: James Chen
- authorization: owner explicitly instructed the controller on 2026-09-02 to continue until G10 is complete and resolve intermediate blockers without stopping
- contract_kind: TRACKED_TASK_CARD
- AUTO_CHAIN: false
- worker_may_commit: false
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false

## Objective

Run one minimal live `NEXUS_GOVERNED` Dev MCP execution that proves canonical Nexus authority is validated before worker launch, the worker is constrained to the authorized profile and write scope, the physical result is independently reconcilable, and worker completion does not become Nexus verification or acceptance authority.

## Bound live runtime and target

- Dev MCP live source: `5212252bacfe8ae37747282211aff66594452426`
- Dev MCP live build: `devspace-1.0.7-5212252b`
- Dev MCP server instance at G10 preparation: `26c0cef1-4851-4120-8df5-b689278117f7`
- target workspace: `/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/deploy-g9-5212252-d3800baa`
- target workspace id at G10 preparation: `ws_72d60d25b1`
- target base HEAD: `5212252bacfe8ae37747282211aff66594452426`
- required worker profile: `agy-medium-implement`
- required attempt_id: `g10-live-e2e-attempt-01`
- dispatch_intent_artifact: `tasks/dev-mcp-governed-e2e-g10-20260902/g10-dispatch-intent.json`
- dispatch_intent_hash: `e57bd97487cafd04d58c59462d931e2edf4d1f3f01bde003f00d48fb291bdcb7`

## Authorized execution

The only authorized workspace mutation is creation of `g10-governed-canary.txt` with exactly:

```text
G10_NEXUS_GOVERNED_E2E_OK
```

The file must end with one newline. No other workspace path may change.

The worker may read `AGENTS.md` only as needed for repository instructions. It may not commit, push, merge, install packages, alter configuration, invoke child agents, touch external directories, or claim VERIFIED, ACCEPTED, MERGED, DEPLOYED, RELEASED, or production readiness.

## Required authority properties

1. Dev MCP must run with `authorityMode=NEXUS_GOVERNED` and an immutable pointer to the canonical tracked grant plus this Task Card.
2. The exact controller `DispatchIntent` is tracked at the artifact path above; the grant must bind its canonical hash, this task id, exact attempt id, DevSpace base revision, `agy-medium-implement`, write scope `g10-governed-canary.txt`, effect ceiling `WORKSPACE_MUTATION`, and claim ceiling `IMPLEMENTED`.
3. Missing, stale, tampered, expired, revoked, or mismatched authority must fail closed before worker launch and must never fall back to `OWNER_DIRECT`.
4. Continuation must revalidate the same canonical grant.
5. Worker result is execution evidence only. Acceptance remains outside Dev MCP.

## Verification

After the positive run, independently prove:

- exact live server/build/source identity;
- worker profile/provider/model and durable attempt identity;
- `g10-governed-canary.txt` exact bytes;
- reconcile reports only `g10-governed-canary.txt` changed;
- workspace HEAD remains the authorized base;
- worker output does not contain or create verifier/acceptance authority.

Run negative controls with no mutation proving at least one tampered/mismatched grant is rejected before worker launch. If the positive session is continued after grant revocation in canonical Nexus source, continuation must be rejected before re-execution.

## Claim ceiling

`G10_NEXUS_GOVERNED_E2E_COMPLETE` only after the positive live run, physical reconciliation, and required negative authority control succeed. This Task Card does not grant release or production authority.

## Exit criteria

G10 is complete when the live Dev MCP at the bound G9 runtime successfully executes the exact governed canary under this canonical grant, physical evidence is within scope, at least one tamper/mismatch control fails closed before launch, and no governance authority is silently transferred to Dev MCP.