---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: github-issue-61-wire-golden-pr-gate
campaign_id: github-issue-61-golden-pr-ci-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/61
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Wire Golden Behavior Evaluation into Pull Request CI

## Objective

Add one required-green exact-head Golden Behavior step to the existing
`impact-gate` pull-request job and archive its JSON under the existing
`.ci-impact` evidence directory.

## Baseline and dependency

- GitHub main: `023f6a239871fb3a55ec9b012c67a6e31cb8b45a`
- Issue #46 / PR #50 physically merged
- zero open PRs and no workflow overlap at authorization time

## Allowed source file

- `.github/workflows/pytest.yml`

Maximum source files changed: 1. Task Card files are authorization artifacts.

## Required behavior

- only the pull-request path executes:
  `.venv/bin/python scripts/ops/run_golden_behavior_eval.py --json-report .ci-impact/golden-behavior.json`;
- do not pass `--include-findings`;
- run after exact-head checkout/dependency setup and exact revision validation;
- retain runner nonzero exit behavior as a required-green gate;
- verify the report exists, has schema `nexus.golden_behavior_eval.v1`, and
  `source_revision` equals the exact PR head SHA;
- existing `if: always()` impact artifact upload retains the report;
- push and scheduled full-regression behavior remain unchanged.

## Verification

- workflow YAML syntax validation;
- structural assertions for PR-only reachability, exact command, no findings
  flag, source revision check, and existing artifact path;
- representative local runner execution at exact HEAD;
- `git diff --check` and exact one-source-file scope audit.

## Exit

Exact commit, independent exact-commit review, PR CI proves the Golden step is
reached, JSON artifact is retained, and a covered-case failure is not masked.

## Completion evidence

- pre-mutation card hash:
  `b718d4184d641f081a85538c95a8d3718e8f0a0329aa413b25f2071fc54168ae`
- workflow implementation commits:
  `8f4288f2a93699c64dac7b20040006c65fe683f9` and
  `e81ba9257923187f62dc45c69a27ae40c406fe69`
- first live PR run proved step reachability and exposed missing Git author
  identity; the correction is step-local and does not restore credentials
- corrected exact-head review: `ACCEPT`, no P0/P1 findings
- corrected PR CI run `31345682548`: all required checks passed; Golden runner
  returned 103 passed, exit 0, exact source revision, expected schema, and
  `findings_included_in_eval=false`
- artifact path remains `.ci-impact/golden-behavior.json` under the existing
  `if: always()` upload
- branch was re-anchored after PR #66 to
  `main=14dd1f29183b09646215462b97b0dd0feb8c0743`; the workflow source diff did
  not change during that re-anchor

## Forbidden scope

No corpus/runner/test/production changes, duplicate schedule, second workflow,
route/lifecycle/Workforce/verifier/approval/release change, merge, or broad
claim about witness quality.

## Block classification

`RECOVERABLE_BLOCK` for YAML or reachability defects; `HARD_BLOCK` if another
open branch/PR begins modifying the same workflow.
