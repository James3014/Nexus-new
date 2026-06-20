# V4-B.1 MC007 Direct Patch Real Replay

## Status: V4B1_DIRECT_PATCH_PASS_INTERNAL_ONLY

## Results

| Field | Value |
|-------|-------|
| task_id | MC007 |
| instance_id | astropy__astropy-12907 |
| execution_mode | real |
| source_git_sha | 95df21d |
| model_used | qwen2.5-coder:7b |
| model_calls | 1 |
| cloud_api_used | false |
| match_authority | verbatim |
| success_attribution | model_patch_success |
| export_classification | model_patch_success_candidate |
| task_scoped | true |
| public_claim_allowed | false |
| training_eligible | false |

## V4-B Stability Check

MC007 reproduces MC001 pattern:
- VERBATIM authority ✅
- model_patch_success attribution ✅
- task_scoped verifier ✅
- governance preserved ✅

Direct model patch lane is stable across 2 tasks (MC001 + MC007).
