---
artifact_authority: current
owner: James Chen
status: active
purpose: Use GitHub-compatible Basic auth without credential persistence or argv exposure.
issue: 104
supersedes: tasks/github-issue-104-no-checkout-trusted-source-20260811/01-no-checkout-trusted-source.md
---

## Objective

Repair the exact-SHA bare Git fetch in the trusted controller and verifier by
using GitHub-compatible Basic authentication while preserving every
no-checkout, no-head-execution, token-isolation, cleanup, and evidence gate.

## Inputs

- `main=7f0902453e7e8cfbec270f2b2681dd1c2add9ea6`.
- PR #118 head `b581c55b6b84ce2031eccef6dee73db5acbc03a3`.
- Protected run `31460192921`.
- Exact failure in both trusted fetches:
  `fatal: could not read Username for 'https://github.com'`.
- Issue #104 durable root-cause comment
  `https://github.com/James3014/Nexus-new/issues/104#issuecomment-5249171776`.

## Allowed files

- `.github/workflows/trusted-deletion-anchor.yml`
- `tests/ops/test_trusted_deletion_anchor.py`
- `tasks/github-issue-104-basic-auth-repair-20260811/INDEX.md`
- `tasks/github-issue-104-basic-auth-repair-20260811/01-basic-auth-transport.md`

File-count ceiling: these four files only.

## Required behavior

- Build the HTTP Basic value from `x-access-token:<github.token>` using a
  portable base64 command, validate it is non-empty and single-line, and pass
  `Authorization: basic <encoded>` only through process-local
  `GIT_CONFIG_VALUE_0` shell-prefix environment.
- Never place raw or encoded credentials in argv, Git config, remote URL,
  helper/file, stdout/stderr, artifact, receipt, or a later step.
- Ensure both the initial exact workflow-SHA fetch and the trusted controller's
  exact base/head fetch use the same bounded process environment.
- Preserve credential-free remote URL, exact workflow SHA/ref/path,
  commit/blob/mode/blob-id/SHA-256 binding, failure/signal cleanup, and the
  independently fetched verifier.
- Preserve the unprivileged executor byte-equivalent to the PR #132 baseline:
  `permissions: {}`, no checkout, token, secret, cache, repository workspace,
  or privileged step.
- Add executable hostile tests that distinguish rejected Bearer transport from
  accepted Basic transport without contacting GitHub or leaking a test token.

## Forbidden scope

No checkout, worktree, submodule, persisted credentials, token in argv,
untrusted head execution in a trusted job, permission expansion, #75 verifier
change, selector/impact change, ruleset/App change, admin/manual bypass,
Candidate/approval/integration authority, release, cleanup, or production
claim.

## Verification

- `.venv/bin/pytest -q tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/python -c "import pathlib,yaml; assert isinstance(yaml.safe_load(pathlib.Path('.github/workflows/trusted-deletion-anchor.yml').read_text()), dict)"`
- `.venv/bin/ruff check tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/ruff format --check --preview tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/python -m compileall -q tests/ops/test_trusted_deletion_anchor.py`
- `git diff --check`
- allowed-file, tracked-deletion, staged/unstaged stat, and complete staged-diff
  audits

## Commit and continuation

Commit Task Card setup separately. Worker may commit only workflow/test changes
after all checks pass; it may not push, merge, approve, or claim acceptance.
Require independent hostile review and normal exact-base gates. Merge claim is
only `BASIC_AUTH_TRANSPORT_REPAIR_INSTALLED`.

After physical merge, rebind PR #118 and require a fresh exact-head protected
controller -> executor -> verifier PASS before #104/#75 may close.

## Block classification

- `RECOVERABLE_BLOCK`: bounded auth-format or test defect.
- `HARD_BLOCK`: any credential persistence/exposure, untrusted execution,
  permission expansion, evidence weakening, extra file, or security exception.
