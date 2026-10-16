# Nexus Session Status Report

**Date**: 2026-06-15
**Session**: vNext Active — Speed Optimization + Capability Uplift + Shadow Evaluation

---

## 1. 已完成工作

### 1.1 Speed Optimization（Phase 1）

| 改動 | 效果 |
|:---|:---|
| `num_predict` 512 | 141s → 64s（**-55%**） |
| Lazy imports | memory_indexer 5.8s → 0.03s |
| Token tracking fix | 0 → 6275 tokens |
| D1-D8 (prompt/路由優化) | ~0s speed improvement |

**結論**: 唯一真正加速的是 `num_predict=512`。D1-D8 是 correctness/cost 優化。

### 1.2 Capability Uplift（Phase 2-4）

| Slice | Commit | 內容 |
|:---|:---|:---|
| A | `17a997ad` | PACT schema + dual-output |
| B | `ed30251c` | Skill Memory Query Layer |
| C | `9b85e7cb` | SWE-Explore Lite |

**測試**: 55/55 pass

### 1.3 Latency Ledger + Infrastructure（Slice A-D）

| Commit | 內容 |
|:---|:---|
| `cc0ee644` | Latency Ledger (per-phase timing) |
| `353e84cb` | Persistent Worker pipe deadlock fix |
| `38c4a77e` | Lazy import heavy dependencies |
| `e4cd18a5` | Role Contract Freeze |

### 1.4 Shadow Evaluation

| Commit | 內容 |
|:---|:---|
| `1c9dce65` | Eval harness + 30-task bundle |
| `18784390` | 30-task shadow report (preliminary) |
| `8e008abc` | Updated report with stricter wording |
| `79fb4ad1` | Audit phase KeyError fix |

---

## 2. Shadow Evaluation 現況

### 2.1 發現的問題

**根本原因**: Audit phase 有 pre-existing bug — `KeyError: 'missing_funcs'`

```python
# 問題代碼
msg = f"❌ [Audit:FAILED] Parity Violation in {filepath}. Missing: {res['missing_funcs']}"

# 修復
missing = res.get("missing_funcs", [])
msg = f"❌ [Audit:FAILED] Parity Violation in {filepath}. Missing: {missing}"
```

**影響**: 所有 tasks 在 audit phase crash，導致 `execute_bug` 回傳 False。

**修復**: 已 commit `79fb4ad1`

### 2.2 修復驗證

```bash
# 手動測試
success: True (56.7s) ✅

# 語法檢查
python3 -m py_compile nexus/evaluation/eval_harness.py  # Syntax OK
```

### 2.3 待執行

4 組對照（每組 30 tasks）尚未完成執行：
- Baseline: 未完成
- PACT Only: 未完成
- PACT + Memory: 未完成
- Full Uplift: 未完成

---

## 3. 當前狀態

### 3.1 Commit 總覽
- **總 Commits**: 30+
- **基準 Commit**: `fad8f32e`
- **最新 Commit**: `79fb4ad1`

### 3.2 測試
- **Gate tests**: 31/31 pass
- **PACT tests**: 9/9 pass
- **Skill memory tests**: 7/7 pass
- **SWE-Explore tests**: 8/8 pass
- **Total**: 55/55 pass

### 3.3 Pipeline 狀態
- **手動測試**: `success: True (56.7s)` ✅
- **模型被呼叫**: `raw_model: 6275` ✅
- **Gate tests**: 31/31 pass ✅

### 3.4 Feature Flags
| Flag | 預設 | 狀態 |
|:---|:---:|:---:|
| `NEXUS_S2T_PACT_ENABLED` | OFF | 可啟用 |
| `NEXUS_S2T_SKILL_MEMORY_ENABLED` | OFF | 可啟用 |
| `NEXUS_RETRIEVAL_MULTIGRANULARITY_ENABLED` | OFF | 可啟用 |

---

## 4. 下一步

### 4.1 立即
1. 跑 4 組 shadow evaluation（每組 30 tasks）
2. 生成 divergence report + shadow metrics
3. 生成 final verdict

### 4.2 短期
1. 修正 eval harness 確保所有組走相同 code path
2. 補齊 medium/hard held-out tasks
3. 補 selector override analysis

### 4.3 中期
1. Persistent Worker IPC 重設計
2. Lazy load SentenceTransformer
3. 減少 pipeline phases

---

## 5. 風險與殘留

| 項目 | 狀態 |
|:---|:---:|
| Audit phase bug | ✅ 已修復 |
| Eval harness syntax | ✅ 已修復 |
| Persistent Worker | ⚠️ pipe deadlock 有 fix 但未完全驗證 |
| SentenceTransformer | ⚠️ 仍在 cold start 路徑（~5s） |
| Shadow evaluation | ⚠️ 4 組尚未跑完 |

---

*Report generated: 2026-06-15T05:30:00Z*
*Status: In progress — audit fix verified, evaluation pending*
