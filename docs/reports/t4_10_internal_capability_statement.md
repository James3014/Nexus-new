# T4.10 Internal Capability Statement

**Date**: 2026-06-18

---

## Statement

Nexus has established an internal, CI-validated, fixture-backed model-candidate evidence path for local Qwen14B REPLACE-only patching. As of T4.10, four fixture-backed candidates have passed fresh model replay with strict attribution, source snapshots, canonical SEARCH lock, verification, export guard, and no-public-claim controls.

## Facts

- **Fixture-backed verified candidates**: 4
- **Historical-only preserved candidates**: 4
- **Model**: local Qwen14B (qwen2.5-coder:14b-instruct-q3_K_M via Ollama)
- **Scope**: internal controlled candidates
- **Public benchmark**: NO
- **Solve rate**: NO
- **Official SWE-bench comparison**: NO
- **Human review required**: YES (before training/export)

## What This Is NOT

- "Qwen solves X%"
- "Nexus achieves SWE-bench score"
- "Public benchmark result"
- "Production-ready autonomous patcher"
- "Generalized solve rate"

## What This IS

- Internal controlled model-candidate evidence
- CI-validated fixture-backed replay path
- Attribution-clean model patch candidates
- Foundation for S0 StrategyEnvelope MVP
