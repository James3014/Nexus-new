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
- `/mode [remote|local]`：切換模式。
  - `remote`：一般聊天與治理（走 Gateway）
  - `local`：可讀取你本機 workspace 內容分析/修補
- `/workspace <path>`：設定 local 模式下要操作的本機專案路徑。
  範例：`/workspace ~/project/my-repo`
- `/apply [on|off]`：local 模式是否自動套用模型修改。
  範例：`/apply off`
- `/gateway <url>`：切換後端 Gateway 位址。
  範例：`/gateway http://100.82.155.88:5005`
- `/provider <name>`：切換模型供應商顯示值（不會改你的 API key 類型）。
  範例：`/provider Gemini`
- `/model`：打開模型清單，用數字直接選。
- `/model <name>`：手動指定模型名稱。
  範例：`/model` 或 `/model gemini-3-flash-preview`
- `/govern` 或 `/govern <task>`：把任務送進治理流程（不是一般聊天）。
  範例：`/govern`（下一行輸入任務）或 `/govern 幫我檢查登入 API 為什麼 500`
- `/help`：顯示指令清單。
- `/exit`：離開 CLI。

平常聊天不用加指令，直接輸入問題即可。

如果你要讓 CLI 能讀你本機檔案，最短流程：

```text
/mode local
/workspace /你的專案路徑
/apply off
```

舊版升級（缺少 `/govern`、`/mode`、`/workspace` 時）：

```bash
curl -fsSL http://100.82.155.88:5005/install/nexus-pilot-friend.sh | bash
```

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
