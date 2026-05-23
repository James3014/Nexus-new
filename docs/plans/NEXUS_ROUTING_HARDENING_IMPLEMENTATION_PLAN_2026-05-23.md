---
aliases: '[Routing Hardening Plan, NKP Upgrade Plan]'
confidence: high
owner: agent
status: active
tags: '[plans, routing, security, compilation]'
title: Nexus Routing Hardening & NKP Upgrades (Red Team Consensus Edition)
type: plans
version_scope: '[v26.0]'
---

# Nexus Routing Hardening & NKP Upgrades (Red Team Consensus Edition)

本實施計畫基於「紅藍對抗審計共識」，旨在對 Nexus 策略路由（Capability Planner）與轉譯管線進行極致硬化。我們摒棄了昂貴或引發偽死鎖的過度設計，採用「業力衰退、方法級細粒度鎖、唯讀哈希鏈與保護區 Token 剪枝」四大極致方案。

---

## ⚔️ Red Team Audit & Consensus 防線

> [!WARNING]
> 1. **防止業力偽死鎖 (Karma Decay)**: 業力懲罰絕不粗暴設為 forbidden，必須加入「半衰期衰退演算法」，確保因網路暫時超時導致的失敗能隨時間自動修復。
> 2. **捍衛 Swarm 吞吐量 (Swarm Throughput)**: 嚴禁對整個檔案加鎖。我們採用「方法級粒度鎖」與「 shadow 影分身 worktree」三向合併，確保 subagent 能並行運作。
> 3. **保留 Agent 重構視野 (Anti-Blindness)**: 對目標修改區實施 100% 視野保護，嚴禁對其進行 Token 剪枝，僅對遠程低頻節點進行骨架化瘦身。

---

## 📂 預期物理組件變更與新增

### 1. ⚙️ [MODIFY] [nexus/engine/capability_planner.py](file:///Users/jameschen/workspace/nexus/nexus/engine/capability_planner.py)
* **目的**: 升級路由 Planner 決策演算法。
* **內容**:
  - 實作 `_apply_karma_decay_policy()`：導入業力懲罰半衰期衰退演算法。
  - 升級 `_build_context_slimming_policy()`：導入 AST 保護區剪枝，死守 3% 效能防線。

### 2. 📄 [NEW] [scripts/ops/build_attested_hash_chain.py](file:///Users/jameschen/workspace/nexus/scripts/ops/build_attested_hash_chain.py)
* **目的**: 替代金鑰管理，實作無開銷的運行期 receipts 哈希驗證鏈。
* **內容**: 將 Session ID、Snapshot 與 receipts 做 SHA-256 鏈式校驗。

### 3. ⚙️ [MODIFY] [scripts/ops/nexus_refactor_gate_keeper.py](file:///Users/jameschen/workspace/nexus/scripts/ops/nexus_refactor_gate_keeper.py)
* **目的**: 更新 Gatekeeper 集成腳本。
* **內容**: 整合哈希鏈校驗與 NKP 編譯自動化。

---

## ⚙️ 核心演算法架構設計

### 1. 業力指數衰退公式 (Decay Function)
當某能力在 Replan 第 $t$ 輪被懲罰時，其業力影響值將隨輪數衰減：
$$K_t = K_0 \cdot e^{-\lambda t}$$
其中 $\lambda$ 為半衰係數。這確保了因環境網路超時引起的暫時性失敗，能在隨後的 Replan 中自動修復。

### 2. AST 視野保護區剪枝機制 (Pruning Policy)
```python
def check_pruning_eligibility(node_path, target_mutated_paths):
    # 若該節點屬於修改目標或直接依賴，嚴禁剪枝
    if node_path in target_mutated_paths or is_direct_dependent(node_path):
        return False  # Protected Zone
    return True  # Eligible for Slimming
```

---

## 🧪 驗證與合規計畫

### Automated Tests
- 執行 `pytest tests/engine/test_routing_hardening.py`，驗證在模擬超時與失敗下，大腦能正確觸發「業力衰退自癒」而不發生偽死鎖。
- 測試大容量代碼包在 token Slimming 下，目標修改區註釋依然 100% 完整存留。

### Manual Verification
- 執行 `nexus_refactor_gate_keeper.py` 驗證一鍵閉環自檢流程，確認哈希鏈生成成功，Wiki 編譯正常。

[NEXUS IDENTITY: de0969ff + v2.8 RUNTIME-ALIGNED]
