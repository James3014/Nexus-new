# 17_CAPABILITY_GAP_AND_PRIORITY: Nexus v9 實作優先級與路徑 (校準版)

> [!abstract] 核心目標
> 本文件評估 15 項能力與現有 Nexus 的差距，並根據當前「Runner + Gate + Token 治理」的主線目標重新定義優先級。

---

## 🏗️ 實作優先級 (Updated Priority)

### P0: Runner/Gate/Token 治理 (核心主線)
- [ ] **8. Token-Guardian** (節省 50%+ 成本，防止 Context 溢出)
- [ ] **1. XState-Flow-Architect** (Commander 的狀態機底座，解決邏輯混亂)
- [ ] **2. RootSeeker-v3** (將修復成功率提升至 90% 以上)
- [ ] **7. Side-Effect-Scanner** (Gate 的安全守衛，防止性能回歸)

### P1: 品質與並行效率
- [ ] **3. Committee-Reviewer** (多模型共識，消除單模型偏見)
- [ ] **4. Hybrid-Reranker-Pro** (提升教案搜尋的精確度)
- [ ] **6. Dependency-Mapper** (重構前的風險分析)
- [ ] **13. Parallel-Executor-Worktree** (吞吐量提升 2x)
- [ ] **10. Pattern-Extractor** (經驗自動結晶化)
- [ ] **11. Log-Oracle** (日誌模式匹配加速診斷)
- [ ] **12. Rule-Porter v5** (全域規則同步)

### P2: 擴充與治理優化
- [ ] **5. WebApp-UAT-Playwright** (自動化 UI 驗證)
- [ ] **9. Multi-Strategy Repair** (備選修復方案生成)
- [ ] **14. Knowledge-De-Entropizer** (知識庫去熵)
- [ ] **15. Chaos-Agent-Tester** (魯棒性壓力測試)

---

## 🚀 導入建議 (Adoption Roadmap)

### Adopt Now (P0)
- **能力編號**: **1, 2, 7, 8**
- **理由**: 這些是 Nexus v9 轉型為「自主 OS」的生命線。Token 治理 (8) 解決錢的問題，XState (1) 解決腦的問題，RootSeeker (2) 解決手（診斷）的問題，Side-Effect (7) 解決安全的問題。

### Adopt Next (P1)
- **能力編號**: **3, 4, 6, 10, 11, 12, 13**
- **理由**: 當核心 Runner 穩定後，這些能力將大幅提升「開發品質」與「並行產出效率」。特別是多模型審核 (3) 與重排器 (4) 對於複雜教案的精確度至關重要。

### Adopt Later (P2)
- **能力編號**: **5, 9, 14, 15**
- **理由**: 屬於邊際效益遞減後的「高級加固項」。當系統已經非常穩定後，才需要進行大規模的混沌測試 (15) 或 UI 自動化 (5)。

---

## 🛠️ 技術前提 (Prerequisites)
1. **Canonical Path Alignment**: 已完成 `./scripts/core/` 檔案所有權標定。
2. **State Contract Versioning**: 需先將 `current_phase` 與 `retry_count` 等欄位寫入 `state_contracts.py`。

---
%% 
由 Muse-Core 指揮官於 2026-03-18 產出。
校準內容：實體路徑對位、證據路徑補齊、優先級主線對齊。
%%
