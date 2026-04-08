#!/bin/zsh
set -euo pipefail

# Ensure heredoc/tempfile creation always uses writable tmp on macOS.
export TMPDIR="${TMPDIR:-/tmp}"

GEMINI_BIN="/Users/jameschen/.npm-global/bin/gemini"
NEXUS_ROOT="."
NEXUS_OBS="/Users/jameschen/Downloads/obsidian/知識庫/01_Projects/nexus"
BOOTSTRAP_FILE="$NEXUS_OBS/AGENT_BOOTSTRAP_NEXUS.md"
MODEL="${1:-gemini-3-flash-preview}"
APPROVAL_MODE="${2:-yolo}"
INDEX_FILE="$NEXUS_ROOT/docs/INDEX.md"
MODEL_STATE_DIR="$NEXUS_ROOT/.nexus"
MAIN_FLASH_COUNT_FILE="$MODEL_STATE_DIR/main_flash_count.txt"

if [[ ! -x "$GEMINI_BIN" ]]; then
  echo "Gemini binary not found: $GEMINI_BIN" >&2
  exit 1
fi

if [[ ! -f "$BOOTSTRAP_FILE" ]]; then
  echo "Bootstrap file not found: $BOOTSTRAP_FILE" >&2
  exit 1
fi

if [[ ! -f "$INDEX_FILE" ]]; then
  echo "INDEX not found: $INDEX_FILE" >&2
  exit 1
fi

mkdir -p "$MODEL_STATE_DIR"

# Main-agent model policy:
# - First 3 launches with flash are allowed.
# - Starting from the 4th launch, auto-switch to pro.
if [[ "$MODEL" == "gemini-3-flash-preview" ]]; then
  FLASH_COUNT=0
  if [[ -f "$MAIN_FLASH_COUNT_FILE" ]]; then
    FLASH_COUNT="$(cat "$MAIN_FLASH_COUNT_FILE" 2>/dev/null || echo 0)"
  fi
  if ! [[ "$FLASH_COUNT" =~ ^[0-9]+$ ]]; then
    FLASH_COUNT=0
  fi

  if (( FLASH_COUNT >= 3 )); then
    MODEL="gemini-3.1-pro-preview"
    echo "[nexus-launch] main-agent auto switch: flash -> pro (flash_count=$FLASH_COUNT)"
  else
    FLASH_COUNT=$((FLASH_COUNT + 1))
    echo "$FLASH_COUNT" > "$MAIN_FLASH_COUNT_FILE"
    echo "[nexus-launch] main-agent model=gemini-3-flash-preview (flash_count=$FLASH_COUNT/3)"
  fi
elif [[ "$MODEL" == "gemini-3.1-pro-preview" ]]; then
  echo "[nexus-launch] main-agent model=gemini-3.1-pro-preview (manual)"
fi

EXTRA_PROMPT='---
從現在起改成「一次授權、全程連跑」模式，立即執行：
1. 你是單一指揮官；開 4 個分身，各自在獨立 git worktree，宣告檔案 ownership，不可重疊。
2. 全部分身強制 Nexus 模式，只允許入口：
   uv run scripts/engine/nexus_cli.py nexus:runner
3. 執行策略改為批次，不要碎步命令；任務順序只看 task_manifest.yaml 的 depends_on。
4. 將常用命令加入本輪白名單/免確認策略（uv run、pytest、git worktree、nexus runner），避免反覆彈窗。
5. 除非 destructive / credential / spec_conflict，否則不得停下詢問我。
6. 每輪整合後跑 gate（ci / benchmark / docs sync），最後回報格式固定：
   SUMMARY / METRICS / GATE / EVIDENCE_PATHS / NEXT
7. 開工前先讀：
   __INDEX_FILE__
8. 只以 INDEX 的 Current / In Progress / Next 作為當輪主規格；聊天內容僅作補充。
9. 若 INDEX 與其他文件衝突，以 INDEX 為準，並在本輪最後同步回寫相關文件。
10. 先執行 INDEX 的 Next 第 1 項，再依序 2 -> 3 -> 4；不得跳號。
11. 若 INDEX 已標示「raw token 已打通」，禁止回報 Audit-Estimate 現況，除非你有新證據顯示 raw 回到 0。
12. 未經使用者明確指示，禁止修改：
    - `task_manifest.yaml`
    - `task_manifest.longrun.yaml`
    - `scripts/start_nexus_gemini.sh`
    - `scripts/start_nexus_antigravity.sh`
13. 禁止透過 `read_file` 讀取 `.nexus/task_status.json`（該路徑可能被 ignore policy 阻擋）；狀態追蹤改讀：
    - `docs/EXEC_LIVE_STATUS.md`
    - `ci_benchmark.csv`
    - `docs/EXEC_REPORT_*.md`

分身模型策略（強制）：
1. 所有分身預設使用 gemini-3-flash-preview。
2. 若出現配額/速率限制/品質不足，該分身必須立即切換 gemini-3.1-pro-preview 後重試，不可等待人工確認。
2.1 每個分身在本輪最多使用 flash 3 次；第 4 次起必須改用 gemini-3.1-pro-preview。
2.2 若 60 秒內出現 2 次以上 `exhausted your capacity on this model`：
    - 立刻停止新分身派工
    - 併發降到 1（只留 orchestrator）
    - 剩餘任務全部改由 gemini-3.1-pro-preview 單線執行
2.3 若已觸發 2.2，至少連續完成 3 個 task 後，才可恢復並行。
3. 每個分身啟動時先回報：
   worker-id | model=...
4. 每次模型切換必須回報：
   worker-id | switch: flash -> pro | reason=...
5. 最終報告必附 MODEL_USAGE 區塊，列出每個分身實際使用模型與切換次數。
6. 若你無法直接控制分身模型，必須在派工指令中明確帶入模型參數；未帶參數視為派工失敗並重派。
7. 所有分身必須顯式帶入 `GEMINI_SANDBOX=true`；未帶沙盒參數視為派工失敗並重派。
8. 分身派工前必須先做模型自檢；若任何分身不是 `gemini-3-flash-preview` 或 `gemini-3.1-pro-preview`，該輪派工直接判定失敗並全部重派。
9. 禁止使用 `gemini-2.0-*` 系列做分身；發現即刻中止該分身並重派。
10. 分身啟動第一批回報必須包含：
    - worker-id | model=...
    - worker-id | ownership=<file list>
    且 4 位 worker 的 ownership 不可重疊。
11. 若容量告警持續（重試退避超過 30 秒），禁止維持 4-worker 並行；必須降級為單線直到告警解除。

回報節奏（強制）：
1. 每完成一個 task 立刻回報一行：
   [time] task-id | done | gate=<pass/fail> | evidence=<path>
2. 回報後不等待使用者，立刻繼續下一個 depends_on 任務。
3. 全部完成後輸出：
   SUMMARY / METRICS / GATE / EVIDENCE_PATHS / NEXT / MODEL_USAGE
4. 輸出 `SUMMARY...NEXT` 後不得停止；必須立即執行 `NEXT` 的第 1 項，並持續循環直到：
   - 任務全部完成，或
   - 觸發 destructive / credential / spec_conflict，或
   - token/配額耗盡（此時只允許輸出 checkpoint 後結束）。
5. 若僅輸出報告未繼續執行，視為失敗；必須自動恢復並從 `NEXT` 第 1 項重啟。
6. 即使任務執行中，也必須每 30 秒輸出一行心跳：
   [time] worker-id | task-id | running | blocker=<none|...>
7. 每輪里程碑回報必須落地文件到：
   ./docs/EXEC_REPORT_<YYYYMMDD_HHMMSS>.md
   內容固定：
   SUMMARY / METRICS / GATE / EVIDENCE_PATHS / NEXT / MODEL_USAGE
8. 完成回報後，必須把最新報告檔路徑再回貼一行：
   REPORT_FILE: ./docs/EXEC_REPORT_<...>.md
9. 禁止「只回報不落檔」：在回貼 REPORT_FILE 前，必須先執行檔案存在檢查（file_exists=true）並回貼。
10. 若 REPORT_FILE 不存在，該輪回報視為無效，必須立即補寫檔案再重送回報。
11. 若 `nexus:runner` 結束且仍有 token/配額，不得閒置；必須立刻：
    - 重新讀 INDEX 的 Next，執行下一項；或
    - 若 Next 已清空，執行基線循環：gate.ci -> bench.replay -> docs.index.sync
      並持續每 30 秒心跳，直到 token/配額耗盡或觸發中止條件。'

EXTRA_PROMPT="${EXTRA_PROMPT/__INDEX_FILE__/$INDEX_FILE}"
PROMPT="$(cat "$BOOTSTRAP_FILE")"$'\n\n'"$EXTRA_PROMPT"
RUN_MESSAGE="${RUN_MESSAGE:-請你現在立刻開始執行：先讀 INDEX，再依 task_manifest.yaml 的 depends_on 連續執行，不要停在待命提示。完成一輪後輸出 SUMMARY / METRICS / GATE / EVIDENCE_PATHS / NEXT，然後繼續 NEXT 第 1 項。}"
FINAL_PROMPT="${PROMPT}"$'\n\n'"${RUN_MESSAGE}"

cd "$NEXUS_ROOT"
export GEMINI_SANDBOX=true
exec "$GEMINI_BIN" \
  -m "$MODEL" \
  --approval-mode "$APPROVAL_MODE" \
  --include-directories "$NEXUS_ROOT,$NEXUS_OBS" \
  -p "$FINAL_PROMPT"
