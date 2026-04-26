# 🤖 Agent Capability & Persona Boundaries
**[PHYSICAL_STATUS: TENANT_ISOLATED | RBAC_ENFORCED]**

## 🛡️ 戰略邊界規約
定義 Nexus Swarm 中各 Persona 的權責邊界，防止治理死鎖。

## 👥 Persona 分工地圖

| Agent | 核心職能 | 專屬工具 | 禁止行為 (Forbidden) |
|---|---|---|---|
| **Antigravity** | **治理與守門** | `ci_gate`, `contract-check` | 嚴禁在未通過 P0 前強制 Promote。 |
| **Gemini-Nexus**| **開發與實驗** | `research:run`, `msa_routing` | 嚴禁修改核心不附帶測試證據。 |
| **Codex** | **精煉與挑戰** | `codex challenge`, `distill` | 嚴禁執行寫入，僅限唯讀與審核。 |

## 🚧 物理與租戶隔離
- **Allowed Paths**: `scripts/ops/`, `nexus_wiki_vault/`, `docs/`, `nexus/experiments/`。
- **Forbidden Paths**: `.obsidian/`, `logs/`, `packages/`。
- **Tenant ID**: 記憶檢索強制過濾 `tenant_id` 與 `drawer_id`，確保租戶數據隔離。
- **Node ID**: 透過 `NEXUS_NODE_ID` 標識物理計算單元，支援 mTLS 身分驗證。

## 🤝 衝突解決協議
- **優先級**: 治理命令 (Antigravity) > 開發指令 (Gemini)。
- **鎖定**: 偵測到 `Code 16` 時立即停止，進入 `Physical Audit`。

---
**[Source: nexus_wiki_vault/06_Ops/Ops - Agent Capability Boundaries.md]**
