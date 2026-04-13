# AutoResearch 控制平面規格 (v1.0)
## 1. 物理範圍契約 (Modifiable Scope)
- **定義**: 每次實驗前必須宣告 `modifiable_scope` (List of Paths)。
- **硬化**: `ExperimentScheduler` 將在檔案寫入前執行路徑校核，超出範圍則阻斷。
## 2. 評估執行契約 (Eval Contract)
- **Seed 鎖定**: 強制使用 `FIXED_SEEDS = [42, 1337, 2026]` 進行多輪驗收。
- **Budget 鎖定**: 單次實驗總成本 (LLM Tokens/Time) 不得超過 `budget_limit`。
## 3. 候選生命週期 (Candidate Lifecycle)
- **狀態**: `created` -> `running` -> `evaluated` -> `promoted/rejected`。
- **淘汰**: 低於基線評分或觸發 Regression 者自動進入 Rejected 狀態。
## 4. 人機接管 (Human Takeover)
- **中斷點**: 實驗停滯或指標異常偏移。
- **Quest Repo**: 每次實驗自動建立 `.nexus/experiments/[ID]` 作為 Quest 工作目錄，包含 diff 與 log。
