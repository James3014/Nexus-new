# Nexus Skill Chain Contract

This contract defines interoperability between Nexus governance Skills. It does not create a router, execution authority, approval authority, integration authority, or repository source of truth.

Compatibility snapshot: `nexus-skill-chain-2026-09-08-r3`.

## Canonical chain

| Producer | Canonical artifact | Required state | Consumer |
|---|---|---|---|
| `evidence-bounded-design-interview` | `evidence.design_interview.v1` ledger | `READY_FOR_ADAPTER` | `nexus-grill-with-docs` when Nexus-specific binding is required |
| `nexus-grill-with-docs` | `nexus.design_interview.v2` ledger | `READY_FOR_SPEC`, owner-confirmed convergence | `nexus-to-spec` |
| `nexus-current-state-audit` | revision/transport-bound snapshot evidence | fresh or explicitly partial/stale/blocked | Any downstream Skill as evidence only |
| `nexus-mcp-access-audit` | access/transport audit | reviewed recommendation, never permission | Spec, compiler, executor, or owner review |
| `nexus-to-spec` | validated Nexus Spec | `READY_FOR_TASK_CARDS` | `nexus-to-task-cards` |
| `nexus-to-task-cards` | campaign `INDEX.md` plus one ACTIVE Task Card | source Spec digest preserved; one frontier | `nexus-model-task-compiler` or governed executor |
| `nexus-model-onboarding-calibration` | `nexus.model_calibration.v2` plus proposed workforce entry | owner-approved and written to authoritative workforce policy before use | Compiler/runtime policy lookup only |
| `nexus-model-task-compiler` | `nexus.compiled_model_task_packet.v3`; for MCP, `nexus.chatgpt_mcp_execution.v4` | `READY`, exact worker/model/transport/action identity plus compile-time Workforce Admission `ALLOW` bound by receipt/hash | External worker or `nexus-mcp-task-executor` |
| `nexus-mcp-task-executor` | `nexus.mcp_execution_receipt.v2` plus optional Candidate; execution-time Workforce Admission remains validated side evidence when material | Direct verified result, Candidate pending acceptance, or bounded block | Owner review or `nexus-candidate-acceptance-audit` |
| `nexus-candidate-acceptance-audit` | `nexus.candidate_acceptance.v3` | exact lineage, independent reviewer/oracle, bounded claim | Owner decision and/or `nexus-handoff` |
| `nexus-handoff` | inline continuation or formal `nexus.handoff.bundle.v3` | one exact resume gate; no transferred authority | Fresh session or receiving tool |
| `nexus-controller-handoff` | controller mission brief with strategic/progress ledgers and snapshot-bound `CURRENT_TRUTH` evidence | campaign/roadmap transfer only; receiving controller must rebind current state before orchestration | Receiving controller |

## Identity chain

For tracked work preserve, without reconstruction:

`interview_id -> nexus_interview_id -> spec_id/spec_sha256 -> campaign_id/task_id/task_card_sha256/contract_hash -> packet_id/packet_sha256/attempt_id -> manifest_id/manifest_sha256 -> receipt_id/receipt_sha256 -> acceptance_id/acceptance_sha256/reviewer_attempt_id when a Candidate exists -> handoff_id/handoff_sha256 when formal`

Owner-inline execution is supported directly by `nexus-mcp-task-executor`; do not invent a Task Card, compiled packet, or campaign merely to force Owner-inline work through the tracked chain.

## Side evidence and freshness

Current-state snapshots, access audits, calibration receipts, provider preflights, Issue worker preferences, CI checks, and Workforce Admission are evidence or policy inputs rather than standing execution authority. Preserve dynamic evidence by exact digest/identity and observation time when it materially supports a downstream claim.

For model-specific compiled execution, distinguish:

- compile-time Workforce Admission embedded and hash-bound in `nexus.compiled_model_task_packet.v3`;
- execution-time Workforce Admission side evidence required by the executor when exact worker/model binding is material;
- acceptance-time verification of that execution binding when Candidate acceptance relies on it.

Reacquire dynamic repository/transport/admission evidence after material delay, reconnect, source or dirty-state movement, server/root/action/schema/permission movement, runtime-source drift, worker/provider/model/role/autonomy/context change, or model/executable revision. A prior receipt remains historical evidence; it is not a lease.

## Authority and claim rules

- CapabilityPlanner remains the sole Nexus route/capability authority; no Skill creates a parallel router.
- A compiled packet or manifest is not standing execution authorization by itself.
- Host discovery does not prove direct-recipient invocation or semantic expressibility.
- Executor Direct work stops at `DIRECT_VERIFIED_RESULT`; it does not create a Candidate.
- Candidate work stops at `IMPLEMENTER_PASS_PENDING_ACCEPTANCE` and requires independent acceptance before owner approval.
- Candidate acceptance recommends; it does not approve, integrate, push, release, deploy, or clean up.
- Handoffs preserve evidence and one resume gate; they never transfer confirmations, admission, approval, retry budget, or mutation authority.
- Controller handoffs preserve roadmap rationale, current frontier, do-not-rediscover knowledge, and snapshot-bound current truth; they never transfer dispatch, worker-admission, approval, integration, or mutation authority, and the receiving controller must rebind freshness before changing orchestration.
- Downstream claim ceilings must equal or narrow the nearest binding source.
- Skills name one next gate and do not auto-chain.

## Applicability and compatibility (2026-09-08)

This is the explicitly selected tracked Nexus artifact chain, not a universal prerequisite for every direct task. Target-repository lane rules govern card use. Resident Open SWE has separate explicit repository-local card obligations. A card from another repository is not imported authority.

New output: compiled packet v3; MCP manifest v4; execution receipt v2; acceptance result v3; formal handoff v3. The acceptance validator also contains legacy manifest v3 and receipt v1 branches, subject to all its pairing, identity and evidence checks. This is not a promise that arbitrary version combinations pass. Preserve historical artifacts byte-for-byte; never rewrite a version string to make an old artifact appear current. See `schema-compatibility.md` where provided.

Current source evidence is a snapshot, not live authority. Runtime effect/operation identity and observed model attestation must be retained through the actual supported side-evidence surface; do not invent schema fields. An unexpressible material binding is a capability gap, not permission to omit it.
