---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR-2026-05-06: Public Delivery and Cost Gate Split

## Status

Accepted

## Context

Flash P61-P75 showed verified delivery can pass while token/cost evidence remains incomplete because long-running rows may finish through local fallback after model timeout. A single public claim gate made this ambiguous: delivery evidence was blocked by cost telemetry, or worse, a future relaxation could accidentally make cost-ineligible rows look fully public-safe.

## Decision

1. Keep `public_claim_gate` as the backward-compatible aggregate delivery-and-cost gate.
2. Add `public_delivery_gate` for verified-delivery claims only.
3. Add `public_cost_claim_gate` for token/cost claims only.
4. P30 acceptance with `--require-flash` requires delivery gate pass, while reporting legacy aggregate and cost gate status separately.

## Lessons

1. Cost telemetry incompleteness must not erase verified-delivery evidence.
2. Verified-delivery evidence must not be reused as token/cost evidence.
3. In the Codex sandbox, `uv run` can fail on the global uv cache with `Operation not permitted`; rerun important verification with the approved elevated `uv run` path instead of treating it as a code failure.

## Evidence

- Targeted regression: `4 passed`.
- P30 `--require-flash`: `passed=true` with `flash_public_delivery_gate=true`, `flash_public_cost_claim_gate=false`, and legacy `flash_public_claim_gate=false`.
- Existing Flash 2x2 rows remain cost-ineligible because with-Nexus token measured rate is `0.75`, below the public cost threshold.
