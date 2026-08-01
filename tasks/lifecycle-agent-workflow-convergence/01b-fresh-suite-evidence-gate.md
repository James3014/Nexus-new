# Task Card: lifecycle-workflow-p1b-fresh-suite-evidence-gate

artifact_authority: current
owner: James Chen
status: COMPLETED_PENDING_OWNER_REVIEW
task_id: lifecycle-workflow-p1b-fresh-suite-evidence-gate
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Provide a cache-independent, revision-bound pytest closure manifest before
continuing lifecycle P2/P3. The manifest is evidence only and cannot replace
Task Cards, lifecycle state, or route authority.

## Dependencies

- `lifecycle-workflow-p1-action-envelope` integrated.
- `tasks/bootstrap-authority-convergence/09-context-budget-and-overlay-gates.md`
  owner review remains a prerequisite for lifecycle P2.

## Allowed files

- `scripts/ops/nexus_fresh_suite.py`
- `tests/ops/test_nexus_fresh_suite.py`
- `tasks/lifecycle-agent-workflow-convergence/INDEX.md`
- `tasks/lifecycle-agent-workflow-convergence/01b-fresh-suite-evidence-gate.md`

## Forbidden scope

- No runtime routing, provider, receipt, or lifecycle-state changes.
- No new database, MCP server, router, or persistent report under `docs/`.
- No mutation of worktrees, refs, branches, or canonical source files.
- Do not infer a product Bug from a legacy checkout or pytest cache.

## Contract

- Collection and execution both use `--cache-clear`.
- Manifest binds branch, HEAD, dirty state, exact pytest args, collected nodeids,
  JUnit outcomes, and failure-domain fingerprints.
- Empty collection, collection failure, test failure, or JUnit parse failure is
  `FAIL` and never produces a PASS claim.
- Output is caller-selected evidence; default operation should use `/tmp` or an
  external evidence store, not a tracked report directory.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-fresh-pycache uv run pytest -q tests/ops/test_nexus_fresh_suite.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-fresh-pycache uv run python scripts/ops/nexus_fresh_suite.py --output /tmp/nexus-fresh-suite.json -- tests/ops/test_nexus_fresh_suite.py
git diff --check
```

## Exit criteria

The script emits `nexus.fresh_suite_manifest.v1`; the focused tests prove
nodeid, JUnit, HEAD/dirty binding, cache clearing, and empty-collection
fail-closed behavior. P2 remains blocked until this card and the bootstrap
owner-review gate are explicitly accepted.

## Block classification

- `RECOVERABLE_BLOCK`: local pytest/tooling failure with changes preserved.
- `HARD_BLOCK`: inability to bind the manifest to a revision or evidence
  authority conflict.
