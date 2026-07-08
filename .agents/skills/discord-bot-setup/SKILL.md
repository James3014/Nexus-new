---
name: discord-bot-setup
description: "Discord Bot 自動建置與 OpenAB 整合。建立 Discord bot、設定 intents、邀請至伺服器、配置 openab config.toml。"
version: 1.0.0
---

# Discord Bot Setup Skill

完整流程：從零建立 Discord bot 並接入 OpenAB。

## 觸發條件

- 用戶說「建立 Discord bot」
- 用戶說「接 Discord」
- 用戶說「openab Discord 設定」

## 前置需求

- Discord 帳號
- 已安裝 openab（`/Users/jameschen/Workspace/openab`）
- Chrome 瀏覽器（用於 AppleScript 控制）

## 完整流程

### Step 1: 建立 Discord 應用

1. 打開 Chrome 前往 https://discord.com/developers/applications
2. 點 **New Application**
3. 輸入名稱（如 `MiMo`）
4. 點 **Create**

### Step 2: 建立 Bot

1. 左側選單點 **Bot**
2. 點 **Add Bot** → **Yes, do it!**
3. 點 **Reset Token** → 複製 Token
4. 開啟 Privileged Gateway Intents：
   - ✅ **Presence Intent**
   - ✅ **Server Members Intent**
   - ✅ **Message Content Intent**（最重要！）

### Step 3: 邀請 Bot 到伺服器

1. 左側選單點 **OAuth2** → **URL Generator**
2. **Scopes** 勾選 `bot`
3. **Bot Permissions** 勾選：
   - Send Messages
   - Send Messages in Threads
   - Read Message History
   - Add Reactions
   - Use External Emojis
   - Embed Links
   - Attach Files
4. 複製生成的 URL，瀏覽器打開，選擇伺服器，授權

### Step 4: 取得正確的頻道 ID

**重要：`1490882492826386637` 是伺服器 ID，不是頻道 ID！**

用 API 取得頻道列表：
```bash
curl -s -H "Authorization: Bot <TOKEN>" \
  https://discord.com/api/v10/guilds/<GUILD_ID>/channels | python3 -m json.tool
```

或在 Discord 中：
1. 設定 → 高級 → 開啟「開發者模式」
2. 右鍵文字頻道 → 複製 ID

### Step 5: 配置 OpenAB

編輯 `/Users/jameschen/Workspace/openab/config.toml`：

```toml
[discord]
bot_token = "<YOUR_BOT_TOKEN>"
allowed_channels = ["<CHANNEL_ID_1>", "<CHANNEL_ID_2>"]
allow_all_users = true
allow_user_messages = "mentions"

[agent]
command = "mimo"
args = ["acp"]

[pool]
max_sessions = 5
```

### Step 6: 測試

```bash
cd /Users/jameschen/Workspace/openab
RUST_LOG=openab=debug cargo run
```

在 Discord @Bot 名稱 發訊測試。

## 常見問題

### Q: Bot 沒回應
A: 檢查：
1. `allowed_channels` 是否用**頻道 ID**（不是伺服器 ID）
2. `Message Content Intent` 是否開啟
3. 用戶是否用 `@Bot名稱` 發訊

### Q: 如何取得 Guild ID？
A: 右鍵伺服器圖示 → 複製 ID

### Q: 如何取得 Channel ID？
A: 右鍵文字頻道 → 複製 ID

### Q: Bot 顯示 `allow_all_channels=false channels=1`
A: 確認 `allowed_channels` 列表中有正確的頻道 ID

## AppleScript 自動化

可用 AppleScript 控制 Chrome 建立 bot：

```bash
# 打開 Discord 開發者门户
osascript -e 'tell application "Google Chrome" to tell active tab of window 1 to set URL to "https://discord.com/developers/applications"'

# 點擊 New Application
osascript -e 'tell application "Google Chrome" to tell active tab of window 1 to execute javascript "document.querySelectorAll(\"button\").forEach(b => { if(b.textContent.includes(\"新建應用程式\")) b.click() })"'
```

## 配置範例

### 單一頻道
```toml
[discord]
bot_token = "MTUx..."
allowed_channels = ["1490882493686091907"]
```

### 多頻道
```toml
[discord]
bot_token = "MTUx..."
allowed_channels = ["1490882493686091907", "1490882493686091910"]
```

### 允許所有頻道
```toml
[discord]
bot_token = "MTUx..."
allow_all_channels = true
```

## 完成標準

- [ ] Bot Token 已取得
- [ ] 三個 Privileged Intents 已開啟
- [ ] Bot 已邀請至伺服器
- [ ] 頻道 ID 已取得（不是伺服器 ID）
- [ ] config.toml 已配置
- [ ] `cargo run` 後 bot 連線成功
- [ ] 在 Discord @Bot 能收到回應
