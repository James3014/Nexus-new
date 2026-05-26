---
name: nexus-task-launch
description: |
  Nexus 任務啟動 SOP。將「列計劃 → task → 開分支 → TDD → 階段性提交」的完整儀式封裝為可重用工作流程。
  觸發詞：「列plan、task」「用tdd方式」「開始」（在 Nexus 改動脈絡中）、「開分支處理」。
  不適用於：一次性文件修改、純閱讀研究任務。
---

# Nexus 任務啟動 SOP

## 1. Pre-flight（任務前確認）

```bash
# 確認當前主線狀態
cd /Users/jameschen/workspace/nexus
git status
git log --oneline -5
uv run scripts/nexus_cli.py nexus:health
```

必須確認：
- `git status` 工作樹乾淨（或已 stash）
- 測試基線 PASS（若有 `pytest` 快速路徑，先跑一次）

---

## 2. 建立實作計劃（implementation_plan.md）

產出內容必須包含：
- 目標描述（1句話）
- Open Questions（若有需要 User 決策的項目）
- Proposed Changes（按檔案分組）
- Verification Plan（驗收方式）

存至 Antigravity artifact 目錄（system 自動路由）。

---

## 3. 建立 task.md

格式：
```markdown
- [ ] P0: <最小可驗證步驟>
  - [ ] 子任務 A
  - [ ] 子任務 B
- [ ] P1: <下一批>
```

規則：
- 每個 P 階段獨立可提交
- 每個子任務 ≤ 3 個檔案改動

---

## 4. 開立功能分支

```bash
# 命名格式：feature/<scope>-<keyword>-<date>
git checkout -b feature/<scope>-<keyword>-$(date +%Y%m%d)
```

> [!IMPORTANT]
> 必須開分支。直接在 main 上作業將觸發 merge conflict 風險。

---

## 5. TDD 紅綠重構循環

每個子任務遵循：

```
RED   → 寫失敗測試（pytest -x 應失敗）
GREEN → 最小實作讓測試通過
REFAC → 清理，不新增行為
```

驗證命令：
```bash
uv run pytest <相關測試路徑> -x -q
```

---

## 6. 階段性提交（每個 P 階段完成後）

```bash
git add -p          # 逐 hunk 確認
git commit -m "feat(<scope>): <動詞> <主語> — P<N> <描述>"
```

Conventional Commits 格式：`feat|fix|refactor|docs|test|chore(scope): 描述`

---

## 7. 合併前驗證（交棒給 nexus-merge-gate）

完成所有 P 階段後，切換至 `nexus-merge-gate` Skill 執行合併前三連驗證。

---

## 觸發條件（Examples）

| 用戶輸入 | 對應步驟 |
|---------|---------|
| 「列plan、task改善這問題」 | → 步驟 2+3 |
| 「記得開分支處理，開始」 | → 步驟 4+5 |
| 「繼續」（在 task 進行中） | → 步驟 5，更新 task.md |
| 「同意，合併後全量測試」 | → 步驟 6+7 |

---

## 常見錯誤防範（來自 Learning Closure Matrix）

| 錯誤 | 防範規則 |
|------|---------|
| 直接在 main 改動 | 步驟 4 強制開分支 |
| 格式通關但語義未完成 | 步驟 2 要求 Verification Plan |
| 順手改到無關檔案 | 步驟 3 限制每子任務 ≤3 個檔案 |
| plan 錨點漂移導致 patch 失敗 | 修改前先 `sed -n '<range>p' docs/plans/<plan>.md` 重新定位 |
