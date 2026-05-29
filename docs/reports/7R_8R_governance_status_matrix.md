# 7R/8R 狀態治理與前置條件總表

本報告為 Phase 1 交付物，做為 7R/8R 狀態治理的 SSOT 狀態總表，列出 blocked reason、closeout artifacts、禁止事項與唯一的 reopen SOP，用以徹底排除後續狀態漂移。

---

## 📊 7R/8R 狀態治理矩陣 (Governance Status Matrix)

| 治理維度 | 實體定位與規範 | 機器可讀與實體文件 Refs |
| :--- | :--- | :--- |
| **當前真實狀態** | **🔴 RED / Blocked (Exit C)** (未解鎖 public claim) | [walkthrough.md](file:///Users/jameschen/.gemini/antigravity/brain/48f675b5-8e99-47c3-a9f9-69e9afccee70/walkthrough.md) |
| **P0 阻塞根因** | `pub-bug-004` (provider-token combine blocker) | [7R_pub_bug_004_exclusion_verdict.md](file:///Users/jameschen/Workspace/nexus/docs/reports/7R_pub_bug_004_exclusion_verdict.md) |
| **除障實體工單** | 鎖定為 `pub-bug-004` blocker-specific closeout | [blocker_closeout_action.md](file:///Users/jameschen/Workspace/nexus/.nexus/policy/blocker_closeout_action.md) |
| **實施與硬化計劃** | Phase 1 ~ 5 E2E 系統硬化與狀態分流 | [7R_8R_SYSTEM_HARDENING_AND_GOVERNANCE_PLAN.md](file:///Users/jameschen/Workspace/nexus/docs/plans/7R_8R_SYSTEM_HARDENING_AND_GOVERNANCE_PLAN.md) |
| **證據總表記錄** | 彙整標準、自我修復與長超時 replay telemetry 差異 | [7R_pub_bug_004_evidence_matrix.md](file:///Users/jameschen/Workspace/nexus/docs/reports/7R_pub_bug_004_evidence_matrix.md) |
| **尋址決策報告** | 研判四類 clean path，結論為 `exclusion_recommended` | [7R_pub_bug_004_clean_path_decision.md](file:///Users/jameschen/Workspace/nexus/docs/reports/7R_pub_bug_004_clean_path_decision.md) |

---

## 🚫 治理禁止事項 (Prohibitions)

1. **不得混淆成功敘事**：
   - 嚴禁將 `chunk rollup PASS` 或單臂 `route-stability PASS` 說成 public claim / promotion-ready 完成。
2. **不得弱化門檻**：
   - 不得因成本壓力降低 cost gates 或 provider-token gates 門檻，亦不得將 local fallback 冒充為 model-cost evidence。
3. **不得重複無效測試**：
   - 停止所有基於既有 replay 變體的翻綠嘗試；不再回頭大改 restart 框架或擴增 orchestration 層。

---

## 🔄 唯一允許的 Reopen SOP (Reopen SOP)

未來只有在以下六項條件**同時成立**的情況下，才允許重新打開 audited combine 或執行 full rerun，否則永久維持 exclusion 隔離：
1. **Verified delivery** (通過 hidden 冪等性正規化檢驗)
2. **Model-causal path** (模型主動參與且 causality 成立)
3. **Provider-token measured = True** (在 sandbox 內實體測得 provider tokens)
4. **Route-policy evidence = PASS**
5. **Expected capability evidence = PASS**
6. **Combine eligibility = PASS**

### **重開執行三步 (MANDATORY)**:
`row-level targeted replay` ➔ `audited combine` ➔ `outcome decision` (禁止跳步，亦禁止自 dashboard 反推)。

---
*Status Matrix Created: 2026-05-29 (Phase 1 Complete)*
