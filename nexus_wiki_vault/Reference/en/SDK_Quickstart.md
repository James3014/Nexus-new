# 🛠️ SDK Quickstart (English)
**[VERSION: v1.0.0 | CANONICAL]**

## 1. Quick Install
```bash
pip install nexus-sdk
```

## 2. Hello Nexus
```python
from nexus_sdk import NexusClient

# Connect to Hub
client = NexusClient(endpoint="http://nexus.local:8080")

# Dispatch Intent
task_id = client.dispatch("Update system README", mode="dual")

# Await Receipt
receipt = client.wait_for_receipt(task_id)
print(f"Verified: {receipt.is_verified}")
```

## 3. Core Concepts
- **Receipts**: The proof of physical integrity.
- **Drones**: Executable worker units.
- **Swarms**: Multi-agent coordinated clusters.

---
**[NEXUS ECOSYSTEM: BUILD THE FUTURE OF TRUST]**
