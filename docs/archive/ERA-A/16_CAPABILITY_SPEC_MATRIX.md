# 16_CAPABILITY_SPEC_MATRIX: Nexus v9 能力規格矩陣 (可執行校準版)

> [!abstract] 核心意圖
> 本文件定義了 15 項核心能力如何落地於 Nexus v9 P-D-R-A-C 架構的技術合約。所有整合點均已校準為現存的實體檔案路徑。

---

## 1. XState-Flow-Architect / FSM
- **Problem It Solves**: 解決目前任務調度邏輯散落在各處的問題，實現具備斷點續傳與備援路由的狀態機。
- **Core or Skill**: Core
- **Trigger Phase**: P (Plan / Orchestration)
- **Input Contract**: `intent_id`, `current_state`, `event_payload`
- **Output Contract**: `next_state`, `action_to_dispatch`
- **Success Criteria**: 狀態轉換 100% 準確，WarRoom 視覺化成功渲染。
- **Failure Semantics**: `STATE_LOCKED`, `INVALID_TRANSITION`; 可恢復。
- **Retry/Fallback Policy**: 退回上一級穩定狀態 (Safe-Stage)。
- **Token/Cost Impact**: 低。
- **Security/Risk Notes**: 需防止狀態爆炸與無限循環。
- **Dependency/Prerequisite**: `state_contracts.py` (現存於 `/Users/jameschen/Workspace/nexus/nexus/core/state_contracts.py`)
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/core/factory_router.py` (包含路由與隊列管理邏輯)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/core/factory_router.py`
- **Priority**: P0 (Runner 核心)
- **Confidence**: High
- **Open Questions**: Python 端是否直接嵌入 Node.js XState 實體？

## 2. RootSeeker-v3
- **Problem It Solves**: 讓診斷從「讀報錯」升級為「邊查邊想」，追蹤跨檔案調用鏈，解決修復品質不穩的痛點。
- **Core or Skill**: Skill
- **Trigger Phase**: D (Diagnose)
- **Input Contract**: `error_log`, `target_files`, `trace_depth`
- **Output Contract**: `diagnosis.json` (含 Root Cause, Evidence, Fix Plan)
- **Success Criteria**: 診斷準確率 > 90% (對比歷史 Case)。
- **Failure Semantics**: `RCA_TIMEOUT`; 需人工介入。
- **Retry/Fallback Policy**: 降級為基礎語義搜尋。
- **Token/Cost Impact**: 高 (多步推理)。
- **Security/Risk Notes**: 避免掃描敏感設定檔案。
- **Dependency/Prerequisite**: `Serena__` 語義導航工具。
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/drclaw_diagnosis.py` (現有診斷入口)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/drclaw_diagnosis.py`
- **Priority**: P0 (品質核心)
- **Confidence**: High
- **Open Questions**: 如何限制推理步數以控制成本？

## 3. Committee-Reviewer
- **Problem It Solves**: 單模型審核容易遺漏邊界條件，多模型投票可提升 Audit 階段的嚴謹度。
- **Core or Skill**: Skill
- **Trigger Phase**: A (Audit)
- **Input Contract**: `diff`, `spec`, `repair_round`
- **Output Contract**: `audit_result.json` (Votes: Correctness, Security, Perf)
- **Success Criteria**: 通過多數決決定是否進入合併。
- **Failure Semantics**: `VOTE_DEADLOCK`; 需加權裁決。
- **Retry/Fallback Policy**: 轉向 o1/o3 高推理模型。
- **Token/Cost Impact**: 極高 (3x 消耗)。
- **Security/Risk Notes**: 需確保各模型權限一致。
- **Dependency/Prerequisite**: `OpenClaw` 多模型路由。
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/final_path_audit.py` (現有審核邏輯)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/final_path_audit.py`
- **Priority**: P1 (品質優化)
- **Confidence**: High
- **Open Questions**: 如何設定模型投票權重？

## 4. Hybrid-Reranker-Pro
- **Problem It Solves**: 解決純向量搜尋在大規模教案中常抓到過時筆記的問題。
- **Core or Skill**: Skill
- **Trigger Phase**: Context Hub (X)
- **Input Contract**: `query`, `raw_chunks`
- **Output Contract**: `reranked_pack` (Top-K)
- **Success Criteria**: 檢索相關度提升 30%。
- **Failure Semantics**: `RERANK_ERROR`; Fallback 到 BM25。
- **Retry/Fallback Policy**: 使用本地 Cross-Encoder。
- **Token/Cost Impact**: 中。
- **Security/Risk Notes**: 無。
- **Dependency/Prerequisite**: `LanceDB` (現存於 `/Users/jameschen/Workspace/nexus/scripts/brain_search_v4.py`)
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/brain_search_v4.py` (核心搜尋組件)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/brain_search_v4.py`
- **Priority**: P1 (檢索優化)
- **Confidence**: High
- **Open Questions**: 離線 Rerank 能否滿足毫秒級響應？

## 5. WebApp-UAT-Playwright
- **Problem It Solves**: 驗證網頁 UI 的實際可用性，而不僅僅是代碼正確性。
- **Core or Skill**: Skill
- **Trigger Phase**: A (Audit)
- **Input Contract**: `url`, `acceptance_criteria`
- **Output Contract**: `uat_report` (含截圖與 Log)
- **Success Criteria**: E2E 腳本 100% 通過。
- **Failure Semantics**: `SELECTOR_NOT_FOUND`; 可自動修復。
- **Retry/Fallback Policy**: 自動重生成測試場景。
- **Token/Cost Impact**: 中。
- **Security/Risk Notes**: 需在沙盒環境。
- **Dependency/Prerequisite**: `Playwright`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/ui-validator.py` (UI 驗證腳本)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/ui-validator.py`
- **Priority**: P2 (擴充功能)
- **Confidence**: Medium
- **Open Questions**: 如何動態生成複雜交互腳本？

## 6. Dependency-Mapper
- **Problem It Solves**: 重構時自動產出影響範圍分析，避免誤改共用模組。
- **Core or Skill**: Core
- **Trigger Phase**: P (Plan)
- **Input Contract**: `target_file`, `scan_depth`
- **Output Contract**: `dependency_graph.json`
- **Success Criteria**: 產出完整的影響地圖。
- **Failure Semantics**: `CYCLIC_DEP_DETECTED`.
- **Retry/Fallback Policy**: 限制掃描深度。
- **Token/Cost Impact**: 低。
- **Security/Risk Notes**: 無。
- **Dependency/Prerequisite**: `link_mapper.py`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/link_mapper.py` (鏈結地圖)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/link_mapper.py`
- **Priority**: P1 (並行效率)
- **Confidence**: High
- **Open Questions**: 是否整合到 Plan 階段的 Pre-check？

## 7. Side-Effect-Scanner
- **Problem It Solves**: 監控修復後是否有性能下降或記憶體溢出等副作用。
- **Core or Skill**: Skill
- **Trigger Phase**: A (Audit)
- **Input Contract**: `patch`, `vitals_baseline`
- **Output Contract**: `side_effect_report.json`
- **Success Criteria**: 性能偏離值 < 5%。
- **Failure Semantics**: `REGRESSION_DETECTED`.
- **Retry/Fallback Policy**: 自動退回並重新 Repair。
- **Token/Cost Impact**: 中。
- **Security/Risk Notes**: 需長時間運行監控。
- **Dependency/Prerequisite**: `ci_gate.py`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/ops/ci_gate.py` (CI 驗收門檻)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/ops/ci_gate.py`
- **Priority**: P0 (Gate 核心)
- **Confidence**: High
- **Open Questions**: 如何定義各專案的性能基準線？

## 8. Token-Guardian / Context-Pruner
- **Problem It Solves**: 解決處理大量教案時的 Token 爆炸，直接降低營運成本並防止模型飄移。
- **Core or Skill**: Core
- **Trigger Phase**: 全域 / Context Hub
- **Input Contract**: `full_context`, `token_budget`
- **Output Contract**: `pruned_context` (已裁剪)
- **Success Criteria**: Token 節省 > 50% 且正確性不變。
- **Failure Semantics**: `ESSENTIAL_INFO_LOST`.
- **Retry/Fallback Policy**: 恢復原始上下文摘要。
- **Token/Cost Impact**: 中 (壓縮過程需消耗)。
- **Security/Risk Notes**: 無。
- **Dependency/Prerequisite**: `tiktoken`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/context_pruner.py` (現存裁剪腳本)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/context_pruner.py`
- **Priority**: P0 (Token 治理)
- **Confidence**: High
- **Open Questions**: 壓縮算法如何保證「尺寸數字」不被遺漏？

## 9. Multi-Strategy Repair
- **Problem It Solves**: 單一修復策略失敗後，自動嘗試不同風格（快速 vs 重構）的方案。
- **Core or Skill**: Skill
- **Trigger Phase**: R (Repair)
- **Input Contract**: `diagnosis.json`, `strategies_count`
- **Output Contract**: `repair_candidates.json`
- **Success Criteria**: 至少一個方案通過 Audit。
- **Failure Semantics**: `NO_STRATEGY_PASSED`.
- **Retry/Fallback Policy**: 嘗試策略融合。
- **Token/Cost Impact**: 高。
- **Security/Risk Notes**: 無。
- **Dependency/Prerequisite**: `safepatcher.py`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/safepatcher.py` (修復組件)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/safepatcher.py`
- **Priority**: P2 (修復擴充)
- **Confidence**: Med
- **Open Questions**: 如何過濾無效策略以節省成本？

## 10. Pattern-Extractor
- **Problem It Solves**: 自動從每日 Log 中識別規律，將教訓自動結晶為長期記憶。
- **Core or Skill**: Skill
- **Trigger Phase**: C (Crystal)
- **Input Contract**: `reflection.jsonl`, `daily_log`
- **Output Contract**: `.codex_lessons.md` 更新
- **Success Criteria**: 自動提取出高價值的代碼教訓。
- **Failure Semantics**: `NO_PATTERN_IDENTIFIED`.
- **Retry/Fallback Policy**: 累積更多樣本重跑。
- **Token/Cost Impact**: 中。
- **Security/Risk Notes**: 需去識別化。
- **Dependency/Prerequisite**: `steward.py`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/core/steward.py` (結晶管理員)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/core/steward.py`
- **Priority**: P1 (結晶優化)
- **Confidence**: High
- **Open Questions**: 如何判斷規律的「置信度」？

## 11. Log-Oracle
- **Problem It Solves**: 利用已知故障模式庫加速診斷，減少重複分析的時間。
- **Core or Skill**: Skill
- **Trigger Phase**: D (Diagnose)
- **Input Contract**: `stack_trace`, `log_snippet`
- **Output Contract**: `known_issue_match`
- **Success Criteria**: 命中時診斷時間縮短 80%。
- **Failure Semantics**: `UNKNOWN_PATTERN`.
- **Retry/Fallback Policy**: 轉向 RootSeeker 深度分析。
- **Token/Cost Impact**: 低。
- **Security/Risk Notes**: 無。
- **Dependency/Prerequisite**: `tracelog_analyzer.py`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/tracelog_analyzer.py` (日誌分析器)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/tracelog_analyzer.py`
- **Priority**: P1 (診斷加速)
- **Confidence**: Med
- **Open Questions**: 如何自動獲取新出現的故障模式？

## 12. Rule-Porter v5
- **Problem It Solves**: 實現 Antigravity 與 Cursor 規則的雙向同步，保持 Agent 行為一致。
- **Core or Skill**: Skill
- **Trigger Phase**: 全域 / Tooling
- **Input Contract**: `source_rule`, `target_format`
- **Output Contract**: `converted_rule`
- **Success Criteria**: 轉換後的規則在不同 IDE 下行為一致。
- **Failure Semantics**: `FORMAT_MISMATCH`.
- **Retry/Fallback Policy**: 退回標準 Markdown。
- **Token/Cost Impact**: 低。
- **Security/Risk Notes**: 無。
- **Dependency/Prerequisite**: `sync_docs.sh`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/ops/sync_docs.sh` (文檔同步腳本)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/ops/sync_docs.sh`
- **Priority**: P1 (治理同步)
- **Confidence**: High
- **Open Questions**: 如何映射不同工具的獨有觸發詞？

## 13. Parallel-Executor-Worktree
- **Problem It Solves**: 利用 Worktree 同時處理多個任務，大幅提升系統吞吐量。
- **Core or Skill**: Core
- **Trigger Phase**: Orchestration (P)
- **Input Contract**: `task_queue`, `concurrency`
- **Output Contract**: `multi_task_status`
- **Success Criteria**: 處理速度提升 2x。
- **Failure Semantics**: `RESOURCE_LOCK`; fallback 到序列執行。
- **Retry/Fallback Policy**: 重新排隊。
- **Token/Cost Impact**: 中。
- **Security/Risk Notes**: 需防止 Worktree 衝突。
- **Dependency/Prerequisite**: `parallel_spawner.py`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/core/parallel_spawner.py` (並行執行器)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/core/parallel_spawner.py`
- **Priority**: P1 (並行效率)
- **Confidence**: High
- **Open Questions**: 如何動態分配 GPU/Token 預算給不同進程？

## 14. Knowledge-De-Entropizer
- **Problem It Solves**: 定期清理大腦中的過時資訊，防止誤導 AI。
- **Core or Skill**: Skill
- **Trigger Phase**: C (Crystal)
- **Input Contract**: `vault_data`, `staleness_metrics`
- **Output Contract**: `cleanup_suggestions`
- **Success Criteria**: 知識庫體積減少 20% 且 Hit Rate 提升。
- **Failure Semantics**: `DELETION_BLOCKED`.
- **Retry/Fallback Policy**: 人工二審。
- **Token/Cost Impact**: 高。
- **Security/Risk Notes**: 嚴禁誤刪手寫筆記。
- **Dependency/Prerequisite**: `librarian_auditor.py`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/librarian_auditor.py` (大腦審查員)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/librarian_auditor.py`
- **Priority**: P2 (治理優化)
- **Confidence**: Med
- **Open Questions**: 如何精確定義「技術過時」？

## 15. Chaos-Agent-Tester
- **Problem It Solves**: 透過注入異常（如斷網、Token 耗盡）測試 Nexus 的魯棒性。
- **Core or Skill**: Skill
- **Trigger Phase**: A (Audit)
- **Input Contract**: `chaos_vector`, `target_process`
- **Output Contract**: `resilience_report`
- **Success Criteria**: 識別出至少 1 個隱藏的 Crash 場景。
- **Failure Semantics**: `ENV_POLLUTED`.
- **Retry/Fallback Policy**: 重置容器環境。
- **Token/Cost Impact**: 中。
- **Security/Risk Notes**: 需在完全隔離環境。
- **Dependency/Prerequisite**: `benchmark_suite.py`
- **Local Evidence**: `/Users/jameschen/Workspace/nexus/scripts/bench/benchmark_suite.py` (壓力測試組)
- **Integration Point**: `/Users/jameschen/Workspace/nexus/scripts/bench/benchmark_suite.py`
- **Priority**: P2 (擴充功能)
- **Confidence**: Med
- **Open Questions**: 混沌測試的爆炸半徑如何控制？
