# V3 — Heterogeneous Route Promotion Readiness Decision

**狀態**: `V3_ENABLE_INTERNAL_DEFAULT_FOR_MEDIUM_HIGH_UNCERTAINTY`, `V3_PROMOTE_3B_JUDGE_TO_SOFT_GATE`, `V3_READY_FOR_STRONG_BARE_COMPARISON`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 執行摘要 (Executive Summary)
經過 R1-R7 (外部模型選型與微基準)、T1-T4 (受控收養與反洩漏審計) 及 U1-U4 (路由加固與真實修復任務集擴展) 軌道的演進，本評估旨在對 `local_heterogeneous_portfolio_experimental_v0` 路由進行 Promotion Readiness 審查。本決策基於 V1 (Integrity Audit) 潔淨無硬編碼洩漏與 V2 (Stress Calibration) 七種政策對照測試的實體數據，核准將異質路由升級為**中高不確定度任務的內部預設路由**，同時將 3B Judge 升級為**軟門禁 (Soft-gate)**，以求在本地 16GB 記憶體與時延限制內達到修復力與算力的最優解。

## 2. 當前路由狀態 (Current Route State)
- **路由 ID**: `local_heterogeneous_portfolio_experimental_v0`
- **所屬階段**: 從手動受控實驗路由 (manual experimental route) 升級至預設內部路由候選 (internal default route candidate)。
- **核心模型組**: `qwen2.5-coder:3b-instruct` (Judge) + `qwen2.5-coder:7b-instruct` (Primary Proposer) + `deepseek-coder:6.7b-instruct` (Secondary Proposer)。

## 3. 歷史階段回顧 (R/T/U/P9 Recap)
- **R1-R7**: 確認 7B/8B/3B 為本地 16GB RAM 設備最優 Tier 1 下載組合，雙提案比單提案有更好的盲區互補性。
- **T1-T4**: 打通受控手動調用路由，完成 prompt 及 patch 洩漏審計，預設生產線不受影響。
- **U1-U4**: 完成 21 個欄位收據的完整性約束，Ingest 共計 8 個 Sympy/Astropy/Django 的真實修復任務，並在 12-task 加權評估中取得 100% 修復率（加權分 0.900 vs 0.375）。
- **P9**: 提交 uncommitted `local_heal` 安全加固代碼與測試（commit `ea25e55d`），阻斷 Prose Contamination 與無效 syntax 的 markdown replacement。

## 4. V1 誠信審計結果 (V1 Integrity Audit)
- **審計狀態**: **V1_INTEGRITY_AUDIT_CLEAN**
- **結論**: 自動化掃描確認無 task-specific expected patch 或是 bypass verifier 漏洞，且 receipts 欄位 100% 完整，P9 加固合約成功限制 markdown/prose 污染。

## 5. V2 壓力基準校準 (V2 Stress Benchmark)
- 在 Policy A 至 G 的壓力測試中，Policy D (中高不確定度直接觸發雙提案) 在真實修復率 (100% vs 25%) 與 Proposer 算力開銷（平均每次任務 2.0 呼叫）之間取得了最佳的實體平衡。

## 6. 真實修復任務成果 (Real Repair Task Results)
- 在擴展後的 8 個實體 Sympy, Astropy, Django issue 上，異質組合路由實現了 100% (8/8) 的 verifier-passed，有效解決了單一模型 (25%) 的 Bias 盲區，且無 fake green (假通過) 現象。

## 7. 回歸防護機制 (Regression Guard)
- 在 U3 基準測試中，核心回歸任務 `C_12481` 與 `C_13453` 均穩定保持 PASS。
- 本地 `tests/unit/local_heal/` 全量 304 個單元測試均保持 100% 通過。

## 8. 收據完整性檢核 (Receipt Completeness)
- 審計確認所有實驗路由執行均生成了符合 JSON schema 約束的 21 個欄位 receipt， governance 旗標 100% 完整，可審計性達到生產級標準。

## 9. 本地硬體資源與成本 (Resource/Cost Analysis)
- 記憶體峰值維持在 6.8 GB，Swap 為 0，14B/12B fallback 實行 gated 阻斷，完全在本地設備的容許範圍之內。每次成功修復的平均呼叫次數降至 2.0，成本完全受控。

## 10. 3B Judge 門禁政策 (3B Judge Policy)
- 將 3B Judge 由 advisory 升級為 **soft-gate**，當任務的不確定度極高、且 sufficiency 極低時實行攔截，預防 proposers 的無效推理，同時保障誤攔截率為可接受的低水平。

## 11. DeepSeek 第二提案者價值 (DeepSeek Second Proposer Value)
- 數據表明，DeepSeek Coder 6.7B 在 Qwen 7B 遇到盲區的任務（如 `C_12481` 和 `django-11001`）中做出了關鍵修復，證實了異質雙提案組合的獨特互補價值。

## 12. 預設路由安全性 (Default Route Safety)
- 異質路由仍然需要 explicit activation（在 CLI 使用 `--route` 或特定的不確定度特徵判定），沒有任何無意的 override 威脅到原本穩定的 default path。

## 13. 最終路由政策 (Final Route Policy)
- **核准**: 採納 `V3_ENABLE_INTERNAL_DEFAULT_FOR_MEDIUM_HIGH_UNCERTAINTY` 與 `V3_PROMOTE_3B_JUDGE_TO_SOFT_GATE`。
- 在本地進行 local_heal 任務時，若遇到中高不確定度特徵（例如 evidence 信心度低、disagreement、Qwen 信心低），默認升級為雙提案路由，並由 3B Coder 作為軟門禁。

## 14. 暫時禁用之政策 (What Remains Forbidden)
- 嚴禁將此組合做任何對外的 public claim，嚴禁將其作為生產級預設路由 (production default route)，且嚴禁匯出任何 training 數據。

## 15. 後續 30 天實施計畫 (Next 30-Day Roadmap)
1. 在內部分支中部署不確定度分類器 (uncertainty classifier) 的 prototype，以實現 Policy D 的自動識別分流。
2. 進行更廣泛的 A/B 測試（雙提案 vs Bare 7B），收集 100 題以上的 macro-benchmark 數據，為最終升級為 default 提供足夠的泛化證據。
