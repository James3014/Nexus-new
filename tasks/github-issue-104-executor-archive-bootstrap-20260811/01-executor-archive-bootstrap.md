---
artifact_authority: current
owner: James Chen
status: active
purpose: Repair fail-closed executor extraction for explicitly rejected external links.
issue: 104
---

## Objective

Bootstrap the executor from a trusted source archive that contains an
irrelevant absolute or outside-destination link without weakening Python's
`tarfile` `data` protections or changing executor isolation, evidence, cleanup,
token, workflow, route, lifecycle, permission, auth, or dependency behavior.

## Inputs and first failure

- Baseline `main=6c8ad898ad52b5b7569cf3878b1b59c39bd5da0e`.
- Protected run `31466863912`, controller PASS.
- Exact failure: in a non-Git executor cwd, `tarfile.extractall(filter="data")`
  raises `AbsoluteLinkError` for irrelevant absolute symlink
  `.antigravitycli/f3125a4f-4c98-4d7c-878d-7546220e2d52.json` before pytest.
- Same-seam sibling sweep: exactly one extraction call.

## Allowed files

- `scripts/ops/trusted_deletion_anchor.py`
- `tests/ops/test_trusted_deletion_anchor.py`
- `tasks/github-issue-104-executor-archive-bootstrap-20260811/INDEX.md`
- `tasks/github-issue-104-executor-archive-bootstrap-20260811/01-executor-archive-bootstrap.md`

File-count ceiling: four files; setup and implementation commits are separate.

## Required behavior

- Preserve `tarfile`'s `data_filter` and all protections it supplies.
- Omit only link entries explicitly rejected as absolute or outside-destination
  links; never omit absolute member paths, devices, or other unsafe archive
  forms that `data_filter` rejects.
- Safe regular files and selected tests extract and execute from a non-Git cwd.
- Unsafe external links do not materialize; tampering and other unsafe archive
  forms remain fail-closed.
- Keep evidence schema and deterministic binding unchanged unless skipped paths
  can be recorded without widening authority; otherwise record nothing.

## Forbidden scope

No #75 semantics, workflow, permissions, auth, route, lifecycle, dependency or
network installation, cleanup/token/executor isolation changes, setup-python or
uv installation, archive-wide refactor, Candidate/approval/integration,
push/PR/comment/merge, or production/public claim.

## Verification

1. Exact RED archive reproducer before implementation.
2. Focused trusted-anchor suite.
3. Ruff check and format preview, YAML parse, compile, `git diff --check`,
   allowed-file and tracked-deletion audits, staged/unstaged stats, and full
   staged diff.

## Evidence and exit

Bind evidence to the implementation commit and this card hash. The claim
ceiling is `EXECUTOR_ARCHIVE_BOOTSTRAP_REPAIR_CANDIDATE`; approval, integration,
push, merge, release, and production truth remain unresolved next gates.

## Block classification

- `RECOVERABLE_BLOCK`: focused verifier or environment failure.
- `HARD_BLOCK`: any need to weaken `data_filter`, widen files, or change an
  authority boundary.
