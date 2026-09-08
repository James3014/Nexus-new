# Issue873 GB006 canonical demand conflict repair

status: READY
owner: James Chen
source_issue: James3014/Nexus-new#873
baseline: c05005088564afc1bba5111f9c4036c82e175f30
worker_may_commit: false
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
AUTO_CHAIN=false

## Objective and authority

Owner active engineering goal requires complete #65 product behavior and renewed 繼續完成不要停下來. This separate Ready Issue/card fixes the previously reproduced GB006 prerequisite without expanding existing GateC card. Primary physical Owner-goal receipt: /private/tmp/frontier-plan/issue873-owner-goal-receipt.json. Existing resident onboarding PR871 is merged; runtime19 worker owns a different repository. No shared active production edits in this scope.

## Allowed files (maximum four)

- nexus/engine/canonical_task_seam.py
- tests/contracts/test_canonical_execution.py
- tasks/gb006-workforce-demand-conflict-20260908/00-repair.md
- tasks/gb006-workforce-demand-conflict-20260908/INDEX.md

Worker owns only first two; card/index controller-only.

## Required behavior

Reject repeated local or online execution_channel before bindings can overwrite, with stable canonical_workforce_demand_conflict:<channel>. Reject identical-role duplicates as ambiguous too. Preserve legitimate local+online separate resolution, missing/malformed denial, all current route/admission and canary behavior. No new route/provider/model choices or policy changes.

## Verification

Capture RED on exact base for duplicate local and online demands. GREEN targeted tests then full tests/contracts/test_canonical_execution.py plus tests/contracts/test_workforce_admission_contract.py and tests/contracts/test_model_workforce_policy.py. Test actual _resolve_policy_workforce_bindings, no pseudo-consumer. Run mapped GB006 via canonical Golden evaluator after controller candidate commit. Ruff exact-base/check/preview-format and git diff --check. Keep all existing node IDs. No test weakening.

## Boundaries and exit

No deletions, schema migration, lifecycle/runtime/Gateway/control-plane writes, deployment, global policy/default changes, unrelated cleanup or #143. Luna provides uncommitted scoped diff and real test artifacts; primary independently validates, commits/pushes issue branch and applies exact protected PR gates. Stop as candidate evidence; worker cannot accept or merge. New unexpected scope/authority gap stops affected slice. Known baseline debt must be classified exact-base, not mislabeled as regression.
