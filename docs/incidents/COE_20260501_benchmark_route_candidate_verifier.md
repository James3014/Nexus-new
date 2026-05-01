# COE 2026-05-01: Benchmark Route Candidate and Verifier Drift

## Summary

The 12-task public-candidate benchmark exposed one Nexus treatment failure on `nexus-value-evidence-001`. The task was solvable by Nexus local mutation, but the benchmark row became unverified because candidate selection and hidden-verifier execution did not preserve the same evidence contract as the successful local replay.

## Five Whys

1. Why did the benchmark fail?  
   The Nexus row did not produce a verified artifact/claim outcome for one evidence task.

2. Why did the route not preserve the verified outcome?  
   Autoreason could select a lower-scoring shadow/evidence candidate over an already verified candidate.

3. Why was that allowed?  
   Candidate selection trusted judge evidence ranking without a score guard for `score >= 1.0` candidates.

4. Why did local replay still appear failed inside the benchmark runner?  
   Hidden verifier commands used `uv run pytest`, which can fail in sandboxed environments due cache access.

5. Why was the infra failure counted as task failure?  
   Hidden-verifier infra errors were not classified separately from semantic verifier failures.

## Action Items

- Add an Autoreason score guard: a verified candidate cannot be overridden by a lower-scoring candidate.
- Classify hidden-verifier infrastructure failures as `hidden_verifier_infra_error` and exclude them from solve-rate denominators.
- Run benchmark verifier commands through the current Python interpreter instead of `uv run pytest`.
- Before spending Gemini quota, replay any failed task locally with Nexus and confirm artifact diff, hidden verifier, and public-safe receipts.

## Verification

- `tests/research/test_sprint_service.py::test_select_candidate_with_routing_layers_keeps_verified_candidate_over_shadow`
- `tests/benchmark/test_capability_ab_runner.py::test_hidden_verifier_infra_error_is_not_trust_mismatch`
- `tests/benchmark/test_capability_ab_runner.py::test_pytest_verifier_cmd_uses_current_python`
- Local replay: `.nexus/reports/bench_local_evidence001_fix_20260501_final/with_nexus_1777600278.jsonl`
