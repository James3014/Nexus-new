# Nexus Capability Route Status - 2026-04-30

## What
This document is the current status table for the Nexus capability router. It
separates phase routing from capability composition and public-safe evidence.

## Why
The new router is not only a phase selector. It must decide which capabilities
to compose, when to invoke them, and whether each capability has enough evidence
to be claimed publicly. A task is not route-green until expected capability
receipts are selected, invoked, evidenced, gated, and public-safe.

## How
Use the fixed smoke entry:

```bash
uv run python scripts/ops/capability_route_smoke.py
```

For command inspection without running benchmark tasks:

```bash
uv run python scripts/ops/capability_route_smoke.py --print-only
```

For internal same-model Codex calibration before spending Gemini quota:

```bash
uv run python scripts/ops/codex_nexus_ab_smoke.py --preflight-only
```

## Capability Status

| Capability | Main phase hooks | Router role | Current evidence | Status |
|---|---|---|---|---|
| CodeIntel | P/X/A | Impact/context before repair and delivery gate | scan + impact report + claim bundle | smoke-green |
| Research | X | Context gap fill and citation-backed answer support | research refs + gate flag | smoke-green |
| Hyper | R/A | Focused repair loop and self-heal path | hyper sprint receipt + verified artifact | smoke-green |
| Nightshift | R/A/C | Escalation/recovery when normal repair is insufficient | nightshift report path + recovered flag | smoke-green, bench-safe |
| Swarm | D/R/A | Multi-role review/consensus for complex tasks | role findings + evidence + consensus | smoke-green, bench-safe |
| Drone | R/A | Subtask artifact execution and verification | artifact paths + artifact count | smoke-green, bench-safe |
| Ultra Review | D/A | High-risk review with sandbox evidence gate | Ultra Review report + retained diff/status/progress artifacts | smoke-green |
| Autoreason | D/R/A | Candidate ranking by evidence, specificity, and score | judge votes + winner + stop reason | smoke-green |
| DDTree | X/R/A | Candidate pruning and cost reduction | selected candidate ids + saved steps | smoke-green |
| LanceDB | X | Tactical retrieval / semantic memory support | vector hit refs + source id | smoke-green |
| Memory | P/X/C | Long-term lesson/context contract support | memory refs + memory gate flag | smoke-green |
| Delivery Gate | A/C | Verified delivery fail-closed contract | delivery refs + gate flag | smoke-green |
| MemPalace Gate | D/A | Policy and governance boundary check | task-scoped mempalace ref + gate flag | smoke-green |
| Artifact Gate | A/C | Objective verification evidence | task-scoped artifact ref + gate flag | smoke-green |
| Claim Gate | A/C | Public claim fail-closed contract | task-scoped claim ref + invocation flag | smoke-green |
| Belief Gate | D/R | Confidence and budget-sensitive decision guard | task-scoped belief ref + gate flag | smoke-green |

## Current Smoke Evidence

- `scripts/ops/capability_route_smoke.py` runs four suites:
  - `route_oracles`: 8 route-oracle tasks covering Autoreason, DDTree,
    Ultra Review, Research, LanceDB, Swarm, Drone, and Nightshift.
  - `codeintel_hyper`: 2 Nexus value tasks covering Hyper, CodeIntel, Memory,
    and Delivery Gate.
  - `core_governance_gates`: 2 Nexus value tasks covering MemPalace Gate,
    Artifact Gate, and Claim Gate.
  - `belief_gate`: 1 RLM harder task covering Belief Gate.
- Latest manual evidence before this document:
  - route-oracle smoke: 8/8 `SUCCESS/VERIFIED`, missing expected receipts = 0.
  - CodeIntel/Hyper smoke: 2/2 `SUCCESS/VERIFIED`, missing expected receipts = 0.
  - core governance gate smoke: 2/2 `SUCCESS/VERIFIED`, missing expected
    receipts = 0.
  - Belief gate smoke: 1/1 `SUCCESS/VERIFIED`, missing expected receipts = 0.
  - full fixed smoke summary: `receipt_diagnostic_pass=true`,
    `public_benchmark_claim_allowed=false`, because this is Nexus-only receipt
    proof rather than same-model A/B proof.
  - Ultra Review final resmoke preserved audit artifacts while deleting the
    large sandbox `worktree/`.
- `scripts/ops/codex_nexus_ab_smoke.py` locks a fixed 4-task Codex 5.5 bare vs
  Codex 5.5 wearing Nexus smoke for internal route/value calibration. It uses
  the subprocess Nexus path, hidden verifier, same-model lock, Autoreason,
  DDTree, Ultra Review dry gate, and a candidate cap of 3. This smoke is not a
  public Gemini claim; it is the fast pre-Gemini check that the benchmark wiring
  is ready.

## Residual Debt

- Swarm, Drone, and Nightshift are public-safe in the fixed smoke suite, but
  broad product claims still need production-grade non-benchmark executor
  evidence.
- Gemini public comparison should run only after this smoke suite passes, so
  quota is spent on comparison rather than route debugging.
