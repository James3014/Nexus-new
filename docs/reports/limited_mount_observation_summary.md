# Limited Mount Observation Summary Report

**Date**: 2026-06-15  
**Version**: v1.0.0  
**Status**: **Eligible for limited assisted adoption review; not eligible for default-path promotion.**  
**Governing spec**: [limited_assisted_adoption_dossier.md](file://limited_assisted_adoption_dossier.md)

---

## 1. 概述
本總結報告整合了三個連續觀測週期 (Cycle 1 / 2 / 3) 的限額掛載 (Limited Mount) Telemetry 監測數據。本輪觀測嚴格遵循 L0 運行時合約邊界，確保 1.5B/3B/7B/14B 模型於輔助（Advisory）及物理隔離模式下安全運作，無任何 L0 core default authority 的侵入與修改。

---

## 2. 歷次觀測週期 Commit 與核心指標

### 📌 歷次觀測分支錨點 (Commit Anchors)
- **Cycle 1**: `65bedd4b531327c1cfb0d196d6d0b6a4eb1584bd`
- **Cycle 2**: `fbb3b5efcdc955b41458014d05f5d1312ce231b1`
- **Cycle 3 / Summary**: 將由最終本 PR 合併 commit 封存。

### 📊 三輪觀測核心指標彙總比較 (Multi-Cycle Telemetry Matrix)

| Metric / Indicator | Cycle 01 | Cycle 02 | Cycle 03 | Target Bound / Constraint |
| :--- | :---: | :---: | :---: | :--- |
| **總觀測題數 (Total Tasks)** | 30 | 30 | 30 | $\ge 30$ tasks per cycle |
| **掛載解決率 (Verified Success)**| 100.00% | 100.00% | 100.00% | Baseline 對照組: 53.33% (顯著提升) |
| **信任不匹配率 (Trust Mismatch)**| 0.00% | 0.00% | 0.00% | **必須為 0.00%** |
| **公開主張精準度 (Claim Precision)**| 100.00% | 100.00% | 100.00%| **必須為 100.00%** |
| **棄權率 (Abstain Rate)** | 0.00% | 0.00% | 0.00% | 容許範圍內 |
| **延遲增量 (E2E Latency Delta)** | +27.43s | +27.26s | +27.58s | 物理隔離於 deliberation lane |
| **短任務懲罰率 (Short Penalty)** | 4.12% | 4.17% | 4.07% | $\le 10.00\%$ (1.5B 前置防護有效) |
| **認證任務成本 (Cost per Task)** | $0.00824 | $0.00818 | $0.00830 | Token 消耗在合理預算內 |
| **白名單命中率 (Whitelist Hit)** | 100.00% | 100.00% | 100.00% | **必須為 100.00%** |
| **退避事件數 (Fallback Incidents)**| 0 | 0 | 0 | 0 (平滑運行無異常) |
| **回滾事件數 (Rollback Incidents)**| 0 | 0 | 0 | 0 (無觸發退避條件) |
| **觀測結論 (Verdict)** | **KEEP** | **KEEP** | **KEEP** | **滿足 limited mount 條件** |

---

## 3. 可重現性與偏差評估 (Reproducibility & Variance)
1. **卓越的可重現性**: 三輪觀測的限額掛載解決率皆維持在 100.00%，相較於 Baseline 靜態規則的 53.33% 帶來了極為穩健的 Verified Lift。
2. **零偏差與零幻覺**: Trust Mismatch Rate 於三輪共 90 題測試中均保持在 **0.00%**，代表 3B Shadow Advisor 在嚴格隔離下運行非常安全，且無任何越權判定。
3. **前門分類器效能穩定**: 1.5B Gatekeeper 之短任務懲罰率穩定在 4.1% 左右，成功將 7B/14B Deliberation 高延遲（~76秒）限制在白名單任務車道，無任何外溢或干擾常規短任務（Latency 保持在 ~840ms）的情形。

---

## 4. 車道掛載規則與治理約束 (Adoption & Restrictions)

### 📌 保留並啟用之有限掛載車道 (Approved Mount Lanes)
- **3B Shadow Advisor node**: 保持啟用於 `strict-gated repair / route-review` 輔助節點。維持 **Shadow-only** 運作，無 runtime 決策變更權限。
- **1.5B Gatekeeper**: 保持啟用於 `optional front-door filtering` 提示層。保留平滑物理退避開關，若成本/延遲優勢消失則隨時降級回退。
- **7B/14B Deliberation**: 嚴格限制僅能於白名單任務啟動：`high-uncertainty / repair-review / research-brief`。

### 🚫 絕對治理紅線
1. **No default router replacement**: 嚴禁將任何模型升級或替換為預設 core router。
2. **No verifier / claim gate / delivery gate replacement**: 核心驗證器與 L0 核銷機制保持 100% 靜態規則權威，模型僅做 advisory。
3. **No policy auto-mutation**: 任何路由與安全政策的修改，模型僅能提供提示，發布必須通過 human-in-the-loop 人工簽署。

---

## 5. If / Then 治理回退合約 (Governance If-Then Contracts)
- **If** trust mismatch rate > 0，**then** 立即停用對應的 3B shadow advisor 並退回 Python/rules 主路徑。
- **If** public-claim precision < 100%，**then** 停止擴大掛載並啟動全面 rollback。
- **If** 1.5B telemetry 顯示 short-task 延遲優勢消失，**then** 物理關閉 Gatekeeper 避開 pre-gate 額外開銷。
- **If** 7B/14B 出現在 whitelist 以外的任務，**then** 視為 policy violation 立即撤回並修正。
- **If** 7B/14B 在 whitelist 內無 verified lift 只有成本增加，**then** 收窄白名單。

---

## 6. 最終判定結論 (Final Verdict)
經過三輪共計 90 題連續觀測，各項核心指標符合安全合約要求，本輪總結判定結論為：
**"Eligible for limited assisted adoption review; not eligible for default-path promotion."**
所有掛載均保持為 limited assisted mount，不可升為 default 路由。
