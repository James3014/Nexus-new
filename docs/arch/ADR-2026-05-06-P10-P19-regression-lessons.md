# ADR: P10-P19 Regression Lessons

Date: 2026-05-06

## Context

P10-P19 added runtime guardrails for Brain Hub alignment, route receipts, candidate-count routing, storage auditability, and pipeline composition inventory.

## Lessons

1. Brain Hub S-stage audit gates must update test fixtures with the same runtime markers they require in production. Otherwise the audit correctly fails, but the failure reads like product drift instead of fixture incompleteness.
2. Route regression tests must capture the actual subprocess command, not only the environment. Candidate-count degradation is a command-line contract and cannot be proven by `NEXUS_LLM_CANDIDATE_CAP` alone.
3. Long Flash benchmark commands can fail inside sandboxed `uv` cache access before reaching product logic. Treat that as environment failure and rerun through the approved `uv run` path rather than interpreting it as Nexus behavior.
4. If generated markdown and `evidence_bundle.json` disagree on public-claim gate state, the bundle is the authority because it carries the structured gate checks and raw file hashes.
5. Targeted pytest commands must be discovered with `rg "def test_"` before use; a wrong node id can produce zero product evidence while looking like a quick verification attempt.
6. Receipt adapters must distinguish diagnostics from evidence. Rejected-claim-only DocScout output is useful for audit, but must not count as external-doc invocation evidence without a verified external source.
7. Helper functions used in low-level benchmark timing code should avoid dependencies defined later in the module; direct `os.environ` parsing is safer for import-time callable utilities.
8. Public benchmark gate logic must be shared between markdown and evidence bundles. If one path enforces token telemetry completeness and the other does not, the report will create contradictory public-claim evidence.
9. Benchmark artifact regeneration should use exported helpers or an inline parser for JSONL. Do not assume private helper names exist when repairing evidence after a benchmark run.
10. Multi-file inspection commands should use `rg` or separate `sed` calls; tools like `nl` accept one file shape poorly and can fail before producing useful evidence.

## Decision

- Keep the S-stage runtime checklist fail-closed when Brain Hub guidance mentions S.
- Keep candidate-count regression as an explicit command assertion.
- Use targeted tests before Flash so same-model A/B is not asked to discover deterministic contract breaks.
- Require Flash public reports to state model lock and hidden-verifier status from `evidence_bundle.json`, not only markdown prose.
- Keep rejected-only claim uncertainty as a diagnostic path, not a public-safe capability receipt.
- Keep evidence-bundle public gate failures aligned with markdown public gate failures before treating a Flash report as public-safe.
- Regenerate benchmark artifacts with known public helpers after gate logic changes, then inspect the structured gate before reporting.
- Treat Brain Hub alignment as a pre-Flash runtime gate: scoring spec, schema, runtime probes, and S-stage contract must agree before spending Flash budget.
