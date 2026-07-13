---
title: Nexus v9 Capability Specification Matrix
type: capability-matrix-snapshot
status: frozen
lifecycle: historical_validation_snapshot
authority: historical_evidence
snapshot_version: v9
validation_scope: original_v9_commands_and_artifacts
current_state_source: ../nexus_wiki_vault/00_Home/CURRENT_STATE.md
authority_manifest: DOC_AUTHORITY_MANIFEST.yaml
confidence: medium
---

# 🧬 16_CAPABILITY_SPEC_MATRIX: Nexus v9 能力規格矩陣 (可執行校準版)

> [!warning] Historical capability validation snapshot
>
> Every `PASSED` value in this document is bounded to the original Nexus v9
> validation commands, artifacts, environment, and observation date.
>
> These values do not establish current runtime invocation, current route
> availability, present provider behavior, current production readiness, or
> current capability causality.
>
> `docs/EXEC_LIVE_STATUS.md` is now a frozen historical status source and
> cannot be used as present capability evidence.

## 0. 矩陣定義 (Matrix Metadata)
- **版本**: v9.0.0-Stable
- **目標**: 確保 Nexus 在自主循環中具備「自我觀測」與「精準校準」的能力，杜絕幻覺與過度執行。
- **校準入口**: `uv run scripts/engine/nexus_cli.py nexus:calibrate`

## Validation scope

The table below preserves historical v9 results. Interpret:

```text
PASSED = passed within the original documented v9 validation scope
```

Do not interpret:

```text
PASSED = currently active, currently invoked, production-ready, or verified
against the present runtime
```

Do not change individual `PASSED` cells.
Do not rerun commands.
Do not replace old commands with current guesses.

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
