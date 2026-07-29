# Python Verification Isolation Guard

**artifact_authority:** current
**owner:** James Chen
**status:** PENDING
**task_id:** `python-verification-isolation-guard`
**AUTO_CHAIN:** false
**controller_base_revision:** `06bd067d814e7667cbdcb40fe31e9fcfcd1d330a`
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Prevent governed Worker and verifier execution from rewriting tracked Python bytecode or silently changing Candidate state. Convert the existing lesson into deterministic runtime enforcement, Candidate commit environment isolation, and regression tests.

## Required behavior

- `run_cli_worker()` always launches subprocesses with `PYTHONDONTWRITEBYTECODE=1`, even when a caller attempts to override it to `0`.
- Candidate verification captures state after verifiers run.
- Any verifier-created, modified, or deleted repository path changes the Candidate state hash and produces `verifier_mutated_candidate_state`.
- A verifier may exit zero while the Candidate still fails closed because of side effects.
- Controller-unchanged claims require before/after Git status evidence; Worker prose is not sufficient.
- Candidate commit environment is isolated so `MUSE_RUN_CODEX_LOOP` cannot trigger unrelated full-repository drift scans during governed scoped commits.
- The Learning Closure Matrix records the concrete root cause and prevention contract without creating a parallel report.

## Allowed files

- `AGENTS.md`
- `nexus/executors/cli_worker.py`
- `nexus/orchestrator/candidate_verifier.py`
- `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`
- `tests/nexus/executors/test_cli_worker.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`

## Forbidden scope

- No tracked bytecode deletion in this card.
- No Model Workforce, LocalHeal committee, routing, planner, provider, learning pipeline, Context Map, or campaign-frontier changes.
- No new verifier, receipt builder, router, runtime, or report.
- No Controller edit, approval, integration, push, or successor activation by the Worker.

## Verification commands

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/nexus/executors/test_cli_worker.py \
  tests/nexus/executors/test_worker_contract.py \
  tests/nexus/executors/test_codex_executor.py \
  tests/nexus/orchestrator/test_candidate_verifier.py \
  tests/nexus/orchestrator/test_worktree_manager.py \
  tests/nexus/orchestrator/test_self_hosted_controller.py

git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git diff --stat
git diff --cached --stat
```

## Required evidence

- Regression test proves an explicit `PYTHONDONTWRITEBYTECODE=0` request is overridden to `1` and no `.pyc` is created.
- Regression test proves an exit-zero verifier that creates a file cannot produce a verified Candidate.
- Candidate commit environment isolation prevents `MUSE_RUN_CODEX_LOOP` from triggering unrelated full-repository drift scans during governed scoped commits.
- Exact before/after Target status hashes are identical across the test run.
- No deletion is present.
- Scoped commit SHA and durable Candidate ref are bound to this Task Card hash.

## Exit criteria

- All verification commands pass.
- Exactly the six allowed files are changed.
- Candidate is committed and protected.
- Candidate remains pending independent approval and governed integration.
- `tracked-bytecode-cleanup-core` remains inactive until this Candidate is integrated.

## Recovery and block policy

Temporary missing tools, stale Target state, or test-environment issues must be safely recovered and retried on the same card. They may not terminate the run as a final recoverable block. Stop only for owner decision, unsafe architecture conflict, or an active valid Worker owning the serial Target.

## Claim ceiling

Allowed:

- `PYTHON_VERIFICATION_ISOLATION_GUARD_CANDIDATE_READY`
- `VERIFIER_SIDE_EFFECT_FAIL_CLOSED_VERIFIED`

Must remain false:

- `TRACKED_BYTECODE_REMOVED`
- `CONTROLLER_INTEGRATED`
- `PRODUCTION_READY`
- `PUBLIC_CLAIM_ALLOWED`
