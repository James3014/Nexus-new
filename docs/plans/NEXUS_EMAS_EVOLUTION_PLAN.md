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

---
*Created by Antigravity - Nexus Singularity V17*
*Refined with Heterogeneous Intelligence Principles*
