# Nexus Work OS / CodeIntel Roadmap

日期：2026-04-28

## 目標

把 Nexus 已有的治理、證據、RLM、benchmark 能力，收斂成可產品化的 Work OS 與原生 CodeIntel 主路徑。外部 GitNexus / SocratiCode 只作能力對標，不引入外部 runtime、daemon、DB 或套件。

## P28: RLM 內化狀態

What:
- RLM trace / budget contract、RecursiveRepairLoop、RLM benchmark trace evidence 已存在。
- 本輪不重做，避免把已完成能力當新功能重寫。

Why:
- Nexus 的 RLM 價值在於「治理內迴圈」，不是自由 agent。
- 已有 trace/budget/submission semantics 後，下一步應接 rule lifecycle 與 Work OS gate。

How:
- 保留 feature flag 行為。
- 後續只補 per-iteration MemPalace / Belief / CapabilityGate policy 與 harder benchmark。

## P29: 自我更新 Rule Lifecycle

What:
- 新增 rule lifecycle contract：`active | light | deprecated | removed_candidate`。
- 用 verified lift、trust mismatch、cost delta、sample size 決定規則是否保留或降摩擦。

Why:
- Nexus 不能變成靜態規則堆疊。模型變強時，低收益高成本規則應降級；仍能降低幻覺/風險的規則要保留。

How:
- `RuleLifecycleEvidence` 記錄每條治理規則的 benchmark 證據。
- `recommend_rule_state()` 先用保守、可解釋規則，不急著 ML。

## P30: Work OS Contract 最小落地

What:
- Task contract 補 `consulted_agents <= 2`、`delivery_profile`、`requires_proposal/proposal_ref`。
- live delivery profile 需要 human-approval evidence。
- code-change path 開始有 `code-impact` evidence kind / requirement。

Why:
- 這把文件中的 Work OS 規則變成程式級 fail-closed contract：單一 owner、最多兩位 consulted、live/mock 不可混淆、跨邊界任務要 proposal。

How:
- 先在 orchestrator task layer 落地，不改 CLI 與 delivery runtime。
- 下一刀接到 `nexus/delivery/models.py`、`nexus/delivery/gate.py`、`scripts/ops/closeout_guard.py`，讓 closeout 與 completion gate 也使用同一份 contract。

Status:
- 2026-04-28 P30a implemented in orchestrator task contract.
- 2026-04-28 P30b implemented in delivery completion gate, task runner pass-through, and closeout guard.

Lesson:
- `delivery_profile=live_*` is an extra governance requirement, not a shortcut around existing task-level verification floors. Live delivery must satisfy both the normal command/artifact contract and live evidence / human approval policy.

## P31: Native CodeIntel Convergence

What:
- 新增 Nexus 原生 code intelligence 主路徑：
  - `nexus code:scan`
  - `nexus code:impact --files ...`
  - `nexus code:context --symbol ...`
- 新增內建 service：
  - `nexus/services/codeintel/models.py`
  - `graph_builder.py`
  - `impact_service.py`
  - `context_service.py`

Why:
- Nexus 強在治理與 evidence，但 code-intel 目前仍是分散原型。要做到「放心交付」，code-change 任務必須先有 impact/context 證據。

How:
- 借鏡 GitNexus 的 graph-first / impact / symbol context 設計。
- 借鏡 SocratiCode 的 CLI/status/UX 產品化模式。
- 不引入外部專案，不接外部服務；只把 repo 內既有原型收斂成內建 service。

## P32: CodeIntel Gate / Multi-Agent 接線

What:
- code-change 任務缺 `code-impact` evidence 時 gate fail-closed。
- owner 仍唯一；codeintel analyst 與 guardrail reviewer 只能作 consulted evidence producer / reviewer。

Why:
- CodeIntel 不只是查詢工具，而是 A/C gate 的前置證據。這能降低 blind patch、漏測與跨模組回歸。

How:
- 擴充 task/evidence policy。
- 接 `delivery-gate` 與 closeout guard。
- 加 e2e：`code:scan -> code:impact -> patch evidence -> delivery gate`。

## Lesson

- 跨 worktree 文件可能存在於 `/Users/jameschen/Workspace/nexus`，但主工作區是 `/Users/jameschen/.codex/worktrees/ad59/nexus`。執行前要用絕對路徑確認，避免把另一份工作區的計劃誤判為本 worktree 已落地。
- P28 已有比原計劃更多的實作；後續應先查現況再開發，避免重複建置。
