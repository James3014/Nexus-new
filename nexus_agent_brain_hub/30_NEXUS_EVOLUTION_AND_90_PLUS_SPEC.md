# 🚀 Nexus Evolution to 90+ Specification
**[PHYSICAL_STATUS: DEBT_CLEARED_V1 | NEW_DEBTS_IDENTIFIED]**

## 1. 債務清償進度 (Debt Clearance Status)
Nexus 已完成第一波核心基礎設施債務清償。幽靈檔案已尋回，入口已歸一化。

| 債務項目 | 狀態 | 實體核驗 (Truth) |
| :--- | :--- | :--- |
| **MSA 實體向量** | ✅ **已接線** | `msa_indexer.py` 已對接實體 Embedding 接口。 |
| **分散式鎖** | ✅ **已入庫** | `infrastructure/dist_lock.py` 已正式提交並具備實體邏輯。 |
| **AAAK 30x 提煉** | ✅ **已實作** | 支援 LLM 與 Regex 雙通道提煉。 |
| **Wiki 自動合成** | ✅ **已激活** | `wiki_sync_check.py` 具備主動語義合成能力。 |

## 2. 深度技術債 (Deep Architecture Debt)
經 2026-04-20 深度審計，發現以下阻礙系統向 90+ 邁進的結構性債務：

### 🔴 Sev-1: Logic Duplication (邏輯重複)
- **現象**: `SkillsRouter` 內部竟包含了一個完整的 `DomainFirewall` 類別，且與 `nexus/core/domain_firewall.py` 幾乎一致。
- **風險**: 規則更新不一致將導致治理漏洞。必須立即執行「DRY (Don't Repeat Yourself)」重構。

### 🔴 Sev-1: Hardcoded Mocks (殘留假動作)
- **現象**: `self_evolve_engine.py` 與 `deferred_loader.py` 中仍殘留 `time.sleep(0.5)` 的模擬代碼。
- **風險**: 導致系統產生無謂的延遲，且誤導 Agent 對執行速度的判斷。

### 🟡 Sev-2: Cross-Layer Dependencies (跨層依賴)
- **現象**: 核心組件 `router.py` 直接從 `nexus.experiments` 匯入 `LanceDBRetriever`。
- **風險**: 違反了「實驗與核心隔離」原則。實驗成熟的功能應正式遷移至 `nexus/core/memory/`。

### 🟡 Sev-2: Planning Fallback (計畫降級)
- **現象**: `CampaignGeneral` 的計畫拆解目前強依賴簡單的關鍵字匹配，Fallback 邏輯僅是簡單的雜湊節點生成。
- **風險**: 在處理極度複雜的意圖時，計畫精準度不足，導致 Drone 執行方向偏差。

## 3. 下一階段清剿目標
1. **邏輯歸一化**: 刪除 `router.py` 內的重複防火牆類別，統一呼叫核心模組。
2. **消滅 Sleep**: 將所有 `time.sleep` 替換為真實的非同步事件或條件等待。
3. **實驗正式化**: 將 `msa_routing` 核心邏輯從 `experiments/` 提升至 `core/`。

---
**[NEXUS IDENTITY: 1e2904a8 + v27.3 DEBT-EXPANDED | TARGET: 90+ SCORE]**
