# 🌐 System Overview & Component Maturity Map
**[PHYSICAL_STATUS: HYBRID_RETRIEVAL | MATURITY_TRACKED]**

## 1. 系統全景
Nexus 是一個「具備自我免疫與演化能力」的多 Agent 協作框架，透過物理守門員與任務契約確保穩定性。

## 📊 成熟度矩陣 (Maturity Matrix)

| Component | Maturity | Version | Status | Guardrails |
|---|---|---|---|---|
| **Nexus Engine** | 🌲 **STABLE** | v26.1 | Production | 100% CI pass, Pydantic Enforced |
| **Governance CLI**| 🌲 **STABLE** | v23.7 | Production | Enforced Briefing, No-Alias |
| **Master Loop** | 🌲 **STABLE** | v25.0 | Production | P-X-D-R-A-C Evidence enforced |
| **Drone Engine** | 🌲 **STABLE** | v1.0.x | Production | 1-bit Core + GBNF enforced |
| **MSA Routing** | 🌿 **EVOLVING** | v0.9.0 | Hardened Beta| Real LanceDB Wired |
| **Bonsai Brain** | 🌿 **EVOLVING** | v1.1.0 | Beta | Physically Wired + Health Check |

## 2. 核心術語表
- **Soul 5-Trinity**: LanceDB, Memory, MemPalace, Belief, Artifact。
- **Fail-Closed**: 分數未達標時回傳 UNKNOWN，阻斷隨意生成。
- **Drift (漂移)**: 代碼與文件間的物理或語義不一致。
- **1-bit Core**: 原子化決策單元，產出硬性判定。

## 3. 操作指引
- **STABLE**: 嚴禁破壞性修改，必須具備 ADR。
- **EVOLVING**: 允許微調，但必須保留回滾路徑。

---
**[NEXUS v28 ACTIVE | TRUTH-ALIGNED]**
