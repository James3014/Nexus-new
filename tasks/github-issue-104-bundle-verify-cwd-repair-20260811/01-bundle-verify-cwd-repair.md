---
card_id: github-issue-104-bundle-verify-cwd-repair-20260811/01
status: in_progress
authority: Owner-authorized Ready Issue #104
baseline: 374348c89e7814e11d55e00ea397dc5a6effe471
claim_ceiling: BUNDLE_VERIFY_CWD_REPAIR_CANDIDATE
---

# Bundle verification cwd repair

## Objective

Repair the production `git bundle verify` invocation so an absolute bundle
path is verified with an ephemeral bare repository as its bound cwd. Preserve
the controller/verifier path, bundle contents, execution tokens, checkout and
worktree invariants, and all existing behavior outside this defect.

## Allowed files

- `scripts/ops/trusted_deletion_anchor.py`
- `tests/ops/test_trusted_deletion_anchor.py`
- this campaign `INDEX.md`
- this card

## Forbidden scope

- Any workflow file or workflow behavior change.
- Any route, lifecycle, approval, promotion, Candidate, release, or production
  state change.
- Any checkout, worktree, HEAD execution, token, authentication, or bundle
  format change.
- Any other repository file, generated artifact, cleanup, reset, stash, rebase,
  force-push, ref deletion, push, PR, merge, or comment.

## Required evidence and verification

- Record the exact mechanism: absolute bundle path succeeds from bare-repo cwd
  and fails from non-repository cwd.
- Add a hostile regression that runs the verifier/controller bundle path from a
  non-repository cwd and is RED at the baseline and GREEN after the repair.
- Preserve all existing 29 trusted-anchor tests.
- Run the trusted-anchor suite, YAML parse, Ruff check and preview format,
  compileall, `git diff --check`, scope/deletion audits, and complete staged
  diff inspection.

## Exit criteria

The smallest production change binds bundle verification to the ephemeral bare
repo, the hostile non-repository-cwd regression passes, the existing suite
remains green, all required structural/security checks pass, and implementation
is committed separately from this setup commit. This card does not authorize
approval, integration, push, PR, merge, cleanup, or a claim above the stated
ceiling.

## Block class

`RECOVERABLE_BLOCK` for environment/test failures; `HARD_BLOCK` for scope,
authority, security-invariant, or evidence-integrity conflicts.
