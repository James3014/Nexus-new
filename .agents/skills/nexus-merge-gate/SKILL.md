---
name: nexus-merge-gate
description: |
  Nexus 合併前三連驗證 SOP。封裝「pytest 全量 → acceptance-check → contract-check → merge → push」防護梯，
  防止假綠燈（NightShift landing 假通過）。
  觸發詞：「全量測試一下nexus」「都確認沒問題就合併」「先合併再推」「有問題就可以回復」。
  不適用於：純文件修改、docs-only commit（可跳過 pytest）。
---

# Nexus 合併前三連驗證 SOP

> **核心問題**：任務級 score 通過 ≠ 全庫合約相容。  
> 來源：Learning Closure Matrix 2026-04-14「NightShift high-confidence landing」事件。

---

## Gate 0：確認分支狀態

```bash
cd /Users/jameschen/workspace/nexus
git status                        # 確認無意外改動
git log --oneline origin/main..HEAD   # 確認待合併 commits
```

若有未 commit 的改動，先處理或 stash。

---

## Gate 1：全量 pytest

```bash
uv run pytest -q --tb=short 2>&1 | tail -20
```

**阻斷條件**：任何 `FAILED` 或 `ERROR`（環境 Flaky 除外）。

Flaky 例外判定（必須明確說明理由）：
- Playwright headless Chromium ICU 損毀 → 環境問題，非代碼回歸
- Docker 未啟動導致的 Connection Error → 記錄但不阻斷

> [!CAUTION]
> 禁止「因為 Flaky 所以跳過」—— 必須明確分類 Flaky vs 代碼回歸，並回寫到 Learning Closure Matrix。

---

## Gate 2：Acceptance Check

```bash
uv run scripts/nexus_cli.py nexus:acceptance-check 2>&1 | tail -20
```

**阻斷條件**：`REJECT` 或 `BLOCK` 輸出。

若失敗：查看報告中的具體失敗原因，修復後重跑 Gate 1。

---

## Gate 3：Contract Check

```bash
uv run scripts/nexus_cli.py contract-check 2>&1 | tail -20
```

**阻斷條件**：任何 contract violation。

重點檢查：
- `OutcomePayload` schema 相容性
- `SkillFrontmatter → SkillRegistry → coordinator` 鏈
- persistence round-trip（寫入後可讀回）

---

## Gate 4：合併

```bash
git checkout main
git merge --no-ff feature/<branch-name> -m "Merge feature/<branch>: <一句話描述>"
```

使用 `--no-ff` 保留分支記錄，方便回溯。

---

## Gate 5：Push + 驗證

```bash
git push origin main
git log --oneline -5      # 確認推送成功
```

---

## Gate 6：清理

```bash
git branch -d feature/<branch-name>   # 刪除已合併的本地分支
git branch -r | grep merged           # 確認是否有未清理的遠端分支
```

---

## 快速決策矩陣

| Gate 結果 | 下一步 |
|-----------|--------|
| Gate 1 FAIL（代碼回歸） | 回到分支修復，重跑 Gate 1 |
| Gate 1 FAIL（環境 Flaky） | 記錄原因，繼續 Gate 2 |
| Gate 2 REJECT | 查閱 acceptance 報告，修復後重跑 Gate 1+2 |
| Gate 3 VIOLATION | 修復 contract，重跑 Gate 1+2+3 |
| 全部 PASS | 執行 Gate 4+5+6 |

---

## 失敗寫回規則

每次 Gate 失敗後，若發現新模式，必須更新：
```
nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md
```

格式：
```markdown
## <YYYY-MM-DD>: <錯誤類型>
- **Phenomenon**: 
- **Root Cause**: 
- **Decision**: 
- **Prevention**: 
```

---

## 常見錯誤防範（來自 Learning Closure Matrix）

| 事件 | Gate | 防範 |
|------|------|------|
| NightShift 高信心 landing 仍有 6 failures | Gate 1 | 全套測試不可跳過 |
| worktree 環境差距假陰性 | Gate 1 | 分類 Flaky vs 代碼回歸 |
| legacy alias drift 繞過驗收 | Gate 2 | 保持 CLI alias 最小化，避免 obsolete options |
| 計劃文字 vs 記憶錨點不符 | Gate 3 | 修改前先 sed 重新定位段落 |
