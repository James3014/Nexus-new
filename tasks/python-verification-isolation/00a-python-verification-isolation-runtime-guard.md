# Python Verification Isolation Runtime Guard

**artifact_authority:** current
**owner:** James Chen
**status:** COMPLETED
**candidate:** `5e44ce7fe97d65797503e6e14607d2100fb436fb` integrated at `bf6afeddf921128b061a6bc65f6228650f22627d`
**task_id:** `python-verification-isolation-runtime-guard`
**supersedes:** `python-verification-isolation-guard`
**AUTO_CHAIN:** false
**controller_base_revision:** `06bd067d814e7667cbdcb40fe31e9fcfcd1d330a`
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Implement the successor runtime-only Python verification isolation guard after RepositoryContractGate correctly rejected AGENTS.md policy self-modification in python-verification-isolation-guard. Enforce subprocess isolation, candidate state verification, and commit environment cleanup without modifying AGENTS.md.

## Required behavior

- `run_cli_worker()` always launches subprocesses with `PYTHONDONTWRITEBYTECODE=1`, even when a caller attempts to override it to `0`.
- Candidate verification captures candidate state after verifiers run.
- Any verifier-created, modified, or deleted repository path changes the Candidate state hash and produces `verifier_mutated_candidate_state` fail-closed status.
- CandidateCommitter forces `MUSE_RUN_CODEX_LOOP=0` around the scoped git commit and restores the original process environment in `finally`.
- The Learning Closure Matrix records the concrete root cause and prevention contract.
- Owner-governance follow-up for AGENTS.md policy update is recorded for owner execution after runtime integration.

## Allowed files

- `tasks/python-verification-isolation/INDEX.md`
- `tasks/python-verification-isolation/00-python-verification-isolation-guard.md`
- `tasks/python-verification-isolation/00a-python-verification-isolation-runtime-guard.md`
- `nexus/executors/cli_worker.py`
- `nexus/orchestrator/candidate_verifier.py`
- `nexus/orchestrator/candidate_commit.py`
- `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`
- `tests/nexus/executors/test_cli_worker.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/nexus/orchestrator/test_candidate_commit.py`

## Forbidden scope

- No modification to `AGENTS.md`.
- No tracked bytecode deletion in this card.
- No Model Workforce, LocalHeal committee, routing, planner, provider, learning pipeline, Context Map, or campaign-frontier changes.
- No new verifier, receipt builder, router, runtime, or report.
- No Controller edit, approval, integration, push, or successor activation by the Worker.

## Verification commands

```bash
python3 -m pytest -q tests/nexus/executors/test_cli_worker.py tests/nexus/executors/test_worker_contract.py tests/nexus/executors/test_codex_executor.py tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_controller.py
git diff --check
```

## Required evidence

- Regression test proves an explicit `PYTHONDONTWRITEBYTECODE=0` request is overridden to `1` and no `.pyc` is created.
- Regression test proves an exit-zero verifier that creates a file cannot produce a verified Candidate (`verifier_mutated_candidate_state`).
- Regression test proves CandidateCommitter forces `MUSE_RUN_CODEX_LOOP=0` during commit and restores outer environment.
- No tracked deletion is present.
- Scoped commit SHA and durable Candidate ref are bound to this Task Card hash.

## Exit criteria

- All verification commands pass.
- Exactly the allowed files are touched.
- AGENTS.md remains unmodified.
- Candidate is committed and protected.
- `tracked-bytecode-cleanup-core` remains inactive until this Candidate is integrated.

## Claim ceiling

Allowed:

- `PYTHON_VERIFICATION_ISOLATION_RUNTIME_GUARD_CANDIDATE_READY`
- `VERIFIER_SIDE_EFFECT_FAIL_CLOSED_VERIFIED`

Must remain false:

- `AGENTS_MD_MODIFIED`
- `TRACKED_BYTECODE_REMOVED`
- `CONTROLLER_INTEGRATED`
- `PRODUCTION_READY`
- `PUBLIC_CLAIM_ALLOWED`
