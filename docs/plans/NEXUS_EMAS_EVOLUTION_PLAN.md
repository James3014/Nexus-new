# Nexus Evolutionary Multi-Axis Swarm Plan (EMAS-P) v2

## 1. 概述
本計劃定義了 Nexus 戰甲的自動化演進路徑。其核心邏輯從「單一技能替換」進化為 **「異質技能矩陣裝配 (Heterogeneous Skill Assembly)」**，透過結合不同性質的專職技能，實現超越單一模型的工程嚴謹性。

## 2. 技能裝配維度 (The Trinity Matrix)
在「複數模式」下，每項能力應由以下三種性質的技能組成：
- **Scout (斥候型)**：負責底層數據抓取、符號索引與環境感知。
- **Logic (邏輯型)**：負責核心語義推理、代碼生成與決策邏輯。
- **Audit (門衛型)**：負責邊界檢查、安全掃描與回歸風險評估。

## 3. 自動演化流程 (Evolutionary Loop)
1. **GitHub 獵頭 (Headhunt)**：自動掃描 GitHub SOTA 專案，尋找具備特定「性質」的專職 Skill。
2. **安全去毒 (Sanitize)**：針對外部 Skill 執行安全改寫，產出 `Safe-Candidate`。
3. **異質比對 (Heterogeneous Benchmark)**：
    - 測試 **「現任全才 (Incumbent Generalist)」** vs **「新異質組合 (New Heterogeneous Swarm)」**。
    - 指標：**協同係數 (Synergy Factor)** —— 組合後是否能捕捉到單一技能漏掉的邊界案例。
4. **結晶化提示 (Update Prompt)**：當異質組合展現出顯著的品質增量時，提示用戶更新「能力裝配策略」。

## 4. 推薦策略矩陣 (部分預測)
| 能力 | 推薦裝配性質 | HEEP 模式 |
| :--- | :--- | :--- |
| `artifact_gate` | Logic + Audit | Mode B (Dual Guard) |
| `codeintel` | Scout + Logic + Audit | Mode C (Neural Swarm) |
| `research` | Scout + Logic | Mode B (Dual Guard) |

## 5. 落地契約修訂 (2026-05-20)

EMAS 第一階段不自動掃 GitHub 並 promotion runtime；它只把現有 SF skill provenance 分成 repo-local/current-best 與 sanitized Safe-Candidate，供 HEEP assembly catalog 使用。

- **執行入口**：`uv run python scripts/ops/build_heep_emas_pipeline.py`
- **Safe-Candidate 產物**：`docs/reports/NEXUS_EMAS_SAFE_CANDIDATE_INTAKE_2026-05-20.json`
- **角色分類**：每個 capability 的 current primary 先按 `Scout / Logic / Audit` deterministic role heuristics 分類。
- **裝配規則**：
  - Mode A：只保留 primary skill。
  - Mode B：primary + complementary guard/auditor。
  - Mode C：Scout + Logic + Audit 三角色組裝。
- **硬邊界**：
  - Safe-Candidate 不會自動寫入 runtime default。
  - GitHub / external skill 必須先經 sanitize、receipt-backed comparison、apply gate，才可進 runtime review。
  - 本階段產物不得作為 public benchmark 或 publication-ready claim。

## 6. Heterogeneous Assembly Evaluation Contract (2026-05-20)

EMAS 的 Scout / Logic / Audit 分類只用來建立 Mode B / Mode C assembly，不是 replacement 證據。任何異質組合都必須回到 HEEP MAT-B gate，以目前 primary skill 的 Mode A 作 baseline 做 Flash+Nexus internal live compare。

### 6.1 Role Contract

- **Scout**：可提供上下文、檢索、索引、環境感知，但不得單獨作為 delivery success。
- **Logic**：可提供核心推理、實作與決策，但不得繞過 evidence gate。
- **Audit**：可提供安全、治理、回歸與污染檢查，但不得覆寫 hidden verifier 或 runtime receipt。

### 6.2 Assembly Eligibility

Mode B / Mode C 進入 compare queue 前必須同時滿足：

- skill 來源已被標為 repo-local current-best 或 sanitized Safe-Candidate。
- quarantine / candidate inbox / worktree copy / vendor-only skill 未被直接納入 runtime arm。
- 每個 arm 都可產生 runtime-final receipt chain：selected、injected、used、evidence、gate、outcome。
- assembly 沒有宣稱 public-ready；只允許 `internal_heep_mode_candidate_only`。

### 6.3 MAT-B 交接

EMAS 只負責產生候選組合與角色解釋；最終是否替代單一 primary skill 由 HEEP MAT-B 決定：

- Reliability：`success_rate`
- Quality：`pollution_pct`
- Governance：`evidence_seal_count`
- Efficiency：`token_delta`, `wall_delta`
- Regression：`reopen_rate`

若 MAT-B 缺任一 live KPI，EMAS verdict 必須停在 `PENDING_FLASH_NEXUS_LIVE_COMPARE` 或 `HOLD_MISSING_MAT_B_EVIDENCE`。

### 6.4 更新邊界

- EMAS 不直接修改 runtime default。
- EMAS 不直接觸發 public benchmark。
- EMAS 只更新 assembly catalog、compare queue、runtime apply review packet 的候選狀態。

## 7. Multi-Nature Ensemble 校準 (2026-05-20)

EMAS 的複數模式不是「三路投票」或多數決，而是 **Multi-Nature Ensemble**：用不同性質的 skill 覆蓋同一能力的不同風險面，追求互補協同，而不是堆疊同質候選。

### 7.1 三維矩陣

| 角色性質 | 負責維度 | `codeintel` 例子 |
| :--- | :--- | :--- |
| Scout | 物理掃描、數據採集 | 分析全域依賴、symbol index、impact surface。 |
| Logic | 語義推理、決策生成 | 判斷演算法邏輯、修改策略、上下文取捨。 |
| Audit | 邊界檢查、安全防禦 | 檢查 security risk、regression risk、policy boundary。 |

### 7.2 搜尋策略

外部 skill discovery 不再優先尋找「同質 replacement」，而是尋找能補齊當前 primary 缺口的專職組件：

- `codeintel`：優先找 symbol indexing、dependency impact、security-aware static scan。
- `artifact_gate` / `claim_gate`：優先找 evidence sealing、citation/claim verification、redaction/audit。
- `research_control_plane`：優先找 citation-chain、source validation、source conflict resolution。
- `ui_validator`：優先找 browser/e2e visual validator，而不是一般 frontend writer。

### 7.3 Synergy Factor 定義

`Synergy Factor` 只在異質組合解決 Mode A primary 漏掉的邊界案例時成立。範例：

- Mode A 成功交付但漏掉 security risk，Audit 補上並讓 evidence gate 改判。
- Mode A 找到局部 symbol，Scout 補出跨檔 impact surface 並降低 reopen risk。
- Mode A 做出可行答案，Logic + Audit 組合發現 hidden verifier 會拒絕的 claim gap。

因此 synergy 不是「輸出更長」、「角色更多」或「共識更高」。沒有 MAT-B live KPI 與 runtime receipt，Synergy Factor 必須停在 `PENDING_FLASH_NEXUS_LIVE_COMPARE`。

### 7.4 裝配建議語義

EMAS 的 update notification 應表達為「新增互補組件」，不是「取代 primary」：

- 正確：`發現高品質安全審計專職 skill，建議加入 artifact_gate 的 Audit slot。`
- 錯誤：`新安全 skill 比 artifact_gate primary 更好，直接取代。`

是否取代或升為 runtime mode，仍由 HEEP MAT-B gate 與 runtime apply review 決定。

---
*Created by Antigravity - Nexus Singularity V17*
*Refined with Heterogeneous Intelligence Principles*
