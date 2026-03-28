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

第一次通常只需要輸入你的 API Key。

進入後會看到 `NEXUS >` 提示符，直接開始聊天即可。

## 3) 平常怎麼用

可以直接：

- 問問題（自然語言）
- 貼錯誤訊息
- 貼多行長題目（會自動當成同一題）

常用指令（朋友版）：

- `/status`：查看目前連線狀態（Tenant / Gateway / Provider / Model）。
- `/gateway <url>`：切換後端 Gateway。
- `/provider <name>`：切換供應商名稱（例如 Gemini）。
- `/model <name>`：切換模型名稱。
- `/govern <task>`：把任務送入治理流程。
- `/help`：顯示指令說明。
- `/exit`：離開 CLI。

範例：

```text
/status
/model gemini-2.5-flash
/govern 幫我分析這段錯誤堆疊並給修復步驟
```

## 4) 兩種工作方式

1. 聊天模式：直接問答、貼 bug、貼 log。  
2. 治理模式：輸入 `/govern <任務內容>`，進入任務導向流程（分析、修復、回報）。

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
- `/govern <task>`：拿來送正式任務，讓 Gateway 走治理流程。

## 7) 安全說明

- API Key 只在當前 session 使用。  
- `/status` 只顯示遮罩後資訊。  
- 結束 CLI 後，session 內的 key 不會留在對話輸出中。

---

## 給管理者（非朋友）

以下內容是維運者才需要：

- 本地入口：`nexus-pilot`
- 核心交付 gate：`nexus:release-ready`（已串接 `nexus:acceptance-check`）
- 朋友安裝腳本（推薦）：`scripts/ops/install_nexus_pilot_friend_standalone.sh`
- 開發者安裝腳本（需完整 repo）：`scripts/ops/install_nexus_pilot_friend.sh`
