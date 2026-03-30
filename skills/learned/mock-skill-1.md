---
task_id: mock-skill-1
name: "WebSocket Race Condition Fixer"
task_type: "bug"
description: "Handles race conditions in websocket connections by using a reconnect backoff strategy."
keywords: ["websocket", "race", "backoff", "reconnect"]
trust_level: reviewed
---

# WebSocket Race Condition Fixer

## 成功模式與步驟
1. 偵測到掛載時的競爭狀態。
2. 實作指數退避演算法。
3. 確保斷線後自動清理狀態。
