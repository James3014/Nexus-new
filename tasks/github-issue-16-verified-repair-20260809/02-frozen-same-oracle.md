---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: issue16-g2-frozen-same-oracle
campaign_id: github-issue-16-verified-repair-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/16
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# G2 Frozen Same-Oracle Fail to Pass

## Objective

Freeze exact oracle command/content/source identity before mutation and require the
same oracle to fail on base and pass on Candidate; drift and tamper fail closed.

This gate is intentionally restricted to a structured Python-script oracle:

- command is `(resolved_python_executable, resolved_oracle_py, *literal_args)`;
- the oracle script is exactly the second command argument and arbitrary
  `python -c`, shell, or generic executable forms are rejected;
- oracle, source, and suite are three distinct regular non-symlink files;
- base and Candidate are distinct existing workspace directories;
- one descriptor-held sealed oracle snapshot is used for both physical runs.

Trusted verifier source integrity is supplied by the repository/source hash
gate. G2 does not claim resistance to an attacker who can mutate the executing
Python module itself.

## Dependencies

G1 physical provenance contract merged into this branch.

## Allowed files

- `nexus/services/local_heal/phases/verification.py`
- `tests/unit/local_heal/test_isolated_verifier.py`

Maximum changed files: 2.

## Forbidden scope

Reproduction implementation, evaluation/World C/mutation files, routing,
approval/integration, and public claims.

## Verification

- `.venv/bin/python -m pytest -q tests/unit/local_heal/test_isolated_verifier.py`
- `git diff --check`

## Required evidence and exit

Oracle identity/hash plus bound base FAIL and Candidate PASS receipts. Base already
passing, Candidate failing, hash tamper, command/source/suite drift, command-form
substitution, symlink/same-file material, or workspace reuse all fail closed.
Maximum claim: same-oracle Candidate evidence.

## Block classification

`RECOVERABLE_BLOCK` for bounded verifier defects; `HARD_BLOCK` for authority conflict.

## Completion receipt

- Implementation commit: `a574923a8fdc85cb4c8b90baa5073199b2528df6`
- Exact-commit independent review: ACCEPT
- Exact tests: 37 passed
- Command, material, workspace identity, tamper/drift, receipt, Ruff format,
  diff, scope, and deletion gates passed
