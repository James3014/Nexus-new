# NEXUS SF Runtime Replacement Declaration V8

## Status
- `REPLACED`: SF V8 已取代 runtime overlay primary skill。
- `runtime_update_allowed=true`
- `sf_runtime_replacement_complete=true`
- `public_benchmark_allowed=false`

## Primary Skill Mapping
- `repair_loop` -> `tdd`
- `forecast_pregate` -> `create-plan`
- `research_and_source_discipline` -> `research-citation-chain-verifier`
- `governance_and_trust` -> `acceptance-evidence-failclosed`

## Runtime Load
```bash
export NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY=docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V8_2026-05-18.json
export NEXUS_RUNTIME_SKILL_POLICY_OVERLAY=docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V8_2026-05-18.json
```

## Complete Replacement Flow
1. source intake: 新 skill 只能進 candidate intake；不得直接 runtime mount -> DONE
2. capability bucket: 先映射到 Nexus 新路由能力分類，再進同能力候選池 -> DONE
3. paired compare: Flash+Nexus without skill vs Flash+Nexus+skill；比較 delivery/trust/token/wall/receipt -> DONE
4. seal: selected/injected/used/evidence/gate/outcome 六段鏈必須成立 -> DONE
5. catalog verdict: 寫入 capability-skill catalog；產生 primary/alternate/reject -> DONE
6. replacement approval: 由 evidence-approved apply review 判定，不由人工喜好挑選 -> DONE
7. runtime replacement: V8 runtime overlay 寫入 primary_skill_by_capability，runtime resolver 載入後即以新 skill 為 primary -> DONE
8. post-apply smoke: runtime-final receipt 再確認四個 primary 都有 contract，且 violation=0 -> DONE
9. ledger: applied_primary / held_alternate / rejected 分流落帳 -> DONE
10. future replacement loop: 新 skill 若勝出，重走 1-9；勝出後替換 overlay primary 並追加 ledger -> DONE

## Future New Skill Replacement Rule
- 同能力候選比較，不跨 capability 混選
- challenger 必須先贏 current primary 的 paired compare
- challenger 必須通過 seal 與 post-apply smoke
- 勝出後更新 overlay primary，舊 primary 移到 held_alternate 或 rejected
- 每次替換必須追加 replacement ledger，不覆寫歷史

## Evidence
- `overlay`: `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V8_2026-05-18.json`
- `post_apply_smoke`: `docs/reports/NEXUS_SF_RUNTIME_POST_APPLY_SMOKE_V8_2026-05-18.json`
- `apply_result`: `docs/reports/NEXUS_SF_RUNTIME_APPLY_RESULT_V8_2026-05-18.json`
- `ledger`: `docs/reports/NEXUS_SF_RUNTIME_REPLACEMENT_LEDGER_V8_2026-05-18.json`
- `pairing_table`: `docs/reports/NEXUS_SF_CAPABILITY_SKILL_PAIRING_TABLE_V8_2026-05-18.md`
