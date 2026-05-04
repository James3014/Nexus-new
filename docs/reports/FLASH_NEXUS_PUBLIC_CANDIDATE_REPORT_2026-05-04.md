# Gemini 3 Flash + Nexus 公開候選報告（2026-05-04）

## 1) 測試設定（同規格）
- 模型：`gemini-3-flash-preview`
- A/B：`bare` vs `+nexus`
- 題目：`public_benchmark_nexus_value_execution_safe_v1` 共 12 題
- trial：每題 1 次（12x1）
- 執行日期：2026-05-04
- 產物：
  - with_nexus merged: `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/bench_flash_public_12x1_merged_20260504/with_nexus_merged.jsonl`
  - without_nexus merged: `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/bench_flash_public_12x1_merged_20260504/without_nexus_merged.jsonl`
  - auto report: `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/bench_flash_public_12x1_merged_20260504/gemini_flash_nexus_public_report_2026-05-04.md`

## 2) 核心結果
- Usable rows：
  - bare：`10/12`
  - +nexus：`12/12`
- Eligible solve rate：
  - bare：`90.0%`
  - +nexus：`100.0%`
  - 提升：`+10.0pp`
- Semantic verified：
  - bare：`75.0%`
  - +nexus：`100.0%`
  - 提升：`+25.0pp`
- Trust mismatch：
  - bare：`0.0%`
  - +nexus：`0.0%`
- Avg wall time：
  - bare：`55.49s`
  - +nexus：`67.09s`
  - 成本差：`+11.59s`
- Avg model calls：
  - bare：`0.83`
  - +nexus：`1.08`

## 3) 能力證據（本輪）
- 五支柱訊號在 `+nexus` 皆有 evidence（LanceDB / Memory / MemPalace / Belief / Artifact+Claim）。
- Capability public-safe（本輪可宣稱）：
  - `codeintel`, `research`, `memory`, `belief`, `mempalace_gate`, `artifact_gate`, `claim_gate`, `delivery_gate`, `hyper`
- 本輪 selected 但未形成 public-safe 的能力：
  - `ultra_review`, `ddtree`, `autoreason`（部分 row 未達 invoked+evidence+gate）

## 4) Public Claim Gate 判定
- 結果：`FAIL`
- 失敗原因：`run_eligibility_incomplete`
- 具體原因：bare arm 有 `2` 筆 `quota_exhausted`，導致可公開分母不完整。

## 5) 可對外說法（當前版本）
- 可以說：
  - 在本輪 12 題同規格測試中，`+nexus` 的 verified/semantic 指標高於 bare，且 trust mismatch 維持 0。
- 不可說：
  - 「本輪已通過最終 public claim gate」。
  - 「所有能力（含 ultra_review/ddtree/autoreason）均已 public-safe 完整驗證」。

## 6) 下一步（變成可公開最終版）
1. 補跑同規格 12x1（或 12x2）直到 `run_eligibility_complete=PASS`。  
2. 保持 trust mismatch `0`，且 semantic verified 不回退。  
3. 重新產出 public report，要求 gate 全綠後再做最終對外稿。  

