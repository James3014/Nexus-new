# Task Card: 01-impact-coverage.md

- issue: #88
- task_id: github-issue-88
- status: COMPLETED
- frontier_status: TERMINAL_RECONCILIATION
- base_sha: 8f7c75ca08a6c88fad9b791f254d38d79ad8bf29 (historical baseline)
- worker: agy_flash
- provider: agy
- model: gemini-3.6-flash-high
- role: fast_bounded_implementation
- autonomy: L2
- context: nexus_bounded
- terminal_marker: IMPACT_COVERAGE_EVIDENCE_PROVEN
- claim_ceiling: IMPACT_COVERAGE_EVIDENCE_PROVEN_ONLY
- implementation_gate: SATISFIED_BY_PR97_MERGE_CB25EF23
- reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
- current_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
- worker_may_commit: false
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Add evidence-backed impact coverage for PR #86 cleanup surfaces (`scripts/brain_de_entropy.py`, `scripts/core/migration_validator.py`, `scripts/core/drclaw_diagnosis.py`, `muse_nexus.egg-info/SOURCES.txt`).

## Allowed Files (Max 5 implementation/test files)

1. `docs/testing/test_impact_map.md` (EDIT)
2. `tests/core/test_migration_validator_contract.py` (CREATE)
3. `tests/benchmark/test_drclaw_diagnosis_contract.py` (CREATE)
4. `tests/ops/test_source_inventory_integrity.py` (CREATE)
5. `tests/ops/test_select_tests.py` (EDIT)

Task Card authority artifacts in `tasks/github-issue-88-impact-coverage-20260810/` do not count towards the 5 file ceiling.

## Forbidden Scope

- `scripts/ops/pr_impact_gate.py`
- `scripts/ops/select_tests.py`
- `.github/workflows/*`
- `scripts/ops/scope_guard.py`
- `muse_nexus.egg-info/SOURCES.txt`
- PR #86 deleted product files
- PR #87 deleted product files
- Classifier thresholds, exact-base comparison semantics, fallback semantics, fail-closed behavior

## Non-Goals

- Modifying selector or classifier implementation
- Broad directory mappings (e.g. `scripts/`, `scripts/core/`)
- Modifying `SOURCES.txt`
- Claiming PR #86 accepted or production ready

## Mandatory Verification Commands

1. `pytest tests/core/test_migration_validator_contract.py`
2. `pytest tests/benchmark/test_drclaw_diagnosis_contract.py`
3. `pytest tests/ops/test_source_inventory_integrity.py`
4. `pytest tests/ops/test_select_tests.py`
5. `python3 scripts/ops/select_tests.py scripts/brain_de_entropy.py scripts/core/migration_validator.py scripts/core/drclaw_diagnosis.py muse_nexus.egg-info/SOURCES.txt`
6. `ruff check docs/testing/test_impact_map.md tests/core/test_migration_validator_contract.py tests/benchmark/test_drclaw_diagnosis_contract.py tests/ops/test_source_inventory_integrity.py tests/ops/test_select_tests.py`
7. `git diff --check`

## Acceptance Criteria

1. All three new focused tests pass on clean checkout of base.
2. Existing ContextHub tests remain green.
3. `tests/ops/test_select_tests.py` passes and proves all four exact #86 product paths select intended targets without unmatched fallback.
4. Selector probe against exact four #86 product paths shows no `unknown_unmatched` / fallback.
5. Source inventory test passes on pre-#86 main and fails if stale inventory row exists after deletion.
6. No broad mapping added.
7. Ruff and `git diff --check` clean.

## Failure Exit

STOP `IMPACT_COVERAGE_SCOPE_GAP` if truthful coverage cannot be established within the 5 allowed files.

## Candidate Requirements

- Branch: `agy/issue-88-impact-coverage`
- Candidate PR created
- Receipt recorded with base SHA, Task Card SHA-256, Workforce Admission binding, Candidate SHA, verification commands/results, claim ceiling
- No self-approve, no self-merge

## Maximum Supportable Claim

Executable focused coverage and narrow evidence-backed impact mappings exist for the four PR #86 cleanup paths.

## Terminal Reconciliation

Implementation PR #97 MERGED 2026-08-11T00:42:16Z into `main`, head
`ae13d4c4f27916e96a180fb90fd459da5e3c21db`, merge
`cb25ef23cdcc876671803415fa3b430bad817e78`, ancestor of current main
`46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`. Issue #88 is CLOSED with
`state_reason=completed` (2026-08-11T00:42:17Z).

This card is terminally reconciled: `IMPACT_COVERAGE_EVIDENCE_PROVEN` with
claim ceiling `IMPACT_COVERAGE_EVIDENCE_PROVEN_ONLY` and `AUTO_CHAIN=false`.
No selector/CI/product/runtime/route/Workforce/approval/integration/merge/
release/production authority is granted by this reconciliation.
