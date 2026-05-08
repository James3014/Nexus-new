# ADR: Public Credibility Benchmark Lanes

Date: 2026-05-08

## Context

Nexus public claims need two different evidence classes:

- Nexus commercial lanes: same-model bare vs Nexus A/B for capability lift, governed delivery, and cost efficiency.
- External public benchmark lanes: SWE-bench Verified wiring and official harness results.

These must not be merged into one headline. Nexus commercial lanes can support public-candidate claims once their public claim gate passes. SWE-bench Verified can support external credibility only after the official harness result exists with a fixed denominator.

## Decision

Use `scripts/bench/public_credibility_phase_plan.py` as the Phase 0-9 source for public benchmark sequencing.

- Phase 0-5: public-safe Nexus commercial lane preflight and same-model A/B.
- Phase 6: internal realism appendix, never headline.
- Phase 7-9: SWE-bench Verified wiring, subset, and external headline gate.

Public uplift claims require same-model A/B. External SWE-bench claims require official harness output.

## Lesson

The first Phase 0 preflight failed because the command omitted model lock environment and hidden verifier mode. This is the correct failure mode: public preflight must fail closed when `NEXUS_GEMINI_MODEL_NAME`, `NEXUS_DIRECT_GEMINI_MODEL`, or `NEXUS_VALUE_HIDDEN_VERIFIER=1` are missing.

The stable fix is to generate preflight commands from the same command builder used by model benchmark phases, not hand-write a shorter preflight command.
