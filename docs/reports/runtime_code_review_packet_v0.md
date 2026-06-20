# Runtime Code Review Packet v0 任務報告

## 1. 執行摘要 (Executive Summary)
本報告為 `runtime_code_review_packet_v0`，對當前工作樹內 17 個已修改的追蹤原始碼 (runtime_code_candidate) 檔案進行了唯讀審查與工程分組 (Review-only Audit)。
* **唯讀審查**：本任務為純審核性質，**無執行任何 staging、commit、刪除或還原操作**。
* **嚴禁批量提交**：本審查秉持「最小相干原則」，強烈建議**禁止批量提交全部代碼**，並推薦對極窄、獨立且風險較低的分組進行逐步提交處置。

## 2. 來源審查與背景 (Source Review)
在 `restore_generated_modified_files_only_v0` 提交完成後（Commit: `671d8969`），30 個 `.pyc` 快取修改已被成功清除，目前僅餘下 33 個修改檔案（包括 17 個 runtime_code_candidate，.tmp_build 為預期的 submodule dirty 狀態，其餘為測試或 scratch 變動）。工作樹目前狀態清晰，有利於進行代碼細部分類與風險審查。

## 3. 工程分組盤點 (Engineering Packet Grouping)
17 個原始碼檔案被精確拆分為以下五大工程模組：

### 3.1 `local_heal_hardening_packet` (10 個)
* **包含路徑**：
  - `nexus/services/local_heal/context.py`
  - `nexus/services/local_heal/context_budget.py`
  - `nexus/services/local_heal/evidence_compactor.py`
  - `nexus/services/local_heal/interface.py`
  - `nexus/services/local_heal/localizer.py`
  - `nexus/services/local_heal/phases/planning.py`
  - `nexus/services/local_heal/phases/reproduction.py`
  - `nexus/services/local_heal/protocol.py`
  - `nexus/services/local_heal/repomap.py`
  - `nexus/services/local_heal/reproduction.py`
* **風險與影響**：**高 (HIGH)**。此為修復核心模組，改動深度大，任何缺陷都將引發假綠燈或修復流程中斷。

### 3.2 `codeintel_or_pipeline_packet` (4 個)
* **包含路徑**：
  - `nexus-core-rs/src/main.rs`
  - `nexus/core/pipeline_metadata.py`
  - `nexus/delivery/models.py`
  - `nexus/services/codeintel/graph_builder.py`
* **風險與影響**：**高 (HIGH)**。涉及 Rust 解析器、pipeline metadata 與代碼圖生成，影響代碼索引與成功歸因。

### 3.3 `local_model_policy_packet` (1 個)
* **包含路徑**：`nexus/engine/local_model_policy.py`
* **風險與影響**：**中 (MEDIUM)**。主要為 LLM 響應限制與 policy 配置，影響模型呼叫策略。

### 3.4 `s2t_export_guard_packet` (1 個)
* **包含路徑**：`nexus/evidence/s2t_export_guard.py`
* **風險與影響**：**中 (MEDIUM)**。為 s2t 導出套件的校驗邊界邏輯。

### 3.5 `strategy_or_strata_packet` (1 個)
* **包含路徑**：`nexus/strategy/strategy_envelope.py`
* **風險與影響**：**中 (MEDIUM)**。為 strategy envelope 的 adherence logic。

## 4. 提交就緒度與決策推薦 (Commit Readiness)
* **決策判定**：`READY_FOR_TARGETED_PACKET` (窄分組就緒)。
* **可立即提交的窄分組**：
  - `local_model_policy_packet`（修改窄且功能獨立）
  - `s2t_export_guard_packet`
* **受阻與去重分組**：`local_heal_hardening_packet`、`codeintel_or_pipeline_packet`。
* **強烈禁止**：`forbidden_bulk_commit: true`。禁止批量一次性提交。建議下個任務針對極窄的 `local_model_policy_packet` 進行獨立 review 與 commit 處置。

## 5. 治理與安全合規聲明
* 本任務完全在 `AUDIT_ONLY` 模式下執行。無任何 git add/commit 變更，無 model calls，無 verifier 執行。
