# DeepSeek L1 Governance Write-back

**artifact_authority:** current
**owner:** James Chen
**status:** IN_PROGRESS
**task_id:** `deepseek-l1-governance-writeback`
**source_issue:** #107

## Objective

Write back the Owner-approved `opencode_deepseek_v4_flash` L1 bounded OpenCode
code-candidate role without changing route authority, Agy authority, or the
unapproved L1.5 reviewer proposal. Deliver one scoped issue branch and PR to
`main`; stop before merge.

## Allowed files

- `tasks/deepseek-l1-governance-writeback-20260811/INDEX.md`
- `tasks/deepseek-l1-governance-writeback-20260811/00-deepseek-l1-governance-writeback.md`
- `nexus/config/model_workforce.yaml`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `tests/contracts/test_model_workforce_policy.py`
- `tests/services/test_model_workforce_policy_loader.py`

## Forbidden scope

- Any other file, including `nexus/config/model_three_arm_matrix.yaml`.
- Agy, loader bypasses, route/default-route selection, runtime integration,
  reviewer/approval/integration/merge/push/production/public authority.
- The post-merge night-queue role successor; it must remain a separate issue
  serialized after this PR's physical merge.
- Global benchmark snapshot completion fields.

## Required implementation

- DeepSeek state/availability/autonomy/default route remain
  `REGISTERED_CONDITIONAL`/`AVAILABLE`/`L1`/`false`.
- Roles become exactly `bounded_candidate_generation` and
  `compact_code_candidate`.
- Remove `second_repetition` and `physical_patch_suite` from operational
  `requires`; preserve R2/R3 and exact OpenCode, PR #84/#85 evidence in a
  dated `requalification_evidence` record with autonomy ceiling L1 and public
  claim false.
- Add the dated Owner-approved policy amendment and preserve the explicit
  L1.5 reviewer proposal NOT APPROVED wording.
- Add minimum contract and generic admission regression assertions and probes.

## Verification and evidence

- `uv run pytest -q tests/contracts/test_model_workforce_policy.py`
- Exact focused Workforce Admission tests discovered in current source.
- Direct exact-model Candidate `ALLOW` probe with all required controls.
- Reviewer/L1.5, missing-control, and wrong-model fail-closed probes.
- Applicable Ruff/static checks, `compileall`, `git diff --check`, complete
  diff/scope audit, staged diff audit, and commit SHA.
- PR receipt must bind base SHA, candidate SHA, card hash, evidence hashes,
  physical PR #84/#85 SHAs, all test/probe results, and maximum claim
  `OWNER_APPROVED_DEEPSEEK_L1_ROLE_WRITEBACK_CANDIDATE_READY`.

## Exit and block policy

Exit is a scoped commit pushed only to the issue branch with an open PR to
`main`, with no merge. A network failure may leave local implementation and
tests complete but blocks push/PR creation as `RECOVERABLE_BLOCK`. Any scope,
authority, evidence-integrity, or specification conflict is `HARD_BLOCK`.
