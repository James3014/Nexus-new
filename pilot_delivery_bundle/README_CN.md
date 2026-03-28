# Nexus 朋友版操作手冊（兩步啟動）

這份給朋友使用，只保留「安裝 + 登入 + 對話」。

## 朋友先安裝（Standalone，免 Nexus repo）
```bash
curl -fsSL http://100.82.155.88:5005/install/nexus-pilot-friend.sh | bash
```
啟動：
```bash
nexus-pilot-friend pilot_a
```

第一次進去會問 API Key，輸入後就能開始聊天。

## 指令說明（朋友版）

- `/status`：查看目前連線狀態（Tenant / Gateway / Provider / Model）。
  範例：`/status`
- `/gateway <url>`：切換後端 Gateway 位址。
  範例：`/gateway http://100.82.155.88:5005`
- `/provider <name>`：切換模型供應商顯示值（不會改你的 API key 類型）。
  範例：`/provider Gemini`
- `/model <name>`：切換要使用的模型名稱。
  範例：`/model gemini-2.5-flash`
- `/govern <task>`：把任務送進治理流程（不是一般聊天）。
  範例：`/govern 幫我檢查登入 API 為什麼 500`
- `/help`：顯示指令清單。
- `/exit`：離開 CLI。

平常聊天不用加指令，直接輸入問題即可。

若出現 `command not found`，先補 PATH：
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## 維運者（你）才需要的入口

如果要跑 Nexus 核心任務流（不是朋友對話入口），請在你的 Nexus repo 內執行：

```bash
python3 scripts/engine/nexus_cli.py <command>
```
