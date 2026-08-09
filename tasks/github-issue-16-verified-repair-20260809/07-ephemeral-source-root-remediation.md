---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: issue16-g4b-ephemeral-source-root
campaign_id: github-issue-16-verified-repair-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/16
source_pr: https://github.com/James3014/Nexus-new/pull/41
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# G4b Ephemeral Source-Root Remediation

## Objective

Close the exact-base impact regression that exposed an environment-dependent
false green in G4: World C source roots under an OS ephemeral temp tree must
fail closed by default and proceed only under the existing explicit
`NEXUS_ARMOR_ALLOW_EPHEMERAL` test/rehearsal allowance.

## Dependencies

Completed G4 World C adequacy projection and PR #41 impact artifact
`exact-base-impact-b629ebb0fe2ec46bcf8cb91982d39c2e33c37531`.

## Allowed files

- `nexus/services/local_heal/pipeline_isolation.py`
- `tests/unit/local_heal/test_world_c_root_receipt.py`

Maximum changed implementation/test files: 2.

## Forbidden scope

No router, verifier, receipt authority, approval, integration, release, public
claim, artifact-root policy, or unrelated test-baseline changes. Do not delete
or weaken the Linux `/tmp` negative control.

## Verification

- `.venv/bin/python -m pytest -q tests/unit/local_heal/test_world_c_root_receipt.py`
- `.venv/bin/python -m pytest -q` for the Issue #16 campaign union
- changed-file Ruff check and preview-format check
- changed-file Pyright
- `git diff --check`

## Required evidence and exit

The default path rejects a source under `/tmp`, `/private/tmp`, or another
existing Armor ephemeral marker before copying. The existing explicit
allowance permits bounded test/rehearsal fixtures. Both behaviors are tested
without relying on platform-specific pytest temp paths.

## Completion receipt

- exact implementation commit:
  `d118833eafae427a852b26156c62c90dcaec849c`
- parent: `f6d6f95c0788c77350c0411ebb5e8de079ede50d`
- independent exact-commit review: `ACCEPT`
- focused World-C receipt verification: `32 passed`
- Issue #16 campaign union: `180 passed`
- changed-file Ruff check and preview-format check: passed
- changed-file Pyright: `0 errors`
- `git diff --check`: passed
- security result: ephemeral World-C source roots fail closed by default; only
  the existing explicit `NEXUS_ARMOR_ALLOW_EPHEMERAL` test/rehearsal allowance
  permits them
- scope result: implementation/test changes confined to the two allowed files;
  no authority surface was widened

## Block classification

`RECOVERABLE_BLOCK` for bounded implementation/test defects; `HARD_BLOCK` for
an artifact-root authority conflict.
