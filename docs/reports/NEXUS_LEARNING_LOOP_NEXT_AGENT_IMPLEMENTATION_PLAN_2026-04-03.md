# Nexus Learning Loop Next-Agent Implementation Plan

Date: 2026-04-03
Audience: 下一位負責實作深化的 agent
Repo: `.`

## 1. 任務定位

你不是要重做 learning loop。

基礎閉環已存在，且已提交：

- `2d054a6`
- `f65931e`
- `c9e813e`

你的工作是把它從「工程可用」升級為「治理成熟」。

## 2. 先讀哪些檔

先讀：

- [NEXUS_LEARNING_LOOP_CLOSED_LOOP_REPORT_2026-04-03.md](./docs/reports/NEXUS_LEARNING_LOOP_CLOSED_LOOP_REPORT_2026-04-03.md)
- [continuous_learning.py](./nexus/services/continuous_learning.py)
- [pipeline_crystal.py](./nexus/engine/pipeline_crystal.py)
- [coordinator.py](./nexus/engine/coordinator.py)
- [nexus_cli.py](./scripts/engine/nexus_cli.py)
- [test_continuous_learning.py](./tests/services/test_continuous_learning.py)
- [test_cli_commands.py](./tests/test_cli_commands.py)
- [test_coordinator.py](./tests/engine/test_coordinator.py)

必要時再讀：

- [steward.py](./scripts/steward.py)
- [INDEX.md](./docs/INDEX.md)
- [MUSE_ENGINE_SPEC_V17.1_HARDENED.md](./MUSE_ENGINE_SPEC_V17.1_HARDENED.md)

## 3. 現況邊界

### 已完成

- protocol startup gate
- strict/dry-run CI 對齊
- lesson crystallization
- writeback todo
- delta artifact generation
- pending delivery status
- startup refresh auto-apply
- fully_delivered promotion
- optional dependency fallback
- current focused tests passing

### 未完成

- semantic doc patching
- writeback governance acceptance
- lesson structure hardening
- planner/repair feedback loop strengthening
- multi-task concurrent writeback isolation

## 4. 你的主要目標

下一位 agent 應做的是 P1 深化，而不是 P0 修復。

### P1-A: 把 auto-apply 從附加式升級成段落級語義編修

現況問題：
- `continuous_learning.py` 目前只是把 delta block 附加到文件末尾

你要做：
- 找出 `INDEX.md` / `SPEC` 的穩定 anchor
- 讓 auto-apply 針對 anchor 區塊更新，而不是一直 append

理想方案：
- 設計 anchor marker，例如：
  - `<!-- nexus-anchor:learning-loop -->`
  - `<!-- nexus-anchor:governance-hardening -->`
- `*_INDEX.delta.md` / `*_SPEC.delta.md` 不只存整段 markdown，而是存：
  - target anchor
  - replace mode
  - generated content

建議修改：
- [continuous_learning.py](./nexus/services/continuous_learning.py)
- 新增純函式 helper，例如 `apply_structured_writeback_delta(...)`
- 視需要新增 `nexus/services/writeback_renderer.py`

測試要求：
- 新增段落不存在時，能安全 append 到 fallback section
- anchor 存在時，能替換指定段落
- 重跑 refresh 不會重複插入

### P1-B: 在 `fully_delivered` 前加入 writeback governance check

現況問題：
- 現在只要 delta 套進文件就會升級成 `fully_delivered`

你要做：
- 在升級前做輕量治理檢查

最小可行 gating：
- `INDEX.md` 與 `SPEC` 的 writeback block 都存在
- 對應 `task_id` 一致
- todo items 全 completed
- delta artifact 與已套用內容 hash 一致

建議新增：
- `validate_writeback_completion(...)`
- `writeback_validation.json`
- `writeback_validation.jsonl`

檔案：
- [continuous_learning.py](./nexus/services/continuous_learning.py)
- tests: [test_continuous_learning.py](./tests/services/test_continuous_learning.py)

### P1-C: 強化 lesson schema

現況問題：
- lesson 太扁平

你要做：
- 讓 crystallized lesson 有更強的結構

至少新增欄位：
- `task_id`
- `category`
- `root_cause`
- `evidence`
- `corrective_action`
- `reusable_when`
- `do_not_apply_when`
- `source_phase`

注意：
- `.codex_lessons.md` 可以維持 human-readable
- 但應同時落一份結構化 JSONL，例如：
  - `.nexus/knowledge/lesson_events.jsonl`

建議修改：
- [steward.py](./scripts/steward.py)
- [continuous_learning.py](./nexus/services/continuous_learning.py)

### P1-D: 把 lessons 反向餵回 planner / repair

現況問題：
- 有寫 lesson，但對下一輪決策的直接影響不夠強

你要做：
- 在 planner / repair 前加入近期 lesson retrieval
- 如果 task 與既有 root cause 類型相近：
  - 提高對同類 phantom pattern 的警戒
  - 預先把 correct practice 注入 context

優先入口：
- [pipeline.py](./nexus/engine/pipeline.py)
- [pipeline_stages.py](./nexus/engine/pipeline_stages.py)
- [pipeline_repair.py](./nexus/engine/pipeline_repair.py)
- 若有需要再接：
  - [coordinator.py](./nexus/engine/coordinator.py)

最小可行版本：
- 根據 task description 與 root cause 做 keyword / tag match
- 找出最近 N 條高關聯 lesson
- 注入 `state.metadata["retrieved_lessons"]`

## 5. 不要做的事

- 不要回退這三個 commit
- 不要把 `.codex_lessons.md` 當成主 schema 唯一來源
- 不要直接大改 `nexus-desk`
- 不要把 `legacy_baseline` 拉進這次工作，除非你真的動到共享契約
- 不要用 destructive git 操作清理工作樹
- 不要把其他已 dirty 的檔案混進你的 commit

## 6. 建議工作順序

### Step 1
先做 writeback semantic patching。

原因：
- 這是目前最大的真值風險
- 也是後續 governance check 的前提

### Step 2
做 writeback validation gate。

原因：
- 這會讓 `fully_delivered` 更可信

### Step 3
做 structured lesson schema。

原因：
- 這是讓學習真正可被 reuse 的基礎

### Step 4
把 lessons 餵回 planner / repair。

原因：
- 這才是讓系統「學完變強」的核心

## 7. 每一步都要補哪些測試

### 針對 semantic patching

新增測試：
- anchor 替換成功
- anchor 缺失 fallback append
- 重複 refresh 不會 duplicate block

### 針對 validation gate

新增測試：
- delta applied 但 hash mismatch 時不可 fully_delivered
- 任一目標未完成時保持 pending
- validation pass 才可 fully_delivered

### 針對 lesson schema

新增測試：
- lesson JSONL 結構完整
- `.codex_lessons.md` 與 JSONL 同步
- 重複 root cause 不會無限膨脹

### 針對 planner feedback

新增測試：
- 相似 task 會檢索到 lesson
- `retrieved_lessons` 會進 state metadata
- phantom / rejection 類型能提升 planner guard

## 8. 驗證命令基線

至少重跑：

- `pytest -q tests/services/test_continuous_learning.py tests/test_cli_commands.py tests/engine/test_coordinator.py`
- `uv run scripts/engine/nexus_cli.py nexus:status --aos`

若你擴大影響 pipeline：

- 補跑與 pipeline / repair 有關的 focused tests

## 9. 交付標準

你完成後，至少要滿足：

1. 任務 finalize 後仍會先停在 pending
2. refresh 會自動完成 writeback
3. `fully_delivered` 必須依賴 validation pass
4. lesson 不只寫 markdown，也有結構化儲存
5. retrieved lesson 能在下一輪任務被看到

## 10. 最後的判斷原則

本系統下一階段的核心不是「多寫一些 log」。

真正的成功條件是：

- 文件真值更準
- 完成判定更嚴格
- lesson 更可重用
- 下一輪決策更少重蹈覆轍

如果你的改動沒有同時提升這四件事，那就還不算真正推進 learning loop。
