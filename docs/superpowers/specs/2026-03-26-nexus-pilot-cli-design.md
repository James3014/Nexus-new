# Nexus Pilot CLI 設計規格

日期：2026-03-26  
狀態：已核准，可進入規劃  
對象：Pilot tenant 產品設計、CLI / Runtime 架構、實作規劃

## 1. 產品定位

`Nexus Pilot CLI` 是一個 `chat-first`、`task-capable`、`closed-core` 的治理入口。

對使用者而言，它看起來像一個高速終端助理，可以回答問題、解讀錯誤、給出修復方向。  
但在底層，它其實是接入你控管的 Nexus runtime，能從輕量對話升級成受治理保護的修復與執行流程。

它不是一般開源 coding assistant。  
它的定位是：在不暴露 Nexus 核心戰甲、編排策略與內部資產的前提下，讓外部 pilot tenant 體驗 Nexus 的治理能力。

## 2. V1 目標

V1 必須證明四件事：

1. Pilot tenant 能在 60 秒內完成首次啟動。
2. 第一輪互動能建立明確的「Nexus 很快」印象。
3. 使用者能自然地從聊天升級成治理任務。
4. Nexus 的核心治理能力仍由 host runtime 控管，不外流。

## 3. V1 非目標

V1 不追求以下事項：

- 完整開源 Nexus 核心。
- 桌面 GUI 或 Web App。
- 一次整合太多 provider。
- 不經確認就直接開放高風險 patch / apply。
- 以現有 `scripts/nexus_chat_cli.py` 為最終產品架構。

## 4. 系統架構

V1 採用 Hybrid 模式，分成三層：

### 4.1 本地 CLI Shell

負責：

- 使用者 onboarding
- prompt 與終端畫面
- 本地 session 狀態
- 快速對話體驗
- 指令處理
- workspace 選擇
- task / phase 顯示

它的任務是保住速度與可用性。

### 4.2 本地 Adapter

負責：

- `chat` / `analyze` / `govern` 路由
- 將自然語言轉成 Nexus 任務意圖
- 收集最小必要本地上下文
- 處理串流輸出與狀態更新

這層可以有輕量策略，但不能放高價值治理核心。

### 4.3 遠端 Nexus Runtime / Gateway

真正的 closed-core 能力留在這裡：

- Battle Lane 治理邏輯
- tenant policy
- sentinel 與安全護欄
- 任務編排
- distillation
- 經濟與審計邏輯
- 高風險動作授權

邊界原則：

- 本地保速度
- 遠端保主權

## 5. 互動模型

V1 分成兩條執行路徑。

### 5.1 Fast Lane

用於：

- 一般問答
- stack trace 解讀
- bug 初判
- 修復方向建議
- 架構建議

Fast Lane 目標是低延遲。除非需要升級，不應一開始就啟動重型治理流程。

### 5.2 Battle Lane

用於：

- 明確的修 bug 請求
- repo 治理
- 受治理保護的分析流程
- 修復流程
- 驗證導向的任務執行

Battle Lane 會引入：

- `task_id`
- phase 進度
- 戰報式回傳
- 治理安全邊界

### 5.3 升級規則

預設留在 Fast Lane。  
只有當使用者意圖明確進入執行級工作時，才升級，例如：

- `fix this bug`
- `analyze this repo`
- `govern this project`
- 已掛載 repo 且提出可執行問題

理想體驗是：

1. 先給快速答案
2. 再給清楚的升級提示
3. 確認後再進入治理流程

## 6. Onboarding 流程

首次啟動必須短而直線。

### 6.1 首次啟動步驟

1. 輸入 `Tenant ID`
2. 選擇 `Provider`
3. 輸入 `API Key`
4. 選擇 `Model`
5. 選擇 `Workspace` 或略過
6. 進入主 prompt

### 6.2 設計原則

- 一次只問一件事
- 儘量有推薦值
- 不要求先理解 Nexus 術語
- 設定完即可立即使用

### 6.3 主畫面

首屏要清楚傳達三件事：

- 可以立刻發問
- 可以立刻貼錯誤
- 可以隨時升級治理

建議畫面：

```text
Nexus Singularity
Tenant: pilot_a
Provider: OpenAI
Model: gpt-5.4
Workspace: ~/project
Mode: FAST

Ask anything, paste an error, or mount a repo to start governance.
Commands: /mount  /govern  /status  /provider  /model  /exit

NEXUS >
```

## 7. 指令模型

自然語言是主介面，slash command 只是系統控制層。

### 7.1 自然語言優先

下列情境都應該不用指令就能工作：

- `幫我看這個錯誤`
- `分析這個 repo`
- `修這個 bug`
- `這個 stack trace 到底怎麼回事`

### 7.2 保留的 Slash Commands

V1 指令面只保留：

- `/mount`
- `/govern`
- `/status`
- `/provider`
- `/model`
- `/reset`
- `/exit`

### 7.3 二次確認規則

以下動作必須要求確認：

- 掛載新的 workspace 或 repo
- 進入 Battle Lane
- 任何可能修改檔案或執行命令的操作

## 8. 安全模型

### 8.1 API Key 處理

Pilot tenant 帶自己的 API key。  
這些 key 預設只活在 session 期間，且不能出現在：

- 戰報
- log
- telemetry
- distillation 紀錄
- 錯誤輸出

### 8.2 Secret Silo 要求

V1 至少要做到：

- session 級 secret handling
- 所有輸出都遮罩 key
- 任務或 session 結束後清理
- 治理產物中不保留原始 key

### 8.3 Tenant 隔離

每個 tenant session 必須保留：

- 獨立 session context
- workspace 關聯
- 不重疊的治理狀態
- 共用智慧層不得洩漏租戶識別資訊

### 8.4 審計範圍

應該記錄：

- 行為軌跡
- phase 狀態
- 確認事件
- 成功 / 失敗結果
- token 與使用估算

不應記錄：

- 原始 API key
- 私有程式碼全文
- 不必要的租戶機密

## 9. 回應風格

CLI 必須像治理終端，不像 noisy debug console，也不像客服聊天機器人。

### 9.1 Fast Lane 風格

- 短
- 準
- 有用
- 低噪音

範例：

```text
初步判斷：這比較像依賴版本衝突，不是業務邏輯錯誤。
先檢查 lockfile 與 CI Python 版本是否一致。
如果要，我可以掛載 workspace 並升級成治理流程。
```

### 9.2 Battle Lane 風格

Battle Mode 只顯示高價值訊號：

```text
Battle Mode engaged.
Task: T-1024

Sensing: 已定位 3 個可疑點
Planning: 正在選擇最低風險修復路徑
Repair: 已生成候選補丁
Verify: 測試執行中
```

### 9.3 完成戰報風格

戰報應聚焦：

- root cause
- action
- result
- next step

不傾倒低價值內部噪音。

## 10. V1 成功指標

若符合以下條件，代表 V1 成功：

- 首次啟動在 60 秒內完成
- 首輪互動有明顯速度感
- 使用者自然理解聊天到治理的升級路徑
- 至少能透過 CLI 完成一次真實治理任務
- key 安全邊界成立
- pilot tenant 感受到 Nexus 是治理系統，而不是普通聊天殼

## 11. 失敗訊號

若出現以下情況，代表方向失準：

- 啟動流程太長或太亂
- 第一輪回應太慢
- command 感太重，像 devtool
- Battle Lane 噪音太多
- secret handling 讓人不放心
- 使用者無法分辨 Nexus 與一般 coding CLI 的差異

## 12. 產品建議

不要再把現有 `scripts/nexus_chat_cli.py` 原型往最終產品方向硬推。

建議做法：

1. 把現有 chat CLI 視為可丟棄原型
2. 新建一個 chat-first 的 `Nexus Pilot CLI`
3. 能重用的 engine / task 能力就重用
4. closed-core 治理邏輯保留在遠端 runtime / gateway
5. 優先優化「第一印象很快」，再展示治理升級能力
