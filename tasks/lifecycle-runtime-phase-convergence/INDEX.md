# Campaign Index: Lifecycle Runtime Phase Convergence

artifact_authority: current
owner: James Chen
status: active, governed and sequential
source_specification: /Users/jameschen/.codex/attachments/c7cbb20c-e2c7-42f8-a943-be66aef5099d/pasted-text-1.txt
AUTO_CHAIN: false

activation:
  activated_by: James Chen
  activated_card: runtime-phase-contract-freeze
  activation_evidence: /Users/jameschen/.codex/attachments/79acf82d-bce4-4346-95ca-054f30ae293c/pasted-text.txt
  activation_base_head: 4ef2a03b9c40b5ea31d8cd56c9bee9ffc4f62fe4
  owner_declared_card_hash: eda0791e09567a140d0537be00ebd668ae79bef78b9fbfa242d312c4fa61d4ba
  activation_source_card_hash: 81c8c2e07ebd3cf6b2d321ea2279126aa00b63746235184c478277aef3a30928
  hash_reconciliation: observed_repository_card_hash_used
  activated_at: 2026-08-02

## Objective

Freeze and wire one runtime phase contract across the existing Nexus Pipeline,
receipts and hooks, then bind it to the existing development lifecycle and
memory/learning lineage. Do not create a second router, lifecycle service,
verifier, receipt store, memory database or MCP server.

## Authority boundaries

- Route authority: `CapabilityPlanner` / `HybridRouteDecision`.
- Runtime execution authority: `UnifiedRuntime` and the existing Pipeline.
- Development lifecycle authority: `SelfHostedTaskService`.
- Evidence authority: existing verifier and receipt validators.
- Owner remains the only approval, integration, push and final-claim authority.
- This campaign does not supersede the active P7 campaign; P7 disposition and
  Owner review remain separate gates.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `runtime-phase-contract-freeze` | `00-phase-contract-freeze.md` | VERIFIED_CANDIDATE | Owner activation |
| 1 | `runtime-phase-transition-integration` | `01-transition-integration.md` | VERIFIED_CANDIDATE | Card 0 |
| 2 | `runtime-phase-receipt-hook-symmetry` | `02-receipt-hook-symmetry.md` | ACTIVE | Card 1 |
| 3 | `runtime-development-lifecycle-mapping` | `03-development-runtime-mapping.md` | DRAFT_PENDING_CARD_2 | Card 2 |
| 4 | `runtime-memory-learning-closure` | `04-memory-learning-closure.md` | DRAFT_PENDING_CARD_3 | Card 3 + workforce learning gate |
| 5 | `runtime-full-acceptance` | `05-full-acceptance.md` | DRAFT_PENDING_CARDS_0_4 | Cards 0–4 + P7 disposition |

## Exit gate

`RUNTIME_PHASE_CONVERGENCE_PASS` requires the contract, legal transitions,
phase receipts, symmetric hooks, development/runtime identity mapping,
qualified learning closure and the full acceptance matrix to pass on fresh
evidence. It does not authorize production/public claims.

## Blocks

`HARD_BLOCK` for a second authority, unsafe transition, missing evidence
binding, or scope outside an activated card. `RECOVERABLE_BLOCK` for provider,
transport or environment failures with retained evidence.

## Current frontier

`runtime-phase-receipt-hook-symmetry` is active after Card 1's scoped candidate
and fresh local verification. Only this card may mutate source until its exit
criteria and receipt are complete.
