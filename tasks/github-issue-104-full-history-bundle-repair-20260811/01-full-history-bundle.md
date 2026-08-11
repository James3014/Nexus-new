---
artifact_authority: current
owner: James Chen
status: active
purpose: Ensure exact base/head Git objects are complete enough for an immutable bundle.
issue: 104
supersedes: tasks/github-issue-104-basic-auth-repair-20260811/01-basic-auth-transport.md
---

## Objective

Remove the shallow boundary that makes `git bundle create` fail for PR merge
heads, while preserving exact-source identity, data-only head handling,
credential isolation, executor isolation, and fail-closed evidence.

## Inputs

- `main=9ab955513f09f4a3d4d2ccc5ee7c45c6fc124ee5`.
- PR #118 head `5d25c5687ef394f54987929ca54efb4f6a059557`.
- Protected run `31461647892`.
- Exact failure: `_create_git_bundle` invokes `git bundle create`, which exits
  128 because `_controller` fetched the merge head with `--depth=1` and Git
  cannot traverse its parents.
- Local independent reproducer: shallow exact head/base fetch reproduces
  `Failed to traverse parents of commit`.
- Issue authority comment
  `https://github.com/James3014/Nexus-new/issues/104#issuecomment-5249340750`.

## Allowed files

- `scripts/ops/trusted_deletion_anchor.py`
- `tests/ops/test_trusted_deletion_anchor.py`
- `.github/workflows/trusted-deletion-anchor.yml` only if required to preserve
  the same complete object-fetch invariant
- `tasks/github-issue-104-full-history-bundle-repair-20260811/INDEX.md`
- `tasks/github-issue-104-full-history-bundle-repair-20260811/01-full-history-bundle.md`

File-count ceiling: these five files only; prefer no workflow change.

## Required behavior

- The trusted controller fetches exact head/base commits without creating a
  shallow boundary before `_create_git_bundle`.
- Verify both exact commits and exact trees before diff, archive, and bundle
  creation; reject missing, substituted, or mutable refs.
- Produced bundle must contain `refs/trusted-anchor/base` and
  `refs/trusted-anchor/head` resolving to the event's exact SHAs and preserve
  enough ancestry to verify the raw diff and trees in the trusted verifier.
- Preserve head/base as Git objects only in trusted jobs: no checkout,
  worktree, submodule, import, source, interpreter/config execution, or head
  hook.
- Preserve process-local Basic auth, credential-free URL/config/artifacts,
  failure/signal cleanup, workflow/blob/mode/hash binding, verifier
  independence, and executor byte equivalence.
- Add a real merge-head shallow reproducer test that is RED on the current
  `--depth=1` implementation and GREEN after the repair.

## Forbidden scope

No product change, selector/impact behavior change, permissions expansion,
checkout/worktree/submodule, untrusted execution in trusted jobs, credential
persistence/exposure, ruleset/App, admin/manual bypass,
Candidate/approval/integration authority, release, cleanup, or production
claim.

## Verification

- `.venv/bin/pytest -q tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/python -c "import pathlib,yaml; assert isinstance(yaml.safe_load(pathlib.Path('.github/workflows/trusted-deletion-anchor.yml').read_text()), dict)"`
- `.venv/bin/ruff check scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/ruff format --check --preview scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/python -m compileall -q scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py`
- `git diff --check`
- allowed-file, tracked-deletion, staged/unstaged stat, and complete staged-diff
  audits

## Commit and continuation

Commit Task Card setup separately. Worker may commit only implementation/test
files after all checks pass; it may not push, merge, approve, or claim final
acceptance. Require independent hostile review and normal exact-base gates.
Merge claim is only `FULL_HISTORY_BUNDLE_REPAIR_INSTALLED`.

After physical merge, rebind PR #118 and require a fresh exact-head protected
controller -> executor -> verifier PASS before #104/#75 may close.

## Block classification

- `RECOVERABLE_BLOCK`: bounded Git object-depth or test defect.
- `HARD_BLOCK`: untrusted execution, credential exposure, permission/evidence
  weakening, extra file, or need for a security exception.
