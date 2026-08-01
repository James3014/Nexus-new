# Campaign Index: Lifecycle Runtime Phase Convergence

artifact_authority: draft-successor
owner: James Chen
status: DRAFT_PENDING_OWNER_ACTIVATION
source_specification: /Users/jameschen/.codex/attachments/c7cbb20c-e2c7-42f8-a943-be66aef5099d/pasted-text-1.txt
AUTO_CHAIN: false

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
- This draft does not supersede or auto-chain the active P7 campaign.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `runtime-phase-contract-freeze` | `00-phase-contract-freeze.md` | DRAFT | Owner activation |
| 1 | `runtime-phase-transition-integration` | `01-transition-integration.md` | DRAFT | Card 0 |
| 2 | `runtime-phase-receipt-hook-symmetry` | `02-receipt-hook-symmetry.md` | DRAFT | Card 1 |
| 3 | `runtime-development-lifecycle-mapping` | `03-development-runtime-mapping.md` | DRAFT | Card 2 |
| 4 | `runtime-memory-learning-closure` | `04-memory-learning-closure.md` | DRAFT | Card 3 + workforce learning gate |
| 5 | `runtime-full-acceptance` | `05-full-acceptance.md` | DRAFT | Cards 0–4 + P7 disposition |

## Exit gate

`RUNTIME_PHASE_CONVERGENCE_PASS` requires the contract, legal transitions,
phase receipts, symmetric hooks, development/runtime identity mapping,
qualified learning closure and the full acceptance matrix to pass on fresh
evidence. It does not authorize production/public claims.

## Blocks

`HARD_BLOCK` for a second authority, unsafe transition, missing evidence
binding, or scope outside an activated card. `RECOVERABLE_BLOCK` for provider,
transport or environment failures with retained evidence.
