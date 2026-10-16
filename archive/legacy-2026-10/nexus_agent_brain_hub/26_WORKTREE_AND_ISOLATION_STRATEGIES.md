# 🏗️ Worktree & Isolation Strategies
**[PHYSICAL_STATUS: SANDBOX_ENFORCED | DRIFT_AWARE]**

## 1. 環境隔離的重要性
Nexus 的治理模式依賴於「開發」與「審計」環境的物理分離。

## ⚙️ 實體化隔離規約
- **`.nexus-swarm-*`**: 專為 Tactical Drone 設計的邊緣執行沙盒。具備獨立的 `.venv` 與本地大腦介面。
- **Git Worktrees**: 用於執行 NightShift 長循環任務，確保未驗收變更不污染主工作區。
- **Shadow Bus**: 實作於 `nexus/app/shadow_bus.py`。
    - **Fail-Closed**: 若 `.agents/scripts/sandbox_runner.sh` 缺失，任務直接失敗。
    - **非阻塞**: 透過 `concurrent.futures.ProcessPoolExecutor` 執行背景預演。

## 2. 漂移解決方案 (Drift Resolution)
- **語義漂移**: 透過 `msa_lifecycle.py` 的 Hash 比對，自動將過時的 Belief 失效。
- **物理漂移**: 執行 `scripts/ops/wiki_drift_audit.py`，阻斷未對齊的提交。

---
**[Source: New Dimension Audit Batch E - 2026-04-20]**
