# Nexus Lifecycle Agent Workflow Contract

artifact_authority: current
owner: James Chen
status: active, implementation contract
source: `tasks/lifecycle-agent-workflow-convergence/INDEX.md`

## Authority

`CapabilityPlanner` and `HybridRouteDecision` are the only route authorities.
The self-hosted task service owns durable lifecycle state. The public Nexus
MCP Gateway is the only external MCP identity; its self-hosted MCP provider is
an internal implementation surface.

## Execution lanes

| Lane | Use | Target | Model authority | Completion authority |
|---|---|---:|---|---|
| `DIRECT_CANONICAL` | read, diagnose, small bounded primary-agent change | no | none required | scoped verifier + primary commit |
| `ASSISTED_CANONICAL` | bounded model proposal on a clean canonical checkout | no | candidate only | parser/verifier + primary apply/commit |
| `ISOLATED_TARGET` | risk, conflict, multi-agent, or explicit Candidate work | yes | candidate only | independent acceptance + Owner promotion |

## Identity and idempotency

Every mutation carries:

```yaml
task_id: stable logical task identity
attempt_id: new identity for each retry/worker/transport attempt
action_id: server-issued identity for one action
idempotency_key: caller/server deduplication key
task_card_hash: hash of the executable Task Card
expected_head: source revision precondition
allowed_paths: bounded mutation scope
request_hash: canonical request digest
```

The same idempotency key with a different request hash is rejected. A timeout
or disconnect produces an uncertain action that must be reconciled against
physical HEAD, diff, Candidate refs, and receipts before any retry.

## Completion and cleanup

```text
candidate produced
→ candidate verified
→ independent acceptance
→ Owner integration or explicit disposition
→ terminal cleanup/archive
```

`APPROVED` is not terminal. A durable Candidate ref permits Target cleanup;
Target retention is not a substitute for lifecycle state.

## Hooks and memory

EventBus is observer-only. Synchronous action/state guards are the enforcement
surface and fail closed with structured reason codes. Learning writeback is
qualified by terminal evidence and keeps task/attempt/action provenance.

## Prohibited behavior

- no second router, lifecycle authority, verifier, receipt store, or MCP server;
- no unrestricted shell as a response to a missing typed action;
- no automatic replay after disconnect;
- no model self-approval, integration, push, cleanup, or production claim;
- no direct JSON state edits.
