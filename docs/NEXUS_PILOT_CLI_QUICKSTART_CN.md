# Nexus Pilot CLI 快速使用指南

## 目的

這份指南是給第一批朋友或 pilot tenant 用的。

你會拿到一個聊天式 CLI，先體驗 Nexus 的高速問答，再在對話中升級成治理任務。

## 啟動方式

如果朋友是自己安裝這版：

```bash
bash /path/to/nexus/scripts/ops/install_nexus_pilot_friend.sh
```

安裝完成後可直接執行：

```bash
nexus-pilot-friend pilot_a
```

推薦直接給朋友這條：

```bash
nexus-pilot-friend pilot_a
```

它會自動帶入：

- `Gateway = http://100.82.155.88:5005`
- `Provider = Gemini`
- `Model = gemini-2.5-flash`

如果你直接在專案內執行：

```bash
/usr/bin/python3 /Users/jameschen/Workspace/nexus/scripts/nexus_chat_cli.py
```

如果已安裝專案 script：

```bash
nexus-pilot
```

## 首次啟動會問你

現在的朋友模式預設只會問：

1. `API Key`

其餘欄位會自動補上或沿用既有設定：

- `Tenant ID`：可由 `nexus-pilot-friend pilot_a` 或環境變數帶入
- `Provider`：預設自動走 `Gemini`
- `Model`：預設 `gemini-2.5-flash`
- `Workspace`：先略過，需要時再用 `/mount`

如果你手動執行 `nexus-pilot`，沒有預設 tenant 時，系統也會自動生成一個預設 tenant id，不再卡在第一步。

填完後就會直接進入 Nexus 主畫面。

第一次填完後，CLI 會自動記住以下內容，之後通常不用再重填：

- Tenant ID
- Provider
- Model
- Workspace

`API Key` 預設不寫入持久設定，但你可以用環境變數一次帶入：

```bash
export NEXUS_PILOT_API_KEY=你的_API_KEY
```

## 基本使用方式

直接輸入自然語言即可：

- `幫我看這個錯誤`
- `這段 stack trace 是什麼意思`
- `幫我修這個 bug`

現在可以直接貼長文與多行題目。
CLI 會把同一波貼上的內容收成同一題，不需要靠 `/paste` 這類額外命令。

當 Nexus 判斷這已經是治理任務時，會提示你升級為 Battle Mode。

## 可用指令

- `/status`
- `/mount <workspace>`
- `/clone <repo-url> [dest]`
- `/provider <name>`
- `/model <name>`
- `/govern`
- `/reset`
- `/exit`

## 處理本機專案

如果朋友要處理自己的本機目錄：

```text
/mount /path/to/project
```

掛好後可直接問：

```text
幫我分析這個專案
/govern
```

## 處理 GitHub repo

如果朋友手上只有 GitHub URL：

```text
/clone https://github.com/your-org/your-repo.git
```

CLI 會：

- clone 到預設工作區
- 自動把該目錄設成目前 workspace

如果想自訂目的地：

```text
/clone https://github.com/your-org/your-repo.git /path/to/dest
```

## 典型流程

```text
1. 啟動 CLI
2. 只輸入 API key
3. 先問問題或貼錯誤
4. 如果需要治理，輸入 /govern
5. 查看 task 與 phase 摘要
```

## 安全說明

- API key 只會存在於目前 session
- `/status` 只會顯示遮罩後的 key
- 結束 session 後會清除 session 內的 secret

## 目前版本限制

- Battle Lane 已有正式 gateway contract，但若 gateway 不可用，會退回本地 stub
- 本版重點是 pilot 體驗，不是完整公開版 Nexus
- 若要接正式遠端 runtime，請設定 `NEXUS_PILOT_GATEWAY_URL`

## 自訂 Gateway

如果你有自己的 gateway：

```bash
export NEXUS_PILOT_GATEWAY_URL=http://your-host:5005
nexus-pilot
```

## Tailscale 發放建議

如果朋友是透過你的 Tailscale 內網接入，建議直接把 gateway 指到你的這台主機：

```bash
export NEXUS_PILOT_GATEWAY_URL=http://100.82.155.88:5005
nexus-pilot
```

這樣朋友的 CLI 會透過 Tailscale 連到你的 Nexus Gateway，而不是直接暴露公網 port。

建議流程：

1. 你的主機先啟動 `nexus-pilot-proxy`
2. 朋友在自己的機器上設定 `NEXUS_PILOT_GATEWAY_URL=http://100.82.155.88:5005`
3. 朋友執行 `nexus-pilot-friend pilot_a`
4. 朋友只需要輸入自己的 API key

如果你想讓朋友幾乎不用設定，建議一起提供以下環境變數：

```bash
export NEXUS_PILOT_GATEWAY_URL=http://100.82.155.88:5005
export NEXUS_PILOT_PROVIDER=Gemini
export NEXUS_PILOT_MODEL=gemini-2.5-flash
```

若你已替某位朋友指定 tenant，也可以直接加上：

```bash
export NEXUS_PILOT_TENANT_ID=pilot_a
```

這樣朋友第一次進 CLI 時，通常只需要補自己的 API key，甚至連這個都可以用 `NEXUS_PILOT_API_KEY` 事先帶入。

如果未來你改用 MagicDNS，也可以把 IP 換成你的 Tailscale hostname。

## 本地 Proxy

若要手動啟動本地 proxy：

```bash
nexus-pilot-proxy
```
