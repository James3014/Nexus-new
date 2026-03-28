# Nexus Pilot CLI 發送模板

把下面這段直接貼給朋友即可：

```text
這是 Nexus Pilot CLI 的試用方式。

1. 如果你還沒安裝，先執行：

curl -fsSL http://100.82.155.88:5005/install/nexus-pilot-friend.sh | bash

2. 直接啟動：

nexus-pilot-friend <你的 tenant id>

例如：

nexus-pilot-friend pilot_a

3. 第一次進去後，通常只會問你 Gemini API key。

4. 長問題可以直接貼，貼完後按一次 Enter 送出。

5. 需要治理時輸入：
/govern <任務內容>

可用指令：
/status                # 看目前連線狀態
/gateway <url>         # 切換 Gateway
/provider <name>       # 切換供應商名稱
/model <name>          # 切換模型名稱
/govern <task>         # 送正式治理任務
/help                  # 顯示指令清單
/exit                  # 離開

（給朋友版）直接用 `nexus-pilot-friend` 聊天與治理即可，不需要 Nexus 核心開發指令。
```

## 建議租戶命名

- 第一位朋友：`pilot_a`
- 第二位朋友：`pilot_b`
- 第三位朋友：`pilot_c`

## 補充

- CLI 會記住 tenant/provider/model/workspace
- API key 預設只留在 session，不會顯示完整值
- 如果看不到 `nexus-pilot-friend`，先開一個新的 terminal 視窗再試一次
- 如果還是看不到 `nexus-pilot-friend`，再執行：

```bash
source ~/.zshrc
```

- 如果你要手動指定設定，仍可用：

```bash
export NEXUS_PILOT_GATEWAY_URL=http://100.82.155.88:5005
export NEXUS_PILOT_PROVIDER=Gemini
export NEXUS_PILOT_MODEL=gemini-2.5-flash
export NEXUS_PILOT_TENANT_ID=pilot_a
export NEXUS_PILOT_API_KEY=<你的 key>
nexus-pilot-friend pilot_a
```
