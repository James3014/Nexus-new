---
aliases:
- gRPC Security Gap
- mTLS Technical Debt
confidence: absolute
last_compiled: 2026-04-07
owner: agent
priority: P3
related_pages:
- '[[System Overview]]'
- '[[System - Unknowns and Conflicts]]'
source_of_truth: nexus_swarm/cmd/swarm-manager/main.go
status: active
tags:
- security
- audit
- mtls
- grpc
- debt
title: Audit - mTLS and Service Mesh Gap
type: security_audit
version_scope:
- v23.1
---



# Audit - mTLS and Service Mesh Gap

## One-sentence summary
本報告針對 Nexus 內部通訊協議 (NSP) 的加密缺失進行風險評級，確認 gRPC 目前仍採用明文傳輸 (Plaintext)，導致治理分數定格於 8.5/10。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **風險識別**: 確認服務間通訊缺乏雙向 TLS (mTLS) 認證。 [Code: nexus_swarm/cmd/swarm-manager/main.go]
- **合規缺口**: 導致無法滿足 Trident 3.0 的「全鏈路加密 (Full Chain Encryption)」規範。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **優化指引**: 作為 Phase 4 安全性強化的實作對位點。

## Technical Evidence

### 1. gRPC Server Initialization
在 `nexus_swarm/cmd/swarm-manager/main.go` 中，gRPC Server 的啟動邏輯如下：
```go
// Current Insecure Implementation
s := grpc.NewServer()
// MISSING: credentials.NewTLS(...)
```
這證實了通訊層未掛載任何憑證，屬於 insecure 狀態。

### 2. Physical Data Risk
- **監聽風險**: 跨節點傳輸（如從 Sensing Agent 到 Swarm Manager）的治理指令可被物理網絡設備截獲。
- **身分冒充**: 缺乏 mTLS 導致任何能存取廣播地址的進程皆可嘗試發送偽造的 NSP 包。

## Audit Grade (審計評分)
- **Current Score**: 🟢 **8.5 / 10**
- **Deduction Reason**: 
    - Physical Layer Insecurity (-1.0)
    - Identity Verification Missing (-0.5)

## Recovery Path (修復路徑)
1.  **Phase 1 (Identity)**: 建立內部的根憑證中心 (Root CA)。
2.  **Phase 2 (Handshake)**: 將 `grpc.WithInsecure()` 替換為 `grpc.WithTransportCredentials(creds)`。
3.  **Phase 3 (Service Mesh)**: 若環境複雜，建議導入 Istio 或 Linkerd 作為加密邊車。

## Source notes
- [Consensus Report 0d389da5](file:///Users/jameschen/.gemini/antigravity/brain/0d389da5-3a15-4717-b21c-cd5aad468415/overview.txt): 首次識別此項治理債務。

---
[[System Overview]] | [[System - Unknowns and Conflicts]]


## Upstream
- TBD

## Downstream
- TBD

## Related modules / files
- TBD

## Open questions / conflicts
- TBD