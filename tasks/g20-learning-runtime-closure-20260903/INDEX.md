# G20 Learning runtime closure index

```yaml
campaign_id: g20-learning-runtime-closure-20260903
repository: James3014/Nexus-new
base_main: 4cebc4d5a59260ded0240bef7a2c5f7c7bf9286e
base_tree: 4b5ed0765cead74414e6d587293ec6bb2f6ca993
owner_authority: "目標完成g20，沒完成不要回報"
auto_chain: false
```

| Order | Task | Status | Dependency |
|---|---|---|---|
| 1 | `G20-LEARNING-ADOPTION-RUNTIME-WIRING` | ACTIVE | G19 source closure + current main |

## Scope

Close only the missing governed Learning-policy adoption runtime seam needed for G20. Reuse the existing `LearningPolicyStore`, `learning_policy_loader`, `CapabilityPlanner`, canonical product task seam, and existing adoption/rollback contracts. Do not create another Router, Planner, policy authority, store, model-promotion authority, or direct executor-side policy mutation.

## Claim ceiling

Source mutation may establish a Candidate only. G20 runtime closure additionally requires exact loaded-runtime identity, physical model/provider consumption, cross-task memory lineage, negative controls, restart reconstruction, rollback, and independent verification.
