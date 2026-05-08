---
aliases: '[Multi-Node, Swarm Deployment, Cluster Architecture]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
source_of_truth: nexus/core/swarm.py
status: production
tags: '[system, swarm, deployment, mtls, redis]'
title: System - Swarm Multi-Node
---

# System - Swarm Multi-Node (v26 Production)

## One-sentence summary
本頁定義 Nexus 跨物理節點的機群佈署架構、mTLS 安全通訊與 Redis 狀態同步機制。

## ⚙️ 機群拓撲 (Architecture)
Nexus 採「Hub-and-Spoke」模型：
- **Orchestrator Hub (L4)**: 負責 DAG 拆解與節點調度。
- **Tactical Drones (L2)**: 運行於分散節點，由 1-bit Core 保護執碼。

## 🛡️ 安全佈署要求 (Deployment)
1. **mTLS Auth**: 每個節點必須持有從 `.nexus/certs/` 核發的專屬證書。
2. **Redis Metabolism**: 必須配置全域可達的 Redis 實例以同步 `Lesson` 與 `Metabolism` 快照。
3. **SSE Signal**: 開放 `NEXUS_SSE_PORT` (預設 8080) 以維持實體信令心跳。

## 🚀 Docker Compose 範本
```yaml
services:
  nexus-hub:
    image: nexus-core:v26
    environment:
      - REDIS_URL=redis://global-redis:6379
  drone-node-01:
    image: nexus-drone:v26
    environment:
      - NEXUS_HUB_URL=http://nexus-hub:8080
      - NEXUS_NODE_ID=DRONE_01
```

---
**[Source: nexus/core/swarm.py]**

## Role / responsibility
- 定義跨節點佈署模型、節點溝通與故障邊界。

## Upstream
- [[01_System/MUSE_PROTO|MUSE_PROTO]]
- [[System Relationship and Dependency Graph|System Relationship and Dependency Graph]]

## Downstream
- [[06_Ops/Security/Audit - mTLS and Service Mesh Gap|mTLS Audit Gap]]
- [[06_Ops/Ops - Performance Benchmarks|Performance Benchmarks]]

## Related modules / files
- [Source: nexus/core/swarm.py]
- [Source: compiled-wiki]
- [[System Overview]]

## Source notes
- [Source: compiled-wiki]

## Open questions / conflicts
- 多節點佈署故障時，是否應先保留 Hub 或降級到單節點保守模式？
