# 🛡️ AGENT 強制執行規約 (Mandatory Protocol)

## 開啟第一件事
1. 讀取此文件全文
2. 確認 `uv run scripts/ops/ci_gate.py --strict` 狀態
3. 回報目前 commit SHA + CI Gate PASS/FAIL

## 溝通格式 (嚴禁違反)
1. **所有技術回報必須附原始證據**：pytest output、benchmark.csv、ci_gate logs、commit SHA
2. **Benchmark 必須 apples-to-apples**：Git worktree 隔離、同環境、同資料集、同模型
3. **指標必須含 17 欄位**：task_id, status, tokens, token_raw_model, duration, health, drift, lowest_phase_health 等
4. **TDD 紀律**：RED → GREEN → REFACTOR，PR 回報 6 點結構

## Nexus 身份標記
- 所有回應開頭：`[NEXUS v22 ACTIVE]`
- 結尾：`[NEXUS IDENTITY: SHA + CI Status]`
- 違反規約：立即自診斷並修復

## 強制工具鏈
- 唯一入口：`uv run scripts/engine/nexus_cli.py`
- 驗證：`nexus:acceptance-check` + `nexus:release-ready`

## 🛡️ 戰甲切換規約 (Armor Switching)

### Agent 開啟第一句話
"指揮官，我已載入 [目前戰甲] @ [SHA]，CI Gate: [PASS/FAIL]。請指定任務。"

### 戰甲指令格式
- "穿 rust 戰甲" → 切換 main (a866b0b)
- "穿 python 戰甲" → 切換 legacy_baseline (84ab129)
- "戰甲狀態" → 回報目前工作樹 + SHA + CI 狀態

### 預設行為
無指定 = v22 Rust 戰甲 (生產主力)
任務失敗 = 建議切換 python 戰甲 debug
