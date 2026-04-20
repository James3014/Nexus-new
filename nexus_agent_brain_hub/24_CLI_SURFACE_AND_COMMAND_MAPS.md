# 🖥️ CLI Surface & Command Maps

## 1. 統一入口規範
Nexus 所有的操作必須經由 `nexus_cli.py` 進行。嚴禁繞過 CLI 直接呼叫內部 Python 腳本，除非是為了開發除錯。

## 2. 核心指令集 (Nexus Commands)

| 指令 | 作用 |
|---|---|
| `nexus run` | 啟動 Supreme Master Loop (P-X-D-R-A-C)。 |
| `nexus resume` | 從物理快照點恢復任務。 |
| `nexus status` | 顯示系統健康度與信任分數。 |
| `nexus acceptance-check` | 執行任務驗收與幻覺審計。 |
| `nexus learn:ingest` | 攝取外部知識並向量化至 LanceDB。 |
| `nexus research:run` | 在沙盒中執行架構實驗。 |

## 3. 隱藏與外掛指令
- **`drone-hud`**: 實時監控 Swarm 中所有 Drone 的信念分數與進度。
- **`ui-validator`**: 自主化網頁 UI 結構驗證。
- **`stress-test`**: 系統壓力測試與併發臨界點探測。

## 4. 環境變數對位
- **`NEXUS_ENFORCED_MODE=1`**: 強制進入治理模式。
- **`NEXUS_TASK_ACCEPTANCE_MODE=task`**: 限定驗收範圍。

---
**[Source: nexus_wiki_vault/00_Home/CLI Surface Quickstart.md]**
