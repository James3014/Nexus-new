# 🧬 Nexus Phase 7: Controlled Experiment & Autonomy Operations

## 🎯 核心目標
將已封存的 A-D 治理鏈轉化為可持續的運行制度。透過 270 天的受控實驗與分階段放行，在維持 fail-closed 的前提下，實現數據驅動的成本自治與效能優化。

## 📅 實作里程碑 (2026-06-02 ~ 2027-03-01)

### Milestone 1: Phase 7-A 治理基線凍結 (Baseline Freeze)
- [ ] **T7.1**: 發布 `governance_baseline_manifest.v1.json`，鎖定 Commit `708b362ea`。
- [ ] **T7.2**: 建立 `failure_taxonomy_v1.md`，統一 A-D 段失敗定義。
- [ ] **T7.3**: 建立 A/B/C/D 四段 Replay 樣本池與自動化驗證。

### Milestone 2: Phase 7-B 受控實驗擴張 (Observation Expansion)
- [ ] **T7.4**: 執行 30-90 天的 Observation-only 擴大樣本收集。
- [ ] **T7.5**: 產出月度治理指標板 (Governance Dashboard)。

### Milestone 3: Phase 7-C 策略收斂與政策化 (Policy Formulation)
- [ ] **T7.6**: 定義各任務類別 (Task Class) 的 Autonomy Policy 分級。
- [ ] **T7.7**: 實裝一鍵回滾 (One-click Rollback) 與 RCA 模板。

### Milestone 4: Phase 7-D 有限放行與自治實驗 (Limited Rollout)
- [ ] **T7.8**: 啟動特定類別的窄門 Canary 實驗。
- [ ] **T7.9**: 產出最終自治效能結案報告。

---

## 📈 成功標準 (Acceptance Criteria)
1. **基線不動**: 任何優化實驗不得導致 stop-layer 一致性下滑。
2. **數據完整**: 100% 的 Canary Run 必須具備對應的理由碼與邊界收據。
3. **治理守恆**: 維持 `Promotion Effect: NONE`，不污染公共門禁。

[NEXUS STATUS: PHASE 7 OPERATIONS INITIATED]
