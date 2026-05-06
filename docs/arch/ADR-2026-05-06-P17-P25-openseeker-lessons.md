# ADR: P17-P25 Benchmark Telemetry, CodeIntel Cache, and OpenSeeker Alignment Lessons

Date: 2026-05-06

## Context

P17-P25 hardening covers Flash-readiness telemetry and route/receipt evidence quality. A new input, `wiki/refactor_openseeker_alignment_spec.md`, aligns Nexus with OpenSeeker-v2 style high-information, long-chain search trajectories.

## Decisions

- Classify model timeout followed by local fallback as `model_timeout_with_local_fallback` instead of generic `model_call_without_tokens`.
- Mark timeout-local fallback rows as `public_cost_evidence=false`; they may be useful engineering diagnostics, but they cannot support public cost claims.
- Add a run-scoped CodeIntel graph cache for benchmark subprocess runs via `NEXUS_CODEINTEL_RUN_CACHE_DIR` and `NEXUS_CODEINTEL_CACHE_SCOPE=run`.
- Treat OpenSeeker alignment as P25 planning input, not as an immediate Flash blocker: low-step filtering, high-information trajectory capture, action schema, and multi-hop evidence should be added after telemetry is trustworthy.

## Failure Lessons

- A targeted pytest command referenced a non-existent node id. Lesson: locate test node ids with `rg` before composing long targeted commands when the test name is uncertain.
- The initial CodeIntel cache env test assumed a default manifest hash of `mh`; actual ad-hoc `CapabilityTask` values can have an empty manifest hash. Lesson: production cache keys must explicitly handle empty manifest hashes with a deterministic `default` segment.

## Follow-up

- P25 replan must include OpenSeeker-derived gates: trajectory step count, evidence hop count, tool action catalog coverage, and low-step filtering policy.
- Public Flash reporting must distinguish engineering rescue success from public model/cost evidence.
