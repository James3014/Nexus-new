---
ci_hash: pend-audit
created: 2026-04-07 05:59:01+00:00
governance: Trident 3.0
id: nexus-nexus-pilot-cli-[[quickstart|quickstart]]-cn
landscape: structural
owner: Nexus Core
path: /docs/NEXUS_PILOT_CLI_QUICKSTART_CN.md
priority: P2
soul_alignment: harmonized
status: Current
tags:
- nexus
- sync
- - - documentation|documentation
type: Guide
updated: 2026-04-07 05:59:01+00:00
version: v23.1
visibility: internal
---


Waiver: 00_Home/[System Overview](../00_Home/System Overview.md).md
[source: nexus_wiki_vault/00_Home/System Overview.md]].md]



## One-sentence summary
- TODO

## Role / responsibility
- TODO

## Upstream
- TODO

## Downstream
- TODO

## Related modules / files
- TODO

## Source notes
- TODO

## Open questions / conflicts
- TODO

---


# Nexus Pilot CLI 快速指南（朋友版）

這份是給第一次使用 Nexus 的朋友。

## 1) 安裝（推薦：Standalone，不需 Nexus 專案）

請先拿到這支腳本（由管理者提供），然後執行：

```bash
curl -fsSL http://100.82.155.88:5005/install/nexus-pilot-friend.sh | bash
```

安裝完成後，開一個新終端機，執行：

```bash
nexus-pilot-friend <tenant_id>
```

範例：

```bash
nexus-pilot-friend pilot_a
```

如果你是開發者本人、機器上有完整 Nexus repo，才使用 repo 安裝器（開發者模式）：

```bash
bash /path/to/nexus/scripts/ops/install_nexus_pilot_friend.sh
```

## 2) 第一次啟動

第一次通常只需要輸入你的 [[api|API]] Key。

進入後會看到 `NEXUS >` 提示符，直接開始聊天即可。

## 3) 平常怎麼用

可以直接：

- 問問題（自然語言）
- 貼錯誤訊息
- 貼多行長題目（會自動當成同一題）

常用指令（朋友版）：

- `/status`：查看目前連線狀態（Tenant / Gateway / Provider / Model）。
- `/mode [remote|local]`：切換執行模式。
  - `remote`：走 Gateway（一般聊天/治理）
  - `local`：可讀取你自己的本機 workspace 內容做分析/修補建議
- `/workspace <path>`：設定 local 模式要操作的本機專案路徑。
- `/apply [on|off]`：local 模式下是否自動套用模型回傳的檔案修改。
- `/gateway <url>`：切換後端 Gateway。
- `/provider <name>`：切換供應商名稱（例如 Gemini）。
- `/model`：打開模型清單，用數字選模型。
- `/model <name>`：手動切換模型名稱。
- `/govern` 或 `/govern <[task](../task.md)>`：把任務送入治理流程。
- `/help`：顯示指令說明。
- `/exit`：離開 CLI。

範例：

```text
/status
/mode local
/workspace ~/project/my-repo
/apply off
/model
/model gemini-3-flash-preview
/govern
（下一行輸入任務內容）
/govern 幫我分析這段錯誤堆疊並給修復步驟
```

## 4) 兩種工作方式

1. `remote` 聊天/治理：直接問答、貼 bug、貼 log，或用 `/govern` 任務流。  
2. `local` 本機工作區：讓 CLI 讀你的本機專案內容（先 `/workspace`），再做分析與修補建議。

## 5) 連到遠端 Gateway（如果有提供）

若你收到主機位址，先設定：

```bash
export NEXUS_PILOT_GATEWAY_URL=http://<HOST>:5005
```

再啟動：

```bash
nexus-pilot-friend <tenant_id>
```

## 6) 常見問題

### Q1. 顯示 `command not found: nexus-pilot-friend`

1. 先重開一個新終端機。  
2. 再試一次。  
3. 還是不行就重跑安裝腳本。

### Q2. 啟動後沒回應

先輸入：

```text
/status
```

確認 Provider / Model / Gateway 是否正確，再重試提問。

### Q3. `govern` 和直接聊天差在哪裡？

- 直接聊天：拿來問問題、要建議、快速查錯。
- `/govern` 或 `/govern <[task](../task.md)>`：拿來送正式任務，讓 Gateway 走治理流程。

### Q4. 朋友說「它不能讀我本機檔案」

要用 `local` 模式，並設定 workspace：

```text
/mode local
/workspace /你的專案路徑
/apply off
```

之後直接提問，CLI 會在該 workspace 內挑選相關檔案當上下文處理。

### Q5. 朋友安裝後還是舊版（例如沒有 `/govern` 或 `/mode`）

直接重跑安裝即可：

```bash
curl -fsSL http://100.82.155.88:5005/install/nexus-pilot-friend.sh | bash
```

## 7) 安全說明

- [[api|API]] Key 只在當前 session 使用。  
- `/status` 只顯示遮罩後資訊。  
- 結束 CLI 後，session 內的 key 不會留在對話輸出中。

---

## 給管理者（非朋友）

以下內容是維運者才需要：

- 本地入口：`nexus-pilot`
- 核心交付 gate：`nexus:release-ready`（已串接 `nexus:acceptance-check`）
- 朋友安裝腳本（推薦）：`scripts/ops/install_nexus_pilot_friend_standalone.sh`
- 開發者安裝腳本（需完整 repo）：`scripts/ops/install_nexus_pilot_friend.sh`

---
[System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]