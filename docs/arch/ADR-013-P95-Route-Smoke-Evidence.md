# ADR-013: Route Smoke Evidence Must Distinguish Infra Invalid From Route Failure

Date: 2026-05-05
Status: Accepted

## Context

During P95 verification, the first sandboxed `python3 scripts/ops/capability_route_smoke.py` run failed before route evidence was generated because `uv` could not read `/Users/jameschen/.cache/uv/sdists-v9/.git`. The resulting smoke summary had `tasks=0` and missing JSONL files. Interpreting that summary as a route regression would be wrong: no route rows existed.

## Decision

Route smoke evidence is valid only after each suite emits a non-empty with_nexus JSONL file or explicitly marks itself infrastructure-invalid. Empty suite summaries following subprocess permission failures must be treated as infra invalid and rerun with the approved unrestricted command path before route-quality metrics are interpreted.

## Consequences

- P96 should add an explicit infra-invalid classifier around subprocess/sandbox failures in route smoke.
- Reports must cite the concrete JSONL path used for route funnel metrics.
- Route-quality gates should only run on non-empty suites unless the suite failed for a real route assertion.

## P95 Lesson

Failure: sandboxed route smoke could not access the uv cache and produced empty suite summaries.

Lesson: evidence generation failure is not behavioral route failure. Require non-empty JSONL evidence before evaluating selected/invoked/evidence/outcome funnels.

Corrected evidence: `.nexus/reports/bench_route_8oracle_smoke/with_nexus_1777983460.jsonl`, followed by `research_stack_route_smoke.py` PASS.
