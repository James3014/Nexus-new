# Issue 1384 — Completion Liveness: Prevent Requalification Starvation Under Unrelated Main Churn

- task_id: `issue-1384-main-drift-liveness`
- campaign_id: `issue-1384-completion-liveness`
- status: `VERIFIED`
- owner: `James Chen (James3014)`
- coordinator: `Antigravity Engineer`
- issue: `https://github.com/James3014/Nexus-new/issues/1384`
- durable_marker: `MAIN_DRIFT_COMPLETION_LIVENESS_ENFORCED`
- AUTO_CHAIN: `false`

## Objective

Prevent requalification starvation of accepted immutable Candidates under sustained main movement churn.
Ensure that:
1. Four consecutive unrelated main movements during exact-head CI can converge to CAS merge without Owner interruption.
2. Immutable source Candidate identity and independent acceptance remain stable across all unaffected integration generations.
3. IRRELEVANT_MAIN_MOVEMENT performs no fresh Candidate acceptance.
4. TEST_IMPACT reruns only the affected test evidence unless the impact classifier proves semantic/authority identity changed.
5. Candidate-owned blob equivalence is mechanically bound for every integration generation.
6. Exact-head required checks remain fresh per generation; stale I_n CI may never satisfy I_(n+1).
7. A main move immediately before merge re-enters bounded requalification without Owner interruption.
8. Repeated ordinary drift can converge to the existing expected-base/expected-head CAS merge primitive without manual branch reconstruction.
9. Generation/time exhaustion returns a truthful deferred/concurrency disposition, not FRESH_CANDIDATE_ACCEPTANCE_REQUIRED solely because main moved.
10. Semantic overlap, authority drift, transport drift, unknown impact, changed Candidate blob, conflict, or expired authority still fail closed.
11. Bounded integration generation maximum is widened from 3 to 10 with relative generation counting from start generation.

## Allowed Files

- `nexus/orchestrator/github_completion_loop.py`
- `nexus/orchestrator/github_orchestration.py`
- `tests/nexus/orchestrator/test_github_completion_loop.py`
- `tasks/issue-1384-completion-liveness/00-issue-1384-main-drift-liveness.md`
- `tasks/issue-1384-completion-liveness/INDEX.md`

## Acceptance Criteria

1. Deterministic regression reproduces at least four consecutive unrelated main movements while one accepted Candidate is waiting on exact-head CI.
2. Immutable source Candidate identity and its independent acceptance remain stable across all unaffected integration generations.
3. IRRELEVANT_MAIN_MOVEMENT performs no fresh Candidate acceptance.
4. TEST_IMPACT reruns only the affected test evidence unless the impact classifier proves semantic/authority identity changed.
5. Candidate-owned blob equivalence is mechanically bound for every integration generation.
6. Exact-head required checks remain fresh per generation; stale I_n CI may never satisfy I_(n+1).
7. A main move immediately before merge re-enters bounded requalification without Owner interruption.
8. Repeated ordinary drift can converge to the existing expected-base/expected-head CAS merge primitive without manual branch reconstruction.
9. Generation/time exhaustion returns a truthful deferred/concurrency disposition, not FRESH_CANDIDATE_ACCEPTANCE_REQUIRED solely because main moved.
10. Semantic overlap, authority drift, transport drift, unknown impact, changed Candidate blob, conflict, or expired authority still fail closed.
11. One live high-concurrency pilot proves: multiple unrelated merges occur during CI, full Candidate re-acceptance count remains zero, the final integration generation merges by exact CAS, and post-merge readback is correct.

## Verification Evidence

- **Unit/Regression Tests**:
  - `pytest tests/nexus/orchestrator/test_github_completion_loop.py`: 58 passed in 0.67s.
  - Dedicated regression coverage for criteria 1, 4, 7, 8, 9, and 10 added with deterministic cryptographic hash proofs and multi-step drift oracles.
- **Lint / Formatting**:
  - `ruff check nexus/orchestrator/github_completion_loop.py tests/nexus/orchestrator/test_github_completion_loop.py`: 0 errors.
  - `ruff format --check nexus/orchestrator/github_completion_loop.py tests/nexus/orchestrator/test_github_completion_loop.py`: all clean.
- **Claude Code Review (`claude-sonnet-4-6` via agy CLI)**:
  - Dispatched via `./scripts/ops/nexus-agy-dispatch --mode plan --model claude-sonnet-4-6`.
  - **Verdict**: APPROVED (zero blockers).
  - Validated: relative generation budgeting, preservation of fail-closed boundaries on authority/blob drift, exact CI freshness per generation, and accurate concurrency disposition on budget exhaustion.

## Claim Ceiling

Source candidate and verified test suite only. No unilateral acceptance, merge, runtime activation, or release authority.
