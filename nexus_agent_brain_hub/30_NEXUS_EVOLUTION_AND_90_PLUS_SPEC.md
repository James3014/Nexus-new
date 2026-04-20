# 🚀 Nexus Evolution to 90+ Specification
**[PHYSICAL_STATUS: DEEP_PURIFICATION_COMPLETE | LOGIC_UNIFIED]**

## 1. 債務清償進度 (Debt Clearance Status)
Nexus 已完成第三波深度淨化。日誌已對位，Mock 已殲滅，模組已拆解。

| 債務項目 | 狀態 | 實體核驗 (Truth) |
| :--- | :--- | :--- |
| **日誌標準化** | ✅ **已對位** | `swarm.py` 等模組已全數替換為結構化 `logging`。 |
| **移除殘留 Mock** | ✅ **已殲滅** | `brain_snapshot.py` 使用實時時間；`eternal_memory.py` 移除假錢包。 |
| **模組解耦 (Split)** | ✅ **已實作** | `context_hub.py` 已拆分出 `KnowledgeInjector` 類別。 |
| **LLM 拆解賦能** | ✅ **已接線** | `campaign_general.py` 透過 Ollama 實作真正的語言理解拆解。 |

## 2. 深度技術債 (Stage 5 Discovery)
經 2026-04-20 核心代碼深度掃描，挖掘出以下邁向 100 分終局的殘餘債務：

### 🔴 Sev-1: Cognition & Model Drift (認知與模型漂移)
- **現象**: `vector_rag.py` 仍硬編碼舊版 `all-MiniLM-L6-v2` 模型且使用 `print()`。
- **風險**: 導致檢索出的向量特徵與 MSA 採用的 `nomic-embed-text` 標準不一致，造成記憶碎片化。

### 🔴 Sev-1: Port Hardcoding (通信埠硬編碼)
- **現象**: `nexus_swarm_sse.py` 的信號中心寫死在 `8080` 埠。
- **風險**: 在 Swarm 多節點環境下將導致埠位競爭，且缺乏集中式日誌監控。

### 🟡 Sev-2: CI Gate Orchestration (門禁調度膨脹)
- **現象**: `ci_gate.py` 循序執行大量 Shell 腳本，錯誤處理在 dry-run 與實體執行間不對等。
- **風險**: CI 執行效率低，且在無頭環境 (Headless) 下難以精準定位哪一道門檻失敗。

### 🟡 Sev-2: Test Fragmentation (測試目錄碎片化)
- **現象**: 測試代碼散落在 `tests/core`, `tests/contracts` 與根目錄，缺乏統一命名空間。
- **風險**: 難以衡量真實覆蓋率，且容易遺漏特定模組的集成測試。

## 3. 下一階段清剿目標
1. **模型歸一化**: 將 `VectorRAG` 對齊至全域 Embedding 標準，並全面 Logging 化。
2. **動態配置化**: 將 SSE 與 RPC 埠位移至 `config.py`，支援環境變數注入。
3. **門禁重構**: 將 `ci_gate.py` 的 Shell 調用重構為 Python 原生 Service 調用。

---
**[NEXUS IDENTITY: 1e2904a8 + v27.6 DEBT-TRACKED | TARGET: 98+ SCORE]**

