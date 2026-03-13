# Muse-Nexus Acceptance Checklist

## Purpose

這份文件用來驗收 agent 或人工完成的 implementation slice，避免「看起來有改」但實際沒有符合 migration strategy。

## Acceptance Scope

適用於第一波 internal-path implementation：

- contracts
- state io
- context hub
- skills router skeleton
- repair / diag minimal integration

## Contract Checks

- [ ] 新欄位名稱與 `09_STATE_CONTRACT_DRAFT.md` 一致
- [ ] JSON/JSONL 仍是唯一權威 state 格式
- [ ] legacy 任務缺欄位時可安全讀取
- [ ] `schema_version` / `current_phase` / `current_step_id` / `steps_history` 有合理 default
- [ ] `external_needed` / `skills_used` / `external_used` 未破壞舊流程

## Context Hub Checks

- [ ] 已有獨立 context assembly 模組
- [ ] 至少能產生 D / R / A 三種 context pack
- [ ] 不直接把 TOON 寫回 state
- [ ] 記憶、reflection、research slot 為 additive integration

## Skills Router Checks

- [ ] 已有表驅動 routing skeleton
- [ ] 由 phase + metadata 做 selection
- [ ] skill 結果有明確 write-back target
- [ ] 第一波沒有硬接大量真 skill execution

## Repair / Diag Checks

- [ ] Repair path 可讀 `repair_context_pack`
- [ ] Repair path 會寫 reflection round
- [ ] Diag path 可輸出結構化 diagnosis
- [ ] Diag / Repair 可設定 `needs_research` 或 `external_needed`
- [ ] 第一波未強制接真 external routing

## Compatibility Checks

- [ ] 舊任務或舊欄位不會導致 crash
- [ ] 現有 core import 沒被破壞
- [ ] 不相關腳本未被大範圍重構
- [ ] dashboard / memory engine 未被誤改

## Scope Checks

- [ ] 實作沒有超出 `11_FIRST_CUT_FILE_PLAN.md`
- [ ] 沒有大量搬移目錄
- [ ] 沒有提前清理 historical snapshot
- [ ] 沒有將 TOON 引入 contract / state 層

## Verification Checks

- [ ] 至少做了 import/smoke verification
- [ ] touched files 有基本執行或讀寫驗證
- [ ] 回報包含 changed files、未完成項目、風險

## Merge Decision

只有在下面條件都成立時，才建議 merge：

- [ ] 契約命名正確
- [ ] 範圍受控
- [ ] 舊流程未被破壞
- [ ] 第一條 internal path 已經更接近可打通

## Practical Conclusion

Muse-Nexus 第一波 implementation 的驗收標準，不是功能看起來很多，而是：

> 是否在不破壞現有系統的前提下，讓 contract-driven 架構真正開始落地。
