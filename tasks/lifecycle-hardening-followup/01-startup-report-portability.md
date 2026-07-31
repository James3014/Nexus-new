# Task Card 01: Startup Report Path Portability

## Identity

- task_id: `startup-report-path-portability`
- campaign_id: `lifecycle-hardening-followup`
- artifact_authority: current
- status: READY
- owner: James Chen
- depends_on: `orphan-workspace-reconciliation` audit complete
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Make the enforced startup gate usable from a clean or read-only source worktree by routing its report and ACK persistence to an explicit writable machine-state directory. Preserve fail-closed behavior when that directory is missing or unwritable; do not silently write generated state into the source checkout.

## Allowed files

- `scripts/ops/nexus_startup_contract_check.py`
- `scripts/ops/start_codex_nexus_enforced.sh`
- `scripts/ops/start_gemini_nexus_enforced.sh`
- `tests/ops/test_nexus_startup_contract_check.py`
- `tests/ops/test_start_gemini_nexus_enforced.py`

## Forbidden scope

No canonical-root mutation; no changes to Task Card authority semantics, workforce policy, route selection, provider/model behavior, cleanup, branch/ref deletion, P6 cutover, or GitNexus instructions. Do not weaken freshness, policy, or worktree gates.

## Required behavior

1. A launcher supplies a writable report/state directory without requiring writes under the checkout.
2. An explicit environment or argument remains available for operators and tests.
3. Missing/unwritable report storage returns a structured fail-closed result.
4. The ACK binds the same worktree, HEAD, INDEX/card, and policy hashes as before.
5. Tests cover both writable external state and source-checkout write denial.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/ops/test_nexus_startup_contract_check.py tests/ops/test_start_gemini_nexus_enforced.py
NEXUS_STARTUP_REPORT_DIR=/private/tmp/nexus-startup-portability-proof NEXUS_TASK_INDEX=tasks/bootstrap-authority-convergence/INDEX.md PYTHONDONTWRITEBYTECODE=1 python3 scripts/ops/nexus_startup_contract_check.py
git diff --check
```

## Evidence required

- RED reproduction showing default source-checkout persistence fails or is unsafe.
- GREEN focused tests and external-state `ENFORCED` ACK.
- Exact commit SHA and scoped diff with no deletions.

## Exit criteria

The launcher and direct checker use explicit writable machine state, preserve all existing gates, focused tests pass, and a scoped commit is created.

## Residual debt

Verifier Target integrity and authorized-deletion contract remain separate cards. Workspace cleanup and P6 remain owner-gated.

## Block classification

- `RECOVERABLE_BLOCK`: test/runtime environment cannot provide a writable temp state directory.
- `HARD_BLOCK`: fixing portability would require weakening fail-closed startup authority or mutating the canonical root.
