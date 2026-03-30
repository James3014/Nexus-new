# Nexus Self-Heal + Learning 研究底座交接（可直接給研究 Agent）

## 1) 你要的路徑對照（已就位）
研究代理原本提到的路徑是概念路徑（`nexus/memory/*`, `nexus/learning/*`）。目前實作在以下位置：

- 記憶與檢索層（MemoryService + LanceDB/Fallback）
  - `/Users/jameschen/Workspace/nexus/nexus/services/memory.py`
- 學習治理（Curiosity/Budget/Canary）
  - `/Users/jameschen/Workspace/nexus/nexus/core/learning_governance.py`
- 學習證據建構（Episode/Evidence）
  - `/Users/jameschen/Workspace/nexus/nexus/core/learning_evidence.py`
- 代謝引擎（PolicyMetabolizer）
  - `/Users/jameschen/Workspace/nexus/nexus/core/policy_metabolizer.py`
- 狀態合約（NexusState）
  - `/Users/jameschen/Workspace/nexus/nexus/core/state_contracts.py`

## 2) 與本輪強化相關的核心檔案
- Signature 抽取
  - `/Users/jameschen/Workspace/nexus/nexus/health/signature_extractor.py`
- Signature-based 診斷
  - `/Users/jameschen/Workspace/nexus/nexus/health/diagnostics.py`
- Speculative Sandbox + evidence 輸出
  - `/Users/jameschen/Workspace/nexus/nexus/health/sandbox.py`
  - `/Users/jameschen/Workspace/nexus/nexus/health/executor.py`
- 自癒協調與回灌（fault_hash, diagnosis_fidelity, sandbox_hit_rate）
  - `/Users/jameschen/Workspace/nexus/nexus/health/service.py`
- 健康信號整合（D/C 相位接 fidelity + sandbox）
  - `/Users/jameschen/Workspace/nexus/nexus/health/signals.py`

## 3) Fault Lessons（你要做 embedding/rerank 的入口）
### 已有 API（可直接用）
- `lookup_fault_lessons(fault_hash, limit)`
- `record_fault_lesson(fault_hash, error_type, diagnosis_kind, lesson, repair_patch, audit_pass_rate, metadata)`
- 定義位置：
  - `/Users/jameschen/Workspace/nexus/nexus/services/memory.py`

### 當前策略
- 優先 LanceDB table：`fault_lessons`
- 無 LanceDB 或表不存在時，降級 JSONL：
  - `/Users/jameschen/Workspace/nexus/.nexus/knowledge/fault_lessons.jsonl`

## 4) FaultSignature 是否掛入資料契約？
- 有完整 dataclass（health 層契約）：
  - `/Users/jameschen/Workspace/nexus/nexus/health/models.py`（`FaultSignature`）
- 在 `NexusState` 層目前是以 `metadata` 承載（`fault_hash`, `fault_signatures`, `diagnosis_fidelity`, `sandbox_hit_rate`），尚未升級為 `state_contracts.py` 顯式欄位。
- 若你要做嚴格 schema 化，下一步建議把以上欄位提升為 typed fields。

## 5) 研究代理可直接使用的故障樣本（20 組）
以下皆為真實 RCA 檔案，可直接做 signature/fidelity 壓測：

1. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_002542_elite.bench.016.md`
2. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152621_auto.repair.pipeline.md`
3. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152622_auto.repair.pipeline.md`
4. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152623_auto.repair.pipeline.md`
5. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152624_auto.repair.pipeline.md`
6. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152630_auto.repair.pipeline.md`
7. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152631_auto.repair.pipeline.md`
8. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152632_auto.repair.pipeline.md`
9. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152633_auto.repair.pipeline.md`
10. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152648_auto.repair.pipeline.md`
11. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152649_auto.repair.pipeline.md`
12. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152650_auto.repair.pipeline.md`
13. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_152651_auto.repair.pipeline.md`
14. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_153209_calib.guard.quota_sim.md`
15. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_153210_calib.guard.quota_sim.md`
16. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_153245_calib.guard.quota_sim.md`
17. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_153246_calib.guard.quota_sim.md`
18. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_163027_auto.repair.pipeline.md`
19. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_163028_auto.repair.pipeline.md`
20. `/Users/jameschen/Workspace/nexus/docs/incidents/RCA_163030_auto.repair.pipeline.md`

補充圖片證據（CLI 互動/長文壓測）：
- `/Users/jameschen/Workspace/nexus/logs/pilot/acheron_bracketed_paste_proof.png`
- `/Users/jameschen/Workspace/nexus/logs/pilot/acheron_real_answer_proof.png`
- `/Users/jameschen/Workspace/nexus/logs/pilot/acheron_real_answer_proof_readable.png`

## 6) 建議研究切入順序（最小風險）
1. 先做 `diagnosis_fidelity` 真實統計（按 `fault_hash` 建 confusion matrix）。
2. 把 `sandbox_hit_rate` 接進 planner 權重（低命中路徑自動降權）。
3. 對 `fault_lessons` 做 patch 片段 embedding + rerank（保留 hash exact match 作第一層 gate）。
4. 最後再把 metadata 欄位升級進 `state_contracts.py` typed schema。

## 7) 快速驗證指令
```bash
cd /Users/jameschen/Workspace/nexus
uv run pytest tests/health/test_signature_extractor.py tests/health/test_diagnostics.py tests/health/test_planner_executor.py tests/health/test_self_heal_service.py tests/test_memory.py -q
uv run scripts/engine/nexus_cli.py nexus:check --level high
```

