# ADR-2026-05-08: Route Cost Local-Preflight Lessons

## Status
Accepted

## Context
P45-P50 route-cost tuning found two cost regressions while Codex was wearing Nexus and validating with single-task Flash runs:

1. Planner lexical policies were reading the Nexus wearing/route contract suffix as if it were the user task body. Contract words such as `governance`, `claim`, and `evidence` selected costly capabilities that were not invoked.
2. `docs_code_sync` tasks with deterministic local repair knowledge still waited for a Gemini gateway timeout before using the local candidate. This made a successful Nexus path look slow and token-unreliable.
3. During implementation, a local edit script accidentally overwrote a test file with unrelated source content. The file was immediately restored, but this is a process lesson.

## Decision
- Planner policy matching must classify the user task body separately from appended Nexus control contracts.
- Route smoke reports must include `over_selection_hotspots` so cost regressions identify concrete selected-not-invoked capabilities.
- Hyper sprint may use a verified local preflight before external LLM calls when the local mutator already has a deterministic contract for the task family.
- Benchmark eligibility must distinguish model-authored Nexus delivery from verified Nexus-internal delivery. Local preflight can be eligible when Nexus context, pillars, phases, artifact verification, and semantic verification are present, but it must not claim provider-token cost evidence.
- Before and after scripted edits, agents should inspect `git diff -- <path>` for touched tests/source files to catch accidental file replacement before broader test runs.

## Evidence
- `capability_route_smoke.py` passed with `receipt_diagnostic_pass=true` and selected-not-invoked hotspots emitted.
- Targeted test suite: `107 passed`.
- Flash single-task validation:
  - `nexus-value-repair-001`: Nexus+Flash passed in 25.5s; bare Flash failed.
  - `nexus-value-context-001`: after local preflight, Nexus passed in 3.85s with 0 model calls; bare Flash failed after 162.39s.
