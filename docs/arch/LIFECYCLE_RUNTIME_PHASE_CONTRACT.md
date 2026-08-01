---
artifact_authority: draft-successor
owner: James Chen
status: DRAFT_PENDING_OWNER_ACTIVATION
purpose: Define the single machine-readable contract for Nexus runtime phases without creating a second router or development lifecycle.
source: /Users/jameschen/.codex/attachments/c7cbb20c-e2c7-42f8-a943-be66aef5099d/pasted-text-1.txt
---

# Nexus Runtime Phase Contract V1

This contract governs the runtime execution lifecycle only. `CapabilityPlanner`
and `HybridRouteDecision` remain route authority; `SelfHostedTaskService`
remains development-lifecycle authority; this contract does not approve,
integrate, push, or promote Candidates.

## Phase identity

| Code | Name | Product-visible | Meaning |
|---|---|---:|---|
| `S` | `PRELIFECYCLE_SPEC_BINDING` | no | Bind owner/task authority, inputs, scope and verifier identity. |
| `P` | `PLAN` | yes | Produce the bounded execution plan. |
| `D` | `DIAGNOSE` | yes | Classify failure/unknowns and decide whether research is needed. |
| `X` | `EXTERNAL_RESEARCH` | yes, optional | Gather bounded external evidence requested by Diagnose. |
| `R` | `REPAIR_EXECUTE` | yes | Execute the approved bounded repair/action. |
| `A` | `AUDIT` | yes | Verify outcome, scope, evidence and causal result. |
| `C` | `CRYSTALLIZE` | yes | Persist terminal outcome, receipt and qualified learning candidate. |

The user-visible path is `P → D → X? → R ↔ A → C`. The complete machine
path includes `S` and represents research return as `X → D` without inventing
another phase or router.

## Legal transitions

```yaml
S: [P, HARD_BLOCK]
P: [D, HARD_BLOCK]
D: [X, R, P, RECOVERABLE_BLOCK, HARD_BLOCK]
X: [D, RECOVERABLE_BLOCK, HARD_BLOCK]
R: [A, D, RECOVERABLE_BLOCK, HARD_BLOCK]
A: [C, R, D, RECOVERABLE_BLOCK, HARD_BLOCK]
C: [COMPLETE, FAILED, HUMAN_REVIEW]
```

`A → C` is legal only with an audit pass and complete evidence. An audit
reject may return to `R` or `D`; it may never silently become success. A
`HARD_BLOCK` stops at authority review and cannot auto-replay.

## Shared status vocabulary

`SUCCESS`, `FAILED`, `REJECTED`, `VETO`, `REPLAN`, `ESCALATED`,
`HUMAN_REVIEW`, `RECOVERABLE_BLOCK`, `HARD_BLOCK`, `CANCELLED`,
`COLLISION_REJECT`, and `COMPLETE` are the only terminal/decision labels.
Compatibility adapters may translate legacy labels but may not redefine them.

## Phase receipt minimum

Every phase attempt must identify `task_id`, `attempt_id`, `action_id`, phase,
attempt number, input/output hashes, authority revision, status, transition,
evidence/verifier references, timeout telemetry, block class and next action.
Missing receipt evidence fails closed and cannot be converted into task success.

## Hook rule

Observer hooks (`on_phase_start`, `on_phase_end`, `on_phase_fail`,
`on_phase_retry`, `on_phase_block`, `on_phase_cancel`, `on_task_terminal`) are
telemetry/learning only and fail open. Enforcement remains synchronous on the
state/action path: transition, scope, expected-head, receipt completeness,
definition drift and Candidate binding guards fail closed.

## Lifecycle separation

Runtime success is not Candidate acceptance; Candidate acceptance is not
integration; integration is not a production or public claim. Runtime and
development receipts share task/attempt/action identity but retain separate
authority and terminal states.
