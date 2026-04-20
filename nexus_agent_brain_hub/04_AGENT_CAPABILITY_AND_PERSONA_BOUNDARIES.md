# 🤖 Agent Capability & Persona Boundaries

## 🛡️ 戰略邊界規約
本文件定義 Nexus Swarm 中各 Persona 的權責邊界，防止多 Agent 同時修改同一模組導致的治理死鎖。

## 👥 Persona 分工地圖

| Agent | 核心職能 | 專屬工具 | 禁止行為 (Forbidden) |
|---|---|---|---|
| **Antigravity** | **治理與守門** | `ci_gate`, `contract-check` | 嚴禁在未通過 P0 門禁前強制 Promote。 |
| **Gemini-Nexus**| **開發與實驗** | `research:run`, `msa_routing` | 嚴禁修改核心模組時不附帶測試證據。 |
| **Codex** | **精煉與挑戰** | `codex challenge`, `distill` | 嚴禁直接執行檔案寫入，僅限唯讀與審核。 |

## 🚧 物理路徑限制

- **Allowed Paths**: `scripts/ops/`, `nexus_wiki_vault/`, `docs/`, `nexus/experiments/`。
- **Forbidden Paths**: `.obsidian/`, `logs/`, `packages/`, `nexus_swarm/`。
- **修改限制**: 單次任務建議修改不超過 **10 個檔案** (Soft Limit)，絕對不超過 **25 個** (Hard Gate)。

## 🤝 衝突解決協議
1. **優先級**: 治理命令 (Antigravity) > 開發指令 (Gemini)。
2. **鎖定機制**: 當偵測到 `Code 16` 錯誤時，必須立即停止所有修改，進入 `Physical Audit` 模式。
3. **證據連鎖**: 上游 Agent 產出的 Artifact 必須被下游 Agent 顯式引用。

---
**[Source: nexus_wiki_vault/06_Ops/Ops - Agent Capability Boundaries.md]**
