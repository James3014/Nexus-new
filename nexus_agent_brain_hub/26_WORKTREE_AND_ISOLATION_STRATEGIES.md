# 🏗️ Worktree & Isolation Strategies

## 1. 環境隔離的重要性
Nexus 的治理模式依賴於「開發」與「審計」環境的物理分離。這主要透過 Git Worktrees 與專屬沙盒目錄實現。

## 2. 隔離策略
- **`.nexus-swarm-*`**: 專為 Tactical Drone 設計的邊緣執行沙盒。具備獨立的 `.venv` 與本地 `Bonsai Brain` 介面。
- **Git Worktrees**: 用於執行 `NightShift` 長循環任務。確保實驗性的變更不會在未驗收前出現在主工作區。
- **Shadow Environment**: 在正式 Promote 前，所有的補丁存放在 `.nexus/shadow_patches/`。

## 3. 漂移解決方案 (Drift Resolution)
- **語義漂移**: 透過 `msa_lifecycle.py` 的 Hash 比對，自動將過時的 Belief 失效。
- **物理漂移**: 執行 `scripts/ops/wiki_drift_audit.py`。若偵測到代碼結構變更但 Wiki 未對應，強制阻斷提交。

## 4. 衛生規約 (Hygiene Rules)
- 嚴禁在隔離目錄外執行 `pip install`。
- 定期清理超過 24 小時的 `.nexus-swarm-*` 過期目錄，釋放磁碟空間。

---
**[Source: nexus_wiki_vault/05_Protocols/Protocol - Context Hygiene.md]**
