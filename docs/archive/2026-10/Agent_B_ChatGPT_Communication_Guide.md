# Agent B — ChatGPT 溝通方法

## 成功方法：AppleScript + JavaScript

### 前置條件

1. Chrome 必須已登入 ChatGPT
2. Chrome 必須啟用「允許 Apple 事件的 JavaScript」：
   - 選單列 → 檢視 → 開發人員 → 允許 Apple 事件的 JavaScript

### 讀取 ChatGPT 最後一條訊息

```bash
osascript -e '
tell application "Google Chrome"
    tell active tab of window 1
        set result to execute javascript "
            var messages = document.querySelectorAll(\"[data-message-author-role]\");
            var lastMsg = messages.length > 0 ? messages[messages.length - 1] : null;
            if (lastMsg) {
                JSON.stringify({
                    role: lastMsg.getAttribute(\"data-message-author-role\"),
                    content: lastMsg.textContent.substring(0, 3000)
                });
            } else {
                \"No messages\";
            }
        "
        return result
    end tell
end tell
'
```

### 讀取更多內容（分頁）

```bash
# 第 3000-6000 字元
osascript -e '
tell application "Google Chrome"
    tell active tab of window 1
        set result to execute javascript "
            var messages = document.querySelectorAll(\"[data-message-author-role]\");
            var lastMsg = messages.length > 0 ? messages[messages.length - 1] : null;
            if (lastMsg) {
                JSON.stringify({
                    role: lastMsg.getAttribute(\"data-message-author-role\"),
                    content: lastMsg.textContent.substring(3000, 6000)
                });
            } else {
                \"No messages\";
            }
        "
        return result
    end tell
end tell
'
```

### 發送訊息到 ChatGPT

```bash
# 1. 複製訊息到剪貼簿
echo '你的訊息內容' | pbcopy

# 2. 貼上到 Chrome
osascript -e '
tell application "Google Chrome"
    activate
end tell
delay 0.5
tell application "System Events"
    keystroke "a" using command down
    delay 0.2
    keystroke "v" using command down
end tell
'

sleep 1

# 3. 點擊 send 按鈕（按鈕 index 可能需要調整）
osascript -e '
tell application "Google Chrome"
    tell active tab of window 1
        set result to execute javascript "
            var allBtns = document.querySelectorAll(\"button\");
            var btn = allBtns[162];
            if (btn) {
                btn.click();
                \"Clicked send\";
            } else {
                \"Send button not found\";
            }
        "
        return result
    end tell
end tell
'
```

### 找 send 按鈕 index

```bash
osascript -e '
tell application "Google Chrome"
    tell active tab of window 1
        set result to execute javascript "
            var allBtns = document.querySelectorAll(\"button\");
            var info = [];
            for (var i = 0; i < Math.min(allBtns.length, 20); i++) {
                var btn = allBtns[i];
                info.push({
                    index: i,
                    testid: btn.getAttribute(\"data-testid\") || \"\",
                    aria: btn.getAttribute(\"aria-label\") || \"\",
                    text: (btn.textContent || \"\").substring(0, 30)
                });
            }
            JSON.stringify(info, null, 2);
        "
        return result
    end tell
end tell
'
```

## 不成功的方法

1. **Playwright CDP 連接** — Chrome 149+ 每次彈安全提示「允許遠端偵錯嗎？」
2. **Playwright launch** — 啟動新 Chrome 實例，沒有登入狀態
3. **AppleScript keystroke** — 需要先 focus Chrome 視窗

## 注意事項

- send 按鈕的 index (162) 可能因頁面結構變化而改變
- 如果 index 不對，用「找 send 按鈕 index」腳本重新查詢
- 訊息太長時用剪貼簿貼上，不要用 JavaScript 直接設定
- 讀取回覆時用 `substring(0, 3000)` 分段讀取，避免截斷
