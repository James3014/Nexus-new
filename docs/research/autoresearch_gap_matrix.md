# AutoResearch 三方對位真實能力矩陣
| 能力維度 | karpathy/autoresearch | ARC (Current) | DeepScientist | Nexus 控制平面目標 |
| :--- | :--- | :--- | :--- | :--- |
| **受限修改區** | ✅ 核心 (受限寫入) | ❌ 全域 (由 LLM 決定) | ❌ Quest 範圍 | ✅ 物理 Scope Lock (P2) |
| **固定評估集** | ✅ 核心 (Seed/Metric) | ❌ 隨機 (依賴 pytest) | ❌ 任務驅動 | ✅ 固定契約 Evaluator (P1) |
| **候選淘汰機制** | ✅ 候選產生與對比 | ✅ 100+ Variants | ❌ 序列探索 | ✅ Score-based 淘汰 (P1) |
| **安全回滾** | ✅ 直接覆蓋 | ❌ 無 (依賴 Git) | ✅ Git-based | ✅ 非破壞性治理回滾 (P1) |
| **人機接管** | ❌ 全自動 | ❌ 全自動 | ✅ 核心 (可接管) | ✅ 狀態機接管點 (P0) |

## 目前落地狀態（2026-04-13）
- 已完成：
  - `nexus research:run` 單一入口（P0）
  - 治理參數與拒絕原因碼（P1-A）
  - 報表 schema v1.0（P1-B）
  - PR smoke gate（P1-C）
  - Nightly gate（P1-D）
- 仍待完成：
  - 策略路由層（何時 research swarm / 何時單代理修復）
  - 以策略訊號驅動的自動模式切換（research swarm / 單代理）產品化

## Failure-to-Lesson（2026-04-13）
- Lesson RCP-001：`retain-last-n` 清理必須把「本輪新報表」納入總量計算；若先清理後寫入，會產生 off-by-one 保留錯誤。現已改為寫入後清理，且 reports 類型以「保留總量（含本輪）」執行。
- Lesson ORCH-002：Gemini CLI 在 sandbox 可能因 OAuth callback 無法 `listen` 而失敗（`EPERM 0.0.0.0`）；Tab 協同需使用可授權的非 sandbox 執行，且長任務提示應以檔案載入避免 shell quoting 斷裂。
- Lesson RCP-003：在此 repo 不應假設 `python` 可直接呼叫；腳本與驗證命令需統一使用 `uv run python ...`，避免 PATH 差異造成流程中斷。
- Lesson RCP-004：A/B benchmark 的 CLI 測試若直接依賴外部子程序與環境啟動成本，容易不穩；測試層應以 monkeypatch 固定 `subprocess.run` 與候選產生器，確保指標計算邏輯可重現。
- Lesson RCP-005：A/B manifest 若依賴 `prepare_command` 產生目標檔，CLI 必須先執行 prepare 再做 target existence 檢查，否則會誤判 `invalid_case`。
- Lesson RCP-006：Click 指令函式不可直接當一般函式呼叫（會進入 Click context 解析）；應抽出純 Python helper（impl 函式）供 CLI 與程式內重用。
- Lesson RCP-007：Auto-flow 的 baseline 短路必須「先 probe 再決策是否跑 Hyper」；若先跑 Hyper 再 probe，會讓短路失效且導致不必要耗時。
