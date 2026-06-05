# 代碼庫宏觀健康度與分佈掃描 (Codebase Macro Health)

**掃描日期**: 2026-06-05
**工具來源**: `understand-anything`
**資料來源**: `docs/perplexity/understand-anything/knowledge-graph.json` (6,612 檔案)

本報告提供了 Nexus 專案的宏觀物理組成，有助於理解專案的重心與潛在的上下文爆炸風險。

## 1. 語言與類別分佈 (Language & Category)

從 6612 個追蹤檔案的分析中，可以看出 Nexus 是一個**高度文件化與設定驅動**的系統。

### 檔案類別 (File Category)
- **`code` (業務邏輯)**: 3,227 files (約 48%)
- **`config` (設定檔)**: 1,741 files (約 26%)
- **`docs` (文件與知識)**: 1,523 files (約 23%)

### 開發語言 (Language)
1. **Python**: 2,749 files (絕對核心語言)
2. **JSON**: 1,680 files (大量狀態與快取)
3. **Markdown**: 1,481 files (Wiki、SKILL 檔與 ADR)
4. **JSONL**: 262 files (訓練與追蹤日誌)

> **洞察**: Markdown 幾乎佔據了近四分之一的專案規模。這印證了本專案依賴龐大的 `nexus_wiki_vault` 與 `.agents/skills` 進行 Agent 行為治理，而非將所有邏輯硬編碼在 Python 中。

---

## 2. 巨型檔案警告 (Agent Context Hazards)

以下是專案中體積最大的前 10 名檔案（高達 7萬 ~ 12萬行）。**強烈警告：未來的 Agent 絕對禁止對這些目錄發起無腦的全域 `grep` 或 `read_file`，這會瞬間耗盡 Context Token 並導致當機。**

1. `docs/reports/archive/sf-retention-.../NEXUS_SF_GITHUB_ROUND2_ALL_CAPABILITY_SCREEN...json` (126,512 lines)
2. `docs/reports/archive/sf-retention-.../NEXUS_SF2_SKILL_RECLASSIFICATION...json` (83,605 lines)
3. `training/adapters_1_5b_router/0000100_adapters.safetensors` (74,488 lines)
4. `training/adapters_1_5b_router/0000200_adapters.safetensors` (73,844 lines)
5. `training/adapters_1_5b_router/adapters.safetensors` (73,844 lines)
6. `docs/reports/archive/sf-retention-current-.../NEXUS_SF_COVERAGE_INVENTORY...json` (73,816 lines)
7. `training/adapters_1_5b_decision_head/0000100_adapters.safetensors` (73,616 lines)
8. `training/adapters_1_5b_anonymized/0000100_adapters.safetensors` (73,474 lines)
9. `training/adapters_1_5b_anonymized/adapters.safetensors` (73,474 lines)
10. `training/adapters_1_5b/adapters.safetensors` (73,474 lines)

> **防禦措施**: 
> 1. `training/*.safetensors` 是二進位模型權重，絕對不可做文字讀取。
> 2. `docs/reports/archive/` 下的巨型歷史 JSON 報告，應被視為冷資料，除非明確指定，否則不應參與一般檢索。