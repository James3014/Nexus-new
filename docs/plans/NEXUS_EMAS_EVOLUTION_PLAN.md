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

---
*Created by Antigravity - Nexus Singularity V17*
*Refined with Heterogeneous Intelligence Principles*
