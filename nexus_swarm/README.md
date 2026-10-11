# Nexus-Go Swarm (v18 Phase A) Demo

## 🌟 簡介
這是 Nexus 向分散式架構演進的第一個實體原型 (MVP)。
它展示了如何使用 **Go (指揮官)** 跨過 HTTP/JSON 協議，同時調度多個 **v17 (執行節點)**。

## 🏗️ 核心組件
1. **Swarm Manager (Go)**: 位於 `manager/`，負責任務分發（部署用 `manager/Dockerfile`）。
   - `cmd/swarm-manager/` 是已退役的 v18 demo：它用到已從 proto 移除的訊息，以 build tag `legacy_v18_demo` 排除在建置之外。
2. **Idempotency Engine (Go)**: 位於 `pkg/index/`，保證全球一致性。
3. **v17 Node (Python)**: `scripts/nexus_cli.py --swarm-mode`，接收並執行任務。

## 🚀 如何建置
v18 demo 腳本 `scripts/test_local_swarm.sh` 已退役。建置現行 manager：
```bash
cd nexus_swarm && go build ./manager
```

## 📊 觀察重點
- **並行性**: 觀察 3 個節點是否幾乎同時收到請求並回傳。
- **冪等性**: Swarm Manager 內部會檢查 Key。若同一個任務被派發，只有第一個 Node 會被 TryStart 成功。
- **吞吐量**: 總執行時間應接近單一任務耗時 + 網絡開銷。

---
**Nexus V17 | Phase 17: Singularity Swarm**
