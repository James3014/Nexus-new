# G20 Learning runtime closure index

```yaml
campaign_id: g20-learning-runtime-closure-20260903
repository: James3014/Nexus-new
base_main: 83353b5ff0c44b2611a45dc7ba9853b6dfe93d44
base_tree: b6092bab54f745971146cf97ac67a699c10492b9
owner_authority: "目標完成g20，沒完成不要回報"
auto_chain: false
```

| Order | Task | Status | Dependency |
|---|---|---|---|
| 1 | `G20-LEARNING-ADOPTION-RUNTIME-WIRING` | MERGED (PR #739) | main `f45c6566521c65da38a8f46a987c54bc468e2dbb` |
| 2 | `G20-GATEWAY-INERT-GITLINK-RECOVERY` | ACTIVE | recovery authority r2 + current main `8f46b3d265a561af05d61d97708c3b107242f29b` |

## Scope

Close only the missing governed Learning-policy adoption runtime seam needed for G20. Reuse the existing `LearningPolicyStore`, `learning_policy_loader`, `CapabilityPlanner`, canonical product task seam, and existing adoption/rollback contracts. Do not create another Router, Planner, policy authority, store, model-promotion authority, or direct executor-side policy mutation.

## Claim ceiling

Source mutation may establish a Candidate only. G20 runtime closure additionally requires exact loaded-runtime identity, physical model/provider consumption, cross-task memory lineage, negative controls, restart reconstruction, rollback, and independent verification.
