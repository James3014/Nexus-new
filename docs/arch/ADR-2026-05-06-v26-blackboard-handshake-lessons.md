# ADR-2026-05-06: v26 Blackboard and Handshake Lessons

## Status
Accepted

## Context
v26 requires immutable phase data and semantic handshakes without breaking existing phase executors. The first implementation path exposed two lessons: missing artifacts must fail the pipeline cleanly, and broad protocol changes increase touch count without adding runtime leverage.

## Decision
Keep the artifact contract as an opt-in runtime seam discovered with `getattr`. Record phase mutations into an append-only blackboard, validate only explicitly declared requirements, and route handshake failures to terminal pipeline metadata instead of leaking exceptions.

## Lesson
Industrial hardening should deepen seams before tightening every interface. Fail-fast is useful only when the failure is observable, typed, and recoverable by the orchestrator.
