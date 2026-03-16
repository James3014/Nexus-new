# MG / Nexus / Agent Debug Protocol (Steel Version)

## 目標
在 Nexus v9 Steel 架構下進行 debug 或修復時，強制 agent 先進行「失敗層識別」，避免跨層修改造成系統污染。

在進行任何修改前，必須先完成以下分析。

---

## Step 1 — Identify Failure Layer

分析錯誤並判定層級：

### Possible Layers:
- **EXECUTOR_LAYER**
- **ESCALATION_LAYER**
- **PATCHER_LAYER**
- **CORE_DECISION_LAYER**
- **BENCHMARK_DISCIPLINE**

**FAILURE_LAYER:** [Identify Layer]

---

## Step 2 — Map Allowed Files

根據 Failure Layer，只允許修改以下檔案。

### EXECUTOR_LAYER
- **Allowed:** `nexus/executors/*.py`
- **Forbidden:** `scripts/codex_loop_brain.py`, `nexus/escalation/`, `nexus/patcher/`

### ESCALATION_LAYER
- **Allowed:** `nexus/escalation/*.py`, `scripts/codex_loop_brain.py`
- **Forbidden:** `nexus/executors/`

### PATCHER_LAYER
- **Allowed:** `nexus/patcher/*.py`
- **Forbidden:** `executor`, `core orchestration`

### CORE_DECISION_LAYER
- **Allowed:** `scripts/codex_loop_brain.py`
- **Forbidden:** `executors`, `patcher`

### BENCHMARK_DISCIPLINE
- **Allowed:** `nexus_benchmark.sh`
- **Forbidden:** `core logic`

---

## Step 3 — Architecture Boundary Check
**WILL_THIS_FIX_TOUCH_FORBIDDEN_FILES:** YES / NO

> [!CAUTION]
> 若為 **YES**，立即停止！此為系統架構違規 (Architecture violation)。

---

## Step 4 — Fix Plan
- **FILES_TO_MODIFY:** [file list]
- **FIX_DESCRIPTION:** [what will be changed]
- **EXPECTED_BEHAVIOR:** [what behavior will change]

---

## Step 5 — Validation Plan
1. [Step 1]
2. [Step 2]
3. [Step 3]

---

## Step 6 — Post-Fix Verification
修復完成後必須執行：
`./nexus_benchmark.sh --self-test`

確認以下 PASS：
- [x] Executor Dry Run
- [x] Continuity Test
- [x] Reviewer Gate
- [x] Contamination Trap
- [x] Executor Swap

---

## Step 7 — Trial Safety Rule
如果當前為 **Protected Trial**：
- **禁止:** 修改核心檔案。
- **僅允許:** diagnostic report。
