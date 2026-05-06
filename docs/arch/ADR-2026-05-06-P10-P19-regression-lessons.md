# ADR: P10-P19 Regression Lessons

Date: 2026-05-06

## Context

P10-P19 added runtime guardrails for Brain Hub alignment, route receipts, candidate-count routing, storage auditability, and pipeline composition inventory.

## Lessons

1. Brain Hub S-stage audit gates must update test fixtures with the same runtime markers they require in production. Otherwise the audit correctly fails, but the failure reads like product drift instead of fixture incompleteness.
2. Route regression tests must capture the actual subprocess command, not only the environment. Candidate-count degradation is a command-line contract and cannot be proven by `NEXUS_LLM_CANDIDATE_CAP` alone.

## Decision

- Keep the S-stage runtime checklist fail-closed when Brain Hub guidance mentions S.
- Keep candidate-count regression as an explicit command assertion.
- Use targeted tests before Flash so same-model A/B is not asked to discover deterministic contract breaks.
