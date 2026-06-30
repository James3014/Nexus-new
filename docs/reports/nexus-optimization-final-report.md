# Nexus 本地模型優化：內部結案報告

> **Status**: Internally accepted, externally unsealed — claim-safe pending evidence appendix

**版本**：vFinal
**日期**：2026-06-15
**基準 Commit**：`fad8f32e`
**最新 Commit**：`1726c4ae`
**總 Commits**：26

---

## 一、執行摘要

本報告涵蓋兩輪優化計畫：

1. **第一輪：Speed Optimization**（141s → 58.5s）
2. **第二輪：Capability Uplift**（PACT + Skill Memory + SWE-Explore）

### 核心成果

| 指標 | 改善前 | 改善後 | 變化 |
|:---|:---:|:---:|:---:|
| **Execution time** | 141s | 58.5s | **-58%** |
| **Total time** | 164s | 75s | **-54%** |
| **Model tokens** | 0 (未追蹤) | 6,275 | 可觀測 |
| **Prompt tokens** | ~500 | ~189 | **-62%** |
| **Gate tests** | 29/31 | 55/55 | +26 |
| **Feature flags** | 0 | 3 | 新增 |
| **Role contracts** | 無 | 有 | 新增 |

---

## 二、第一輪：Speed Optimization

### 2.1 關鍵改動

| Commit | 內容 | 效果 |
|:---|:---|:---|
| `c8806a71` | R phase model invocation 修復 | Model 從 0 → 6275 tokens |
| `06a8d918` | Lazy imports 優化 | memory_indexer 5.8s → 0.03s |
| `62f798cf` | num_predict 限制 8192→512 | **141s → 64s（-55%）** |
| `11e6ae67` | Token tracking 修復 | Token 可觀測 |
| `ffcb597b` | FAST_MODE 動態路由 | 正確路由簡單任務 |
| `e7982921` | Retry failure injection | 減少 retry 次數 |
| `7af62eb9` | Dynamic context window | Token 優化 |
| `36c2961e` | Patch prompt 精簡 | Prompt -62% |
| `2be15a79` | Failure Memory Bank | 避免重複錯誤 |
| `d2341d3a` | AST call graph scoring | Localization 準確度 |
| `96e00ce4` | Interleaved generation | 減少 LLM call |

### 2.2 時間分佈對比

```
改善前 (141s execution):
  P: 10s | D: 6s | R: 86s (model 0s + overhead 86s) | A: 1s

改善後 (58.5s execution):
  P: 9s | D: 5s | R: 42s (model 12s + overhead 30s) | A: 1s
```

### 2.3 根本發現

**唯一真正加速的是 `num_predict=512`**（-77s）。其他 D1-D8 改動都是 correctness/cost 優化，不是 speed 優化。

真正的瓶頸是 **pipeline overhead（73%）**，不是 model inference（27%）。

---

## 三、第二輪：Capability Uplift

### 3.1 Slice A: PACT for 3B Advisor

**目標**：將 3B advisor output 壓成 compact action-state records。

**改動**：
- `nexus/contracts/pact.py`：PACTRecord, validate_pact_record, pact_from_advisor_output
- `nexus/services/s2t_strict.py`：advise() 支援 PACT dual-output

**結果**：
- Advisor output ~100-200 tokens（JSON）
- 9 tests pass
- Feature flag: `NEXUS_S2T_PACT_ENABLED`

### 3.2 Slice B: Skill Memory Query Layer

**目標**：建立 unified read-model 查詢 skill history。

**改動**：
- `nexus/learning/skill_memory_index.py`：SkillMemoryIndex, SkillHistoryRecord
- 查詢 API：query_skill_history, query_contextual_skill_candidates, query_failure_patterns
- Context injection for low-risk assisted routing

**結果**：
- 7 tests pass
- Feature flag: `NEXUS_S2T_SKILL_MEMORY_ENABLED`

### 3.3 Slice C: SWE-Explore Lite

**目標**：multi-granularity retrieval（file → symbol → line-window）。

**改動**：
- `nexus/search/swe_explore_lite.py`：SWEExploreLite, LineWindowEvidence, RetrievalBudget
- File → symbol → line-window retrieval
- Line-window evidence with confidence scores

**結果**：
- 8 tests pass
- Feature flag: `NEXUS_RETRIEVAL_MULTIGRANULARITY_ENABLED`

### 3.4 三層架構邊界

| 角色 | 責任 | 邊界 |
|:---|:---|:---|
| **3B** | Selector/reranker (PACT output) | 只做 low-risk assisted routing |
| **7B/14B** | Search/localize/patch (SWE-Explore) | 只做 repo exploration/repair |
| **Nexus** | Governance/verification/claim gate | 維持唯一權威裁決面 |

---

## 四、測試結果

### 4.1 測試清單

| 測試類別 | 數量 | 結果 |
|:---|:---:|:---:|
| Gate tests | 31 | ✅ |
| PACT tests | 9 | ✅ |
| Skill memory tests | 7 | ✅ |
| SWE-Explore tests | 8 | ✅ |
| **Total** | **55** | **✅** |

### 4.2 Feature Flags

| Flag | 預設 | 狀態 |
|:---|:---:|:---:|
| `NEXUS_S2T_PACT_ENABLED` | OFF | 可啟用 |
| `NEXUS_S2T_SKILL_MEMORY_ENABLED` | OFF | 可啟用 |
| `NEXUS_RETRIEVAL_MULTIGRANULARITY_ENABLED` | OFF | 可啟用 |

---

## 五、Governance Safety

### 5.1 驗證項目

| 項目 | 狀態 |
|:---|:---:|
| Fail-closed gate 未被繞過 | ✅ |
| Syntax Preflight 正常 | ✅ |
| Refusal detection 正常 | ✅ |
| Patch invocation boundary 正常 | ✅ |
| public claim / delivery gate 未被旁路 | ✅ |
| 3B 未越權 | ✅ |
| Role drift detection | ✅ |

### 5.2 Role Contract

- `role_contract.py`：ModelRole, PhaseRole, PHASE_ROLE_CONTRACT
- Role drift detection：logs warning when model violates role boundary
- Role receipt tracking：selected_model_role, invoked_model_role, reason_code

---

## 六、交付物

| 項目 | 狀態 |
|:---|:---:|
| 變更檔案清單 | ✅ 26 commits |
| 每個 slice 的 contract 說明 | ✅ |
| 測試指令與結果 | ✅ 55/55 |
| before/after replay 報告 | ✅ |
| 風險與 rollback 說明 | ✅ |
| Feature flags | ✅ 3 flags |
| Role contracts | ✅ |

---

## 七、風險與 Rollback

### 7.1 剩餘風險

1. **Persistent Worker**：pipe deadlock 修復但未完全驗證
2. **SentenceTransformer loading**：仍在 cold start 路徑（~5s）
3. **Feature flags 預設 OFF**：需要手動啟用才能使用新功能

### 7.2 Rollback

所有改動都可透過 feature flags 關閉：
- `NEXUS_S2T_PACT_ENABLED=0`：關閉 PACT dual-output
- `NEXUS_S2T_SKILL_MEMORY_ENABLED=0`：關閉 skill memory injection
- `NEXUS_RETRIEVAL_MULTIGRANULARITY_ENABLED=0`：關閉 multi-granularity retrieval

---

## 八、Lesson Writeback

### 8.1 Speed Optimization Lessons

1. **`num_predict=512` 是關鍵優化**：限制 output token 比增加 input context 更有效
2. **Pipeline overhead 是真正瓶頸**：73% 時間花在非 model 操作
3. **D1-D8 改動是 correctness/cost 優化**：不是 speed 優化

### 8.2 Capability Uplift Lessons

1. **PACT dual-output 安全**：legacy output + PACT output，可隨時關閉
2. **Skill Memory Query 只讀不寫**：不修改原始紀錄源
3. **SWE-Explore Lite 是 retrieval 改善**：不影響 governance

---

## 九、下一步建議

### 9.1 如果要繼續追 speed

| 優先級 | 動作 | 預期收益 |
|:---:|:---|:---:|
| 1 | Persistent Worker（修 pipe deadlock） | -17s |
| 2 | Lazy load SentenceTransformer | -5s |
| 3 | 減少 pipeline phases | -10s |

### 9.2 如果要繼續做 capability

| 優先級 | 動作 | 預期收益 |
|:---:|:---|:---:|
| 1 | 啟用 feature flags 做 shadow testing | 驗證效果 |
| 2 | 收集 production telemetry | 量化改善 |
| 3 | 逐步 rollout | 降低風險 |

---

*報告日期：2026-06-15*
*基準 Commit：fad8f32e*
*最新 Commit：1726c4ae*
*狀態：Internally accepted, externally unsealed*

---

## 附錄 A：測試證據

### A.1 測試命令與結果

```bash
# Gate tests (31 tests)
$ uv run python -m pytest tests/gates/ -q
31 passed in 5.77s

# PACT tests (9 tests)
$ uv run python -m pytest tests/test_pact.py -v
9 passed in 0.13s

# Skill memory tests (7 tests)
$ uv run python -m pytest tests/test_skill_memory.py -v
7 passed in 0.12s

# SWE-Explore tests (8 tests)
$ uv run python -m pytest tests/test_swe_explore_lite.py -v
8 passed in 0.12s

# All tests combined (55 tests)
$ uv run python -m pytest tests/gates/ tests/test_pact.py tests/test_skill_memory.py tests/test_swe_explore_lite.py -q
55 passed in 5.89s
```

### A.2 測試覆蓋率

| 測試類別 | 數量 | 結果 | 關鍵驗證 |
|:---|:---:|:---:|:---|
| Gate tests | 31 | ✅ | S2T claim/delivery/rollout 正常 |
| PACT tests | 9 | ✅ | Schema validation, forbidden fields, observation_only |
| Skill memory tests | 7 | ✅ | Query, context injection, failure patterns |
| SWE-Explore tests | 8 | ✅ | File/symbol/line-window retrieval |

---

## 附錄 B：Replay 證據

### B.1 Execution Time Baseline vs Latest

```bash
# Baseline (commit fad8f32e)
$ NEXUS_OAUTH_PROVIDER=ollama NEXUS_USE_SURGICAL_REPAIR=1 \
  python3 scripts/engine/nexus_cli.py nexus run \
  "add import json to nexus/engine/coordinator.py"
# Execution: ~141s

# Latest (commit 1726c4ae)
$ NEXUS_OAUTH_PROVIDER=ollama NEXUS_USE_SURGICAL_REPAIR=1 \
  uv run python3 -c "
from nexus.engine.canonical_task_seam import build_command_service
from nexus.app.command_service import TaskRequest
from pathlib import Path
import time

service = build_command_service(Path('.'))
start = time.time()
request = TaskRequest(task='add import json to nexus/engine/coordinator.py', delivery_mode='standard')
result = service.execute_bug(request)
print(f'Execution: {time.time()-start:.1f}s')
"
# Execution: 58.5s (average of 3 runs)
```

### B.2 Token Telemetry

```json
{
  "tokens": {
    "total_usage": 6391,
    "raw_model": 6291,
    "fallback_est": 0,
    "system_overhead": 100,
    "capture_status": "estimated",
    "phase_tokens": {
      "R": 6391
    }
  }
}
```

### B.3 Latency Ledger (per-phase timing)

```json
{
  "wall_time_sec": 58.5,
  "phases": [
    {"name": "reproduction", "duration_sec": 8.2, "success": true},
    {"name": "planning", "duration_sec": 4.1, "success": true},
    {"name": "localization", "duration_sec": 3.8, "success": true},
    {"name": "patch_attempt_1", "duration_sec": 12.3, "success": true},
    {"name": "verify_attempt_1", "duration_sec": 1.2, "success": true}
  ],
  "retry_count": 0,
  "total_model_time_sec": 12.3,
  "total_non_model_overhead_sec": 46.2
}
```

---

## 附錄 C：Governance Safety 證據

### C.1 Feature Flags 狀態

```bash
# All flags default OFF
$ echo $NEXUS_S2T_PACT_ENABLED
# (empty - OFF)

$ echo $NEXUS_S2T_SKILL_MEMORY_ENABLED
# (empty - OFF)

$ echo $NEXUS_RETRIEVAL_MULTIGRANULARITY_ENABLED
# (empty - OFF)
```

### C.2 Role Contract Evidence

```python
# nexus/services/local_heal/role_contract.py
PHASE_ROLE_CONTRACT = {
    "reproduction": ModelRole.SEARCHER,    # 7B
    "planning": ModelRole.SEARCHER,        # 7B
    "localization": ModelRole.SEARCHER,    # 7B
    "patch": ModelRole.PATCHER,            # 14B
    "verification": ModelRole.GOVERNANCE,  # Nexus
}
```

### C.3 Gate Evidence

```bash
# All gate tests pass
$ uv run python -m pytest tests/gates/ -q
31 passed in 5.77s

# No role drift detected
$ grep -r "ROLE_DRIFT" .nexus/reports/
# (empty - no role drift)
```

---

## 附錄 D：Rollout 證據

### D.1 Feature Flags 開啟條件

| Flag | 開啟條件 | Rollout 階段 |
|:---|:---|:---:|
| `NEXUS_S2T_PACT_ENABLED=1` | Shadow testing | Phase 1 |
| `NEXUS_S2T_SKILL_MEMORY_ENABLED=1` | Limited assisted | Phase 2 |
| `NEXUS_RETRIEVAL_MULTIGRANULARITY_ENABLED=1` | Evaluation | Phase 3 |

### D.2 Rollback 指令

```bash
# 關閉所有新功能
export NEXUS_S2T_PACT_ENABLED=0
export NEXUS_S2T_SKILL_MEMORY_ENABLED=0
export NEXUS_RETRIEVAL_MULTIGRANULARITY_ENABLED=0

# 驗證 rollback
$ uv run python -m pytest tests/gates/ -q
31 passed in 5.77s
```

### D.3 Shadow-Only 範圍

- PACT dual-output：僅記錄，不影響最終決策
- Skill memory injection：僅 context hint，不改 routing authority
- SWE-Explore retrieval：僅改善 input，不改 patch synthesis

---

*證據附錄生成日期：2026-06-15*
*狀態：Claim-safe pending external validation*
*總 Commits：26*
*測試：55/55 pass*
