# 🧬 Spec - Nexus L1-L7 Realization

## 1. 概述 (Overview)
本文件定義 Nexus L1~L7 核心模組的真實化 (Realization) 標準，旨在消除模板化與硬編碼邏輯，實現資料驅動的任務拆解、可攜式技能組裝與物理化驗收。

## 2. 核心變更 (Core Changes)

### 2.1 L4: 動態 DAG 拆解 (CampaignGeneral)
- **變更**: 將原本固定的 6 節點拆解邏輯改為啟發式關鍵字驅動。
- **支援關鍵字**: `refactor` (4 節點), `fix` (3 節點), `bug`, `doc`, `wiki`, `security`, `feature`, `system`。
- **Fallback**: 當無匹配關鍵字時，根據意圖長度產生 2~4 個節點。短意圖 (< 15 字) 固定為 2 節點。
- **穩定性**: 支持 `seed` 確定性輸出與基於 MD5 雜湊的變異。
- **Metadata**: 包含 `fallback_used`, `dag_score` 與 `stability_tag`。

### 2.2 L3: 可攜式技能組裝 (SkillAssembler)
- **變更**: 移除 `/Users/jameschen/` 等本機絕對路徑，改用 `project_root` 與環境變數。
- **命名**: 使用 `SHA256(intent)[:8]` 作為穩定雜湊名稱，取代不穩定的 `hash()`。
- **Metadata**: 寫入 `SKILL.md` 的 YAML 區塊，包含原始意圖、缺口原因與建立時間。

### 2.3 L2: 物理化驗收 Gate (CriteriaBuilder)
- **變更**: 實作 `execute_criteria` 邏輯，能真正呼叫測試 Artifacts。
- **報表**: 生成機器可讀的 `criteria_report.json`。
- **整合**: 驗收失敗將直接阻擋 Promote 流程。

## 3. 驗證機制 (Verification)
- **測試包**: `tests/core/test_l1_l4_realization.py`
- **Gate**: `acceptance-check` + `ci_gate`。

## 4. 未來演化 (Future Evolution)
- 對接真實的 LLM API 以替換目前的啟發式關鍵字拆解。
- 實作 L3 技能的沙盒化 JIT 驗證。
