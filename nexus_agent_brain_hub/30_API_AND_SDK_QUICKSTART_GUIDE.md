# 🌐 API & SDK Quickstart Guide
**[PHYSICAL_STATUS: BETA | LAYER_5_ECOSYSTEM]**

## 1. REST API
- `POST /v1/dispatch`: 任務分派。
- `GET /v1/status/{id}`: 狀態查詢。

## 2. SDK Usage
```python
from nexus_sdk import NexusClient
client = NexusClient(endpoint="http://localhost:8080")
task_id = client.dispatch(intent="Fix memory leak", mode="hyper")
```

## 3. SSE Signaling
- 訂閱 `GET /v1/events` 獲取即時機群信令。

---
**[NEXUS ECOSYSTEM: OPEN FOR AGENTIC INNOVATION]**
