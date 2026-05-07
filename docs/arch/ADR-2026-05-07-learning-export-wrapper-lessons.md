# ADR-2026-05-07 Learning Export Wrapper Lessons

## Context

S2T model-training export v2 gained an Autodata quality gate argument, but the public wrapper in `nexus.contracts.s2t_trace` initially kept the old signature.

## Lesson

When a contract module exposes both implementation and facade exports, additive arguments must be tested through the facade path as well as the implementation path. Otherwise runtime callers can fail even when the lower-level implementation is correct.

## Decision

Keep `quality_rows` additive and optional. The facade must forward it unchanged to preserve compatibility while allowing Autodata fail-closed gating.
