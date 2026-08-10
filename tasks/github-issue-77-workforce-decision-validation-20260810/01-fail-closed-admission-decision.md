---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: github-issue-77-workforce-decision-validation
campaign_id: github-issue-77-workforce-decision-validation-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/77
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: Fail-Closed WorkforceAdmissionDecision Values

## Objective

Make `WorkforceAdmissionDecision` fail closed when `decision` is not an
`AdmissionDecision` enum value, at both construction and raw-mapping runtime
boundaries. A forged arbitrary string must not construct or serialize as a
valid admission decision.

## Inputs and dependencies

- Issue #77 is P1 READY and Owner-authorized (DeepSeek auto-claim queue 3/5).
- Evidence baseline: main `84eaa6886e0388a4e15f5b837c89e37768b14307`.
- Defect confirmed by Owner pre-mutation comment (2026-08-10T02:51:54Z):
  `WorkforceAdmissionDecision` currently accepts and serializes arbitrary
  strings, members of the wrong enum family, null, and malformed objects.
- Two boundaries must be repaired:
  1. `WorkforceAdmissionDecision` constructor (`__post_init__` strict
     `AdmissionDecision` membership check).
  2. Raw-mapping boundary `nexus/services/runtime_workforce_admission.py:
     _decision_dict()`, so malformed mapping decisions cannot bypass the
     dataclass.
- No exact file overlap with PR #81 (orchestrator files only), #70/#71, or
  active #7 implementation files. Final integration must rerun #7
  admission/dispatch focused tests (runtime contract is consumed conceptually).

## Allowed files

- `nexus/contracts/workforce_admission.py`
- `nexus/services/runtime_workforce_admission.py`
- `tests/contracts/test_workforce_admission_contract.py`
- `tests/services/test_runtime_workforce_admission.py`
- `tasks/github-issue-77-workforce-decision-validation-20260810/INDEX.md`
- `tasks/github-issue-77-workforce-decision-validation-20260810/01-fail-closed-admission-decision.md`

Maximum changed files: 6.

## Forbidden scope

- route selection, CapabilityPlanner authority, policy YAML, provider/model
  selection, lifecycle semantics, CI, Golden corpus
- any file outside the allowed scope above

## Required behavior

- Valid ALLOW, BLOCK, ESCALATE decisions retain current serialization.
- Unknown strings, wrong enum families, null, and malformed deserialized
  values fail closed before a receipt can be treated as valid.
- No silent coercion; existing callers receive deterministic validation
  errors.
- Route authority remains CapabilityPlanner/HybridRouteDecision; this repair
  only validates admission output.

## Verification

- Focused workforce admission contract tests including forged decision
  negatives.
- Current admission caller tests selected by exact impact.
- Ruff, Pyright exact-base differential, `git diff --check`.
- Canonical Golden evaluator for GB-021/GB-025 mapping.
- If API compatibility requires broader files, stop and reconcile rather than
  widening.

## Required evidence and exit criteria

- Constructor rejects arbitrary string, wrong enum family, null, malformed
  objects with a deterministic ValueError.
- `_decision_dict` rejects malformed raw mappings whose decision value is not
  ALLOW/BLOCK/ESCALATE.
- Valid ALLOW/BLOCK/ESCALATE construction and serialization unchanged.
- Focused contract + service tests, exact-impact callers, #7 admission/dispatch
  regression, static differential gates, and diff gate pass.
- Golden GB-021/GB-025 mapping passes.

Maximum claim: fail-closed admission decision validation at constructor and
raw-mapping boundaries. No route/policy/workforce authority change.

## Completion receipt

- Task Card authorization commit: `24bc0cc6c`
- implementation head: `95f2b0d56`
- PR: https://github.com/James3014/Nexus-new/pull/85
- constructor boundary: `WorkforceAdmissionDecision.__post_init__` rejects
  non-`AdmissionDecision` values (arbitrary strings, wrong enum families,
  null, malformed objects) with a deterministic `ValueError`
- raw-mapping boundary: `_decision_dict` rejects non-canonical decision values
  so malformed mapping decisions cannot bypass the dataclass or serialize as
  valid admission decisions
- valid ALLOW/BLOCK/ESCALATE construction and serialization unchanged;
  existing callers all pass `AdmissionDecision` members
- verification: 35 focused contract/service tests; 84 contract + Golden
  GB-021/GB-025 + model policy loader + unified runtime admission tests;
  36 #7 admission/dispatch focused orchestrator tests; 151 combined targeted
  tests passed
- contracts/services sweep: identical 117 pre-existing environment failures
  on base and Candidate (zero regression); 476 passed
- Ruff exact-base differential: zero new findings (same 4 pre-existing)
- Pyright exact-base differential: prod/runtime 0 = base 0; contract test 0;
  runtime test 1 = base 1 (pre-existing line 243)
- `git diff --check`: clean
- reached `CANDIDATE_PR_READY` (PR opened to `main`; no self-approve/merge)

## Block classification

- `RECOVERABLE_BLOCK`: bounded implementation or regression defect.
- `HARD_BLOCK`: acceptance requires route/policy/workforce authority mutation,
  lifecycle changes, CI edits, or files outside the frozen scope.
