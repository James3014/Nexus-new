---
aliases: '[Capability Hardening, Evolution Plan]'
confidence: high
owner: agent
status: active
tags: '[plans, capability, routing, swarm, sandbox]'
title: Nexus Capability Routing Hardening (Red Team Interlock Edition)
type: plans
version_scope: '[v26.0]'
---

# Nexus Capability Routing Hardening (Red Team Interlock Edition)

本實施計畫基於「紅藍對抗審計共識」，對 Nexus 18 項核心 HEEP 能力的智慧路由進行深度硬化。我們鎖定了 Swarm 通信風暴、沙盒 Operation Denied 偽失敗、與 Autoreason 剪枝退化三大瓶頸，實施極致的物理自癒防線。

---

## ⚔️ Red Team Consensus 防線

> [!WARNING]
> 1. **防止 Swarm 通信風暴 (Anti-Storm)**: subagent 狀態變更嚴禁使用即時 Webhook 高頻同步，改用本地無鎖 Blackboard 批次緩衝（Batched blackboard），死守 3% 運行期開銷。
> 2. **熱沙盒與彈性過濾 (Elastic Sandbox)**: 摒棄昂貴的冷沙盒重建。對無網路請求的 AST 能力重用熱沙盒，並依 blast radius 彈性調整唯讀白名單，防止偽 operation denied 失敗。
> 3. **測試一票否決制 (Test Veto)**: `autoreason` 主觀評審與 `ddtree` 剪枝絕不擁有最終裁決權。若被剪枝分支的 `pytest` 為 PASS，觸發 Test Veto 自動撈回，捍衛客觀證據高於主觀判定。

---

## 📂 預期物理組件變更與新增

### 1. ⚙️ [MODIFY] [nexus/core/blackboard.py](file:///Users/jameschen/workspace/nexus/nexus/core/blackboard.py)
* **目的**: 實作動態批次落盤與靜音緩衝。
* **內容**: 將即時 EventBus 消息轉為批次緩衝落盤。

### 2. ⚙️ [MODIFY] [nexus/engine/sandbox_runner.py](file:///Users/jameschen/workspace/nexus/nexus/engine/sandbox_runner.py)
* **目的**: 升級沙盒調度器。
* **內容**: 實作熱沙盒複用（Pre-warmed reuse）與彈性 profile 過濾器。

### 3. ⚙️ [MODIFY] [nexus/engine/ddtree_adapter.py](file:///Users/jameschen/workspace/nexus/nexus/engine/ddtree_adapter.py)
* **目的**: 硬化剪枝邏輯。
* **內容**: 實作雙軌共識，當 BDD tests PASS 時自動否定（Veto）剪枝決策。

---

## ⚙️ 核心演算法架構設計

### 1. 影分身沙盒動態 Profile 濾波器
```python
# sandbox_runner.py 核心邏輯
def build_elastic_profile(blast_radius):
    profile = ["(version 1)", "(deny default)"]
    for path in blast_radius.read_paths:
        profile.append(f"(allow file-read* (literal \"{path}\"))")
    for path in blast_radius.write_paths:
        profile.append(f"(allow file-write* (literal \"{path}\"))")
    return "\n".join(profile)
```

### 2. 雙軌測試一票否決演算法
$$Veto_{state} = \begin{cases} True & \text{if } Pruned_{state} = True \text{ and } Test_{result} = PASS \\ False & \text{otherwise} \end{cases}$$
當 $Veto_{state}$ 為 $True$ 時，系統會自動在 `ddtree_adapter.py` 中繞過 pruning，將該 candidate 重新放回候選隊列。

---

## 🧪 驗證與合規計畫

### Automated Tests
- 執行 `pytest tests/engine/test_ddtree_veto_policy.py`，驗證當被剪枝代碼運行 PASS 時，系統能無損撈回。
- 測試高頻併發下，Blackboard 批次寫入無資料競爭且 CPU 開銷小於 3%。

### Manual Verification
- 執行一鍵衛士 `nexus_refactor_gate_keeper.py` 驗證閉環，確認沙盒執行無 Pseudo-denied 警告。

[NEXUS IDENTITY: de0969ff + v2.8 RUNTIME-ALIGNED]
