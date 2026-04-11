# 🧬 Nexus 結論狀態機規格 (Claim State Machine v1.0)

## 1. 🎯 核心定義
禁止 Agent 自由宣布任務完成。所有結論必須歸屬於以下法定狀態之一，並滿足對應物理門檻。

| 狀態 (State) | 硬門檻 (Hard Gating) | 降級行為 (Fallback) |
| :--- | :--- | :--- |
| `IDEA` | 僅有想法，無 code。 | 預設狀態。 |
| `HYPOTHESIS` | 列出 invariants 與潛在 root cause。 | 無 invariants 則回退 IDEA。 |
| `CANDIDATE_PATCH` | 具備實體 code diff。 | 無 diff 則禁止宣稱。 |
| `PARTIAL_VALIDATION`| 具備單一測試或模擬器成功日誌。 | 標註 [UNVERIFIED]。 |
| `VERIFIED` | 完整 Evidence Bundle + 物理對齊檢核全過。 | 自動降級至 PARTIAL。 |
| `STANDARDIZED` | 3 次獨立 Swarm 重現 + 審核簽章。 | 僅限特定模組。 |
| `REJECTED` | 被 Audit 攔截或 Invariant 破壞。 | 強制進入 Learning Loop。 |

## 2. 🚫 禁用保留字 (Restricted Claims)
嚴禁在未達 `VERIFIED` 狀態前使用下列詞彙：
- `solved`, `fixed`, `closure`, `verified`, `production-ready`, `100%`, `bit-perfect`.

**替代用語**：
- `likely`, `candidate`, `partial`, `needs repro`, `not yet aligned`.

## 3. ⚖️ 升級邏輯
- 禁止跳躍：`HYPOTHESIS` → `VERIFIED` (ILLEGAL)。
- 強制鏈路：每一級升級必須在 `auditresult.json` 中有對應證據點。

[METADATA]
Status: ACTIVE
Enforcement: CRITIQUE_ENGINE (v23.13+)
