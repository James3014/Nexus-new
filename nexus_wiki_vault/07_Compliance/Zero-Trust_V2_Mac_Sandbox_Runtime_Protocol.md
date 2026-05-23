---
aliases: '[Zero-Trust V2 Sandbox, Sandbox Protocol, V2 Sandbox]'
confidence: high
owner: agent
status: active
tags: '[compliance, security, sandbox, macos]'
title: Zero-Trust V2 macOS Sandbox Runtime Protocol
type: compliance
version_scope: '[v26.0]'
---

# Zero-Trust V2 macOS Sandbox Runtime Protocol

本合規文件物理對齊零信任 V2（Zero-Trust V2）運行期安全治理規範，詳述如何在 macOS 環境下以 `sandbox-exec` 機制對 subagent 進行強力的物理隔離，以及當門禁系統鎖死（`runtime_mutation_allowed=false`）時的標準排障指南。

---

## 🛡️ macOS `sandbox-exec` 物理隔離機制

為防止外部或第三方不安全技能在執行時篡改專案核心源碼，零信任 V2 引入了系統級的 `sandbox-exec` 沙盒限制。

### 1. 沙盒配置規則 (Sandbox Profiles)
沙盒的配置文件嚴格約束了 subagent 的系統權限：
* **唯讀白名單 (Read Allowlist)**:
  - 專案根目錄 `/Users/jameschen/workspace/nexus`
  - Python 與 Node.js 全域虛擬環境與 binaries 讀取。
* **寫入黑名單 (Write Blocklist)**:
  - **嚴格禁止** 寫入 `nexus/` 底下所有的代碼目錄。
  - **嚴格禁止** 寫入 `.git/`、`.obsidian/` 等底座狀態目錄。
* **唯一寫入允許點 (Write Exceptions)**:
  - 僅允許寫入臨時目錄 `tmp/` 與 `/Users/jameschen/workspace/nexus/nexus_wiki_vault/10_Analysis_Scans/` 產物區。

---

## 🚫 門禁鎖死與 `runtime_mutation_allowed=false` 排障

在零信任 V2 機制下，若系統檢測到任何不合規特徵，門禁系統將切換為「Fail-Closed」鎖死狀態：

> [!WARNING]
> **當 `runtime_mutation_allowed=false` 且 `automatic_apply_allowed=false` 被觸發時**：
> - 系統將被鎖定為唯讀狀態，不允許任何代碼層的 mutation 自動套用。
> - 所有新產生的 V2 candidates 將被歸入 Curation Backlog，暫不生效。

### 🛠️ 標準排障與 signed receipts 重播三步驟：

```
+------------------------------------------+
|  步驟 1: 查明缺失 - 執行 V2 behavior 檢查 |
+------------------------------------------+
                     |
                     v
+------------------------------------------+
|  步驟 2: 重播 receipts - 補齊 attested 簽章 |
+------------------------------------------+
                     |
                     v
+------------------------------------------+
|  步驟 3: 手動釋放 - 操作員核可 apply_gate  |
+------------------------------------------+
```

#### 步驟 1：檢查缺失的 behavior 證據
執行合規狀態查詢：
```bash
uv run scripts/ops/build_zero_trust_v2_rollout_status.py
```
這會輸出當前 34 個能力中哪些缺少 behavior execution signature。

#### 步驟 2：重播 attested 簽章
在確保沙盒環境安全無毒的情況下，以 sandbox attested 身分重播對應的能力，以在 `.nexus/` 目錄中重新生成 signed capability receipts：
```bash
uv run scripts/ops/build_zero_trust_v2_fresh_task_refs.py --force-sign
```

#### 步驟 3：手動釋放
當 attested receipts 生成且經過 `ci_gate.py` 檢查通過後，操作員可透過手動簽名確認，將 `runtime_mutation_allowed` 設回 `true`，釋放變更。

---

## 📊 合規稽核矩陣 (Compliance Matrix)

| 審計維度 | 合規指標 | 驗證機制 | 違規處置 |
| :--- | :--- | :--- | :--- |
| **代碼變更** | 零代碼變更 (Mutation-free) | Git status 物理比對 | 觸發 Fail-Closed 鎖死 |
| **沙盒隔離** | `sandbox-exec` 阻斷成功 | 攔截違規寫入之 OS-level exit code 偵測 | 自動回滾並計入 Curation Backlog |
| **憑證合規** | Attested receipts 完整存在 | LanceDB 憑證鏈 SHA 比對 | 鎖定變更權限為 diagnostic-only |

[NEXUS IDENTITY: de0969ff + v2.8 RUNTIME-ALIGNED]
