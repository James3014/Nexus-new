---
artifact_authority: current
owner: James Chen
status: ACTIVE
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

## Forbidden scope

No corpus/runner/test/production changes, duplicate schedule, second workflow,
route/lifecycle/Workforce/verifier/approval/release change, merge, or broad
claim about witness quality.

## Block classification

`RECOVERABLE_BLOCK` for YAML or reachability defects; `HARD_BLOCK` if another
open branch/PR begins modifying the same workflow.
