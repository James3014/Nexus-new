---
artifact_authority: current
owner: James Chen
status: active
purpose: Replace trusted checkout with immutable no-checkout source acquisition.
issue: 104
supersedes: tasks/github-issue-104-gitlink-checkout-repair-20260811/01-gitlink-safe-checkout-teardown.md
---

## Objective

Make the Issue #104 trusted controller and verifier independent of
`actions/checkout` by acquiring only exact-default-branch trusted source in an
ephemeral bare Git repository, while preserving immutable evidence identity,
token isolation, executor isolation, and fail-closed behavior.

## Inputs and dependency

- Issue #104 body and CONTRACT_DELTA comment
  `https://github.com/James3014/Nexus-new/issues/104#issuecomment-5248969210`.
- `main=fdb23157f4c8a78bd43dfc3cde7165a5c62b1bac`.
- PR #118 head `9c29279c153e7e1ee79bcfe7d7810dc3ec41b5a3`.
- Protected run `31458024882`.
- Exact failure: `actions/checkout` invokes immediate credential removal and
  fails on tracked gitlink `SWE-bench` before any later workflow step can add
  local `.gitmodules` metadata.

## Allowed files

- `.github/workflows/trusted-deletion-anchor.yml`
- `tests/ops/test_trusted_deletion_anchor.py`
- `tasks/github-issue-104-no-checkout-trusted-source-20260811/INDEX.md`
- `tasks/github-issue-104-no-checkout-trusted-source-20260811/01-no-checkout-trusted-source.md`

File-count ceiling: one workflow, one hostile test module, and these two Task
Card files.

## Required behavior

- Remove `actions/checkout` from trusted controller and trusted verifier.
- In each trusted job, initialize an ephemeral bare repository under
  `RUNNER_TEMP`, fetch the exact 40-character `github.workflow_sha`, and prove
  the fetched commit equals that SHA.
- Assert the trusted event, repository, default branch, workflow ref/path, and
  workflow SHA before executing any fetched blob.
- Materialize only an allowlisted regular blob from the trusted commit:
  `scripts/ops/trusted_deletion_anchor.py`. Reject missing, symlink, gitlink,
  tree, or unexpected mode/object type. Record its Git blob id and SHA-256 in a
  bounded local receipt before execution.
- The controller may fetch exact base/head commits as Git objects and process
  them only as data. It must never check out, import, source, or execute PR-head
  content. Preserve all existing bundle, tree, diff, inventory, digest,
  tamper/replay, and workflow-identity gates.
- Keep the repository remote URL credential-free. Authentication may exist
  only in the bounded trusted acquisition/controller step environment; never
  persist it in Git config, remote URL, helper/file, artifact, receipt, output,
  or a later step.
- Remove the obsolete gitlink metadata workaround. Add `if: always()` cleanup
  that deletes the ephemeral bare repository and trusted blob directory and
  proves no credential-bearing Git config or file remains.
- Preserve the executor exactly: `permissions: {}`, no checkout, token,
  secrets, cache, credentials, repository workspace, or added privileged step.
- Preserve controller `contents: read` and verifier `contents: read,
  actions: read`; do not broaden workflow permissions.

## Forbidden scope

No `persist-credentials: true`, normal checkout, worktree, submodule operation,
head-code execution in a trusted job, credential in a Git URL/config/file,
admin/manual bypass, skipped/neutral success, product change, #75 verifier
change, selector/impact change, OpenWiki change, ruleset/App configuration,
Candidate/approval/integration authority, cleanup, release, or production
claim. Do not weaken `IMPACT_UNKNOWN` or existing hostile assertions.

## Verification

- `.venv/bin/pytest -q tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/python -c "import pathlib,yaml; assert isinstance(yaml.safe_load(pathlib.Path('.github/workflows/trusted-deletion-anchor.yml').read_text()), dict)"`
- `.venv/bin/ruff check tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/ruff format --check --preview tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/python -m compileall -q tests/ops/test_trusted_deletion_anchor.py`
- `git diff --check`
- allowed-file, tracked-deletion, staged/unstaged stat, and complete staged-diff
  audits

Hostile tests must prove no checkout/worktree/submodule use, exact workflow
SHA/ref/path/repository assertions, exact regular-blob mode/object/hash binding,
credential-free remote/config/receipt, cleanup on success and failure, no
trusted execution of head content, unchanged executor isolation, least
privilege, and all previous substitution/tamper/evidence cases.

## Commit, review, and continuation

The Task Card setup is committed separately. The worker may commit only the
workflow and hostile test module after all checks pass; it may not approve,
merge, clean up, or claim acceptance. Push/open a PR to `main`; require an
independent hostile review and all normal exact-head CI green. Merge claim is
only `NO_CHECKOUT_TRUSTED_SOURCE_REPAIR_INSTALLED`.

After physical merge, rebind PR #118 and require a fresh exact-head protected
controller -> executor -> verifier run. Only that successful run may satisfy
#104 acceptance and permit #75/PR #118 to proceed.

## Block classification

- `RECOVERABLE_BLOCK`: bounded workflow/test defect or transient GitHub run.
- `HARD_BLOCK`: credential persistence, untrusted execution in a trusted job,
  permission expansion, evidence weakening, extra file requirement, or need
  for an Owner security exception.
