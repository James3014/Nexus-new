# Muse-Nexus Project Index

## Purpose

這份文件索引用來把 Muse-Nexus 的現況、目標架構與重構順序收斂到同一個 repo 內，降低口頭藍圖與實際腳本之間的落差。

## Document Map

1. [01_CURRENT_STATE.md](./01_CURRENT_STATE.md)
   現有 repo 的能力、主要腳本與運作方式。

2. [02_TARGET_ARCHITECTURE.md](./02_TARGET_ARCHITECTURE.md)
   目標中的 Commander / Context Hub / P-D-X-R-A-C 架構。

3. [03_GAP_ANALYSIS.md](./03_GAP_ANALYSIS.md)
   現況與藍圖的逐項對照。

4. [04_REFACTOR_ROADMAP.md](./04_REFACTOR_ROADMAP.md)
   從現況演進到目標架構的最短務實路線。

5. [05_BACKLOG.md](./05_BACKLOG.md)
   可執行的專案管理清單，方便分階段落地。

6. [06_REPO_CLEANUP_PLAN.md](./06_REPO_CLEANUP_PLAN.md)
   repo 清理與目錄收斂策略，處理 duplicate、historical snapshot 與 generated artifacts。

7. [07_SCRIPT_OWNERSHIP_MAP.md](./07_SCRIPT_OWNERSHIP_MAP.md)
   root-level scripts 與 `scripts/core/` 的 ownership 暫行判定與 duplicate map。

8. [08_MIGRATION_RUNBOOK_V1_5_2_PLUS.md](./08_MIGRATION_RUNBOOK_V1_5_2_PLUS.md)
   從舊 Nexus 遷移到 Commander / Context Hub / Skills Router / X / Reflection 架構的升級作戰手冊。

9. [09_STATE_CONTRACT_DRAFT.md](./09_STATE_CONTRACT_DRAFT.md)
   `reflection / research_pack / skills_used / external_used / steps_history` 等新增欄位的 JSON contract 草案。

10. [10_IMPLEMENTATION_SEQUENCE.md](./10_IMPLEMENTATION_SEQUENCE.md)
    從文件進入實作時的順序表，說明哪些先做、哪些延後、哪些步驟需人工 review。

11. [11_FIRST_CUT_FILE_PLAN.md](./11_FIRST_CUT_FILE_PLAN.md)
    第一波 implementation 真正要碰的檔案、落地模組與禁止擴張的範圍。

12. [12_AGENT_EXECUTION_GUIDE.md](./12_AGENT_EXECUTION_GUIDE.md)
    交給 agent 施工時的閱讀順序、施工規則、允許/禁止範圍與回報要求。

13. [13_ACCEPTANCE_CHECKLIST.md](./13_ACCEPTANCE_CHECKLIST.md)
    驗收第一波 implementation 的 checklist，避免超範圍施工或破壞既有流程。

## Working Rule

- 先以文件澄清系統邊界與 contract，再做大規模重構。
- 優先保留既有有效能力，不先重寫成熟腳本。
- 新增能力時，優先收斂成 state contract 與 orchestration 介面。
