# Nexus Route-Cost Closure P23 - 2026-05-10

## Goal
Make Gemini 3 Flash / Gemini 3.1 Pro wearing Nexus approach stronger-model reliability on fixed public tasks without paying unnecessary always-on route cost.

## Changes
- Added a route-cost public gate that blocks claims when Nexus has no verified lift but systematically costs more than bare.
- Made the gate robust to single Gemini latency outliers by requiring paired median regression for multi-task runs.
- Marked `supervised_bare_first` rows as valid Nexus-supervised delivery when route, claim, context, and usage receipts are present.
- Promoted supervised bare-first policy for public ops-research/refactor/docs-code-sync neutral fixtures; Nexus escalates only when verifier/trust checks fail.

## Flash hot4 result
Run: `.nexus/reports/flash_hot4_auto_cost_gate_p23/evidence_bundle.json`

- Public claim gate: PASS
- with_nexus semantic verified: 4/4
- without_nexus semantic verified: 2/4
- trust mismatch: 0.0 / 0.0
- avg wall: with_nexus 35.6764s / without_nexus 23.0365s
- wall ratio: 1.5487
- paired median wall ratio: 1.4687
- token ratio: 1.0334
- with_nexus avg model calls: 1.0
- with_nexus avg R phase wall: 13.7557s

## Root cause learned
The earlier forced-Hyper run proved the expensive path was R/Hyper. After supervised bare-first, R phase disappeared for two tasks and stayed bounded for verifier-failing tasks. A separate context-only rerun showed Gemini latency/token stats can produce single-task outliers, so cost gates must use paired task evidence instead of only aggregate averages.

## Closure status
Closed for Flash hot4 route-cost gate: Nexus improves verified delivery from 2/4 to 4/4 with bounded cost and public gate PASS. Larger Flash/Pro fixed sets remain the next validation layer, not a blocker for this closure.
