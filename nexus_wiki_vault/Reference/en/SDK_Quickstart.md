---
title: SDK Quickstart (English)
type: reference
status: active
version_scope: v1.0.0
owner: agent
confidence: high
last_compiled: 2026-04-21
source_of_truth: nexus_wiki_vault/Reference/en/SDK_Quickstart.md
tags:
  - reference
  - quickstart
  - sdk
---

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

## One-sentence summary
本文件提供 Nexus SDK 的最小啟動與執行範例。 [Source: Reference/en/SDK_Quickstart.md]

## Role / responsibility
- 提供國際訪客的快速接入入口。 [Source: Reference/en/SDK_Quickstart.md]
- 確保基本範例對應可運行的客戶端流程。 [Source: scripts/engine/nexus_cli.py]

## Upstream
- **[Reference/en/README_Product](README_Product.md)**: 產品文檔主題入口。 [Source: Reference/en/README_Product.md]
- **[06_Ops/Ops - Wiki Sync](../06_Ops/Ops - Wiki Link Integrity.md)**: 參考連結一致性。 [Source: 06_Ops/Ops - Wiki Link Integrity.md]

## Downstream
- **[Reference/en/README_Product](README_Product.md)**: 導向產品願景。 [Source: Reference/en/README_Product.md]
- **[Reference/en](QUICKSTART.md)**: 導航性文檔銜接。 [Source: Reference/QUICKSTART.md]

## Related modules / files
- `Reference/en/SDK_Quickstart.md`
- `Reference/en/README_Product.md`
- `nexus_sdk`

## Source notes
- 內容為快速上手參考樣本，不涵蓋 API 穩定性保證。 [Source: Reference/en/SDK_Quickstart.md]

## Open questions / conflicts
- [ ] 是否需補上 CLI / Python 的真實可執行範例與版本對應？

**[Source: Reference/en/SDK_Quickstart.md]**

[[System Overview]]
