---
artifact_authority: current
owner: James Chen
status: active
purpose: Make trusted checkout teardown compatible with tracked gitlinks that lack .gitmodules URLs.
issue: 104
---

## Objective

Repair the trusted controller and trusted verifier checkout teardown failure
observed in the first real post-bootstrap `pull_request_target` run without
executing untrusted gitlink content or weakening credential/evidence isolation.

## Inputs and dependency

- Reopened Issue #104 body and latest CONTRACT_DELTA comment.
- `main=fffc127cbb91bf1d06940f4a021c6e3011e96cce`.
- Protected run `31456472233`, PR #118 head
  `df77c50e01e492bbf91757d9e68a7a504335e43d`.
- Exact failure in controller and verifier checkout post-cleanup:
  `fatal: No url found for submodule path 'SWE-bench' in .gitmodules`.
- Existing exact-base workflow compatibility pattern that derives local
  `.gitmodules` entries only from tracked mode-160000 index records.

## Allowed files

- `.github/workflows/trusted-deletion-anchor.yml`
- `tests/ops/test_trusted_deletion_anchor.py`
- `tasks/github-issue-104-gitlink-checkout-repair-20260811/INDEX.md`
- `tasks/github-issue-104-gitlink-checkout-repair-20260811/01-gitlink-safe-checkout-teardown.md`

File-count ceiling: one workflow, one hostile test module, and these two Task
Card files.

## Required behavior

- In trusted controller and trusted verifier jobs only, after trusted checkout
  and before post-job cleanup, enumerate NUL-delimited `git ls-files --stage`
  records and select only mode `160000` paths.
- For each such path lacking `.gitmodules` metadata, write a local path entry
  and URL `.` solely so `actions/checkout` credential cleanup can traverse the
  index without failing.
- Do not initialize, update, fetch, checkout, import, execute, or inspect
  gitlink content. Do not use a remote/external URL.
- Preserve every checkout's `persist-credentials: false` and `submodules: false`.
- Preserve the unprivileged executor exactly: `permissions: {}`, no checkout,
  secrets, cache, credentials, repository workspace, or added step.
- Preserve all controller/verifier evidence identity, digest, bundle, tree,
  and tamper/replay gates.

## Forbidden scope

No product, #75 verifier, selection, impact classifier, OpenWiki, ruleset/App,
Candidate/lifecycle/approval/integration, deletion, cleanup, release, or
runtime changes. Do not hide the failure with continue-on-error, skip, neutral,
or ignored checkout errors. Do not weaken existing hostile assertions.

## Verification

- `.venv/bin/pytest -q tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/python -c "import pathlib,yaml; assert isinstance(yaml.safe_load(pathlib.Path('.github/workflows/trusted-deletion-anchor.yml').read_text()), dict)"`
- `.venv/bin/ruff check tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/ruff format --check --preview tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/python -m compileall -q tests/ops/test_trusted_deletion_anchor.py`
- `git diff --check`
- allowed-file, deletion, staged/unstaged stats, and complete staged-diff audit

Required tests prove both trusted checkout jobs install the local gitlink
metadata step, executor does not, every generated URL is `.`, no gitlink
content command is admitted, checkout flags remain safe, and all previous
hostile cases remain green.

## Exit and continuation

Commit only the two implementation/test files after tests pass, with Task Card
setup committed separately. Push/open a PR to `main`; require independent
hostile review and all current required CI green. Merge claim is only
`TRUSTED_CHECKOUT_TEARDOWN_REPAIR_INSTALLED`.

After physical merge, rebind PR #118 again and require one new exact-head
controller -> executor -> verifier protected run before #104 or #75 may close.

## Block classification

- `RECOVERABLE_BLOCK`: bounded workflow/test defect.
- `HARD_BLOCK`: external permissions/ruleset need, any untrusted code
  execution, need to weaken checkout/evidence isolation, or additional file
  requirement.
