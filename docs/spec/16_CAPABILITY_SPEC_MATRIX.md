# 🧬 16_CAPABILITY_SPEC_MATRIX: Nexus v9 能力規格矩陣 (可執行校準版)

## 0. 矩陣定義 (Matrix Metadata)
- **版本**: v9.0.0-Stable
- **目標**: 確保 Nexus 在自主循環中具備「自我觀測」與「精準校準」的能力，杜絕幻覺與過度執行。
- **校準入口**: `uv run scripts/engine/nexus_cli.py nexus:calibrate`

---

## 1. 核心能力矩陣 (Core Capability Matrix)

| 能力 ID | 核心指標 | 校準指令 (Calibration) | 預期證據 (Evidence) | 狀態 (Status) |
| :--- | :--- | :--- | :--- | :--- |
| **N9-REPAIR** | 自主修復誠實性 | `uv run scripts/ops/ci_gate.py` | `write_proof.json` & CI Pass | **PASSED** (Gate Hardened) |
| **N9-SWARM** | 並行隔離調度 | `nexus:runner --parallel` | `isolated_swarm/` 執行目錄 | **PASSED** (Worktree OK) |
| **N9-GUARD** | 額度與 OAuth 守衛 | `nexus:check --mock-error 429` | `quota_paused` & RCA Generated | **PASSED** (429 Intercept OK) |
| **N9-MEMORY** | 大腦同步與 Episodic | `uv run scripts/ops/memory_sync.py` | `.musestate` 增量寫入 | **PASSED** |
| **N9-HEALTH** | Phase Health 監控 | `nexus:health --report` | `docs/EXEC_LIVE_STATUS.md` 圖表 | **PASSED** |

---

## 2. 誠實驗收標準 (Acceptance Criteria)

### A. 修復誠實性 (Repair Honesty)
- [x] 執行 `N9-REPAIR` 後，若無實體代碼變更，禁止產出偽造的 `write_proof.json`。
- [x] 必須通過 `scripts/ops/ci_gate.py` 的實體查驗。

### B. 資源自覺性 (Resource Awareness)
- [x] 執行 `N9-GUARD` 偵測到 OAuth 失效或額度不足時，必須在 1 秒內暫停所有線程。
- [x] 觸發語音報警：`notify.py "額度不足"`。

### C. 並行安全 (Parallel Integrity)
- [x] 執行 `N9-SWARM` 時，禁止兩個任務同時寫入同一個檔案（需有細粒度鎖）。
- [x] Worktree 隔離必須在任務結束後自動回收。

---

## 3. 待辦事項 (Backlog)
- [ ] 實作 `nexus:calibrate` 統一調度器。
- [ ] 整合 `Codex-Review` 作為校準矩陣的二次查驗層。
