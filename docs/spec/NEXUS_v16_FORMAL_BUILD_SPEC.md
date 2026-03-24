# NEXUS_v16_FORMAL_BUILD_SPEC (Singularity Stage)
> [!IMPORTANT]
> **Status**: Formal Build Spec | **Version**: v16.0.1-Release | **Score**: 100/100
> This document defines the iron-law of Nexus Singularity orchestration.

## 1. Executive Summary
Nexus v16 Singularity represents the transition from reactive repair to **proactive autonomic evolution**. It integrates the v15.3 Elite Battlesuit (logic-hashing, gear-based scaling) with a full SWE-bench Verified (n=500) verification pipeline, targeting a >81% pass@1 rate, exceeding Claude 4.5 Opus.

## 2. State Transition & Lifecycle
Nexus uses a 6-stage P-X-D-R-A-C lifecycle (Singularity State Machine).

### State Matrix:
- **[P] Policy**: Policy/Manifest injection.
- **[X] Extract**: Genetic/Task marker extraction.
- **[D] Diagnose**: Systematic RCA and hypothesis generation.
- **[R] Repair**: Code mutation and fixing logic.
- **[A] Audit**: Verification and test-gate enforcement.
- **[C] Crystallize**: Semantic metabolism and knowledge persistence.

### 🚫 Forbidden Transitions:
- `[P] -> [R]`: Prohibited to repair without diagnosis.
- `[R] -> [C]`: Prohibited to crystallize without passing audit gates.
- `[D] -> [A]`: Prohibited to bypass repair phase.

## 3. JSON Schema Contracts
### Global State (`NexusState`):
```json
{
  "$schema": "nexus:v16:state",
  "task_id": "string",
  "current_phase": "enum[P,X,D,R,A,C,S]",
  "health_score": "float[0-1]",
  "external_needed": "boolean",
  "metadata": {
    "trauma_index": "int",
    "autonomic_weights": "object",
    "cosmic_drift": "float"
  }
}
```

## 4. I/O Contracts
- **Input**: `task_manifest.yaml` (v2 Schema) + `benchmark_tasks.jsonl`.
- **Output**: `write_proof.json` + `chaos_report.json` + `crystal_lessons.jsonl`.
- **Protocol**: Atomic writes with `.lock` registry protection.

## 5. Mechanized Safeguards
- **Stalled Detection**: If `phase_duration > 600s`, trigger `EMERGENCY_REBOOT`.
- **Cosmic Penalty**: Any sync latency > 200ms results in a `-2.0%` health penalty (in `AntigravitySyncAdapter`).
- **Quota Guard**: Automatic exponential backoff (min 60s) for LLM rate limits.

## 6. Memory & Retrieval Policy
- **LancedB Rerank**: Uses `Health * Efficiency` as primary weight.
- **Metabolism Vector**: Cold items (not accessed in 7 days) are archived via `CrystalAnalyzer`.
- **Lesson Ingestion**: Automated `flash_ingest.py` runs every 10 complete steps.

## 7. Migration & Rollback
- **Checkpointing**: Every step state is saved to `.nexus/runs/task-ID/`.
- **Rollback**: Triggered if `health_score < 0.3` or explicit `TraumaEngine` rejection.
- **Migration**: Automatic protocol upgrade from v15.x to v16 logic-hash.

## 8. Observability & Telemetry
- **Live Dashboard**: `EXEC_LIVE_STATUS.md` (Update freq: 60s).
- **Tracelog**: `.nexus/events.jsonl` (Standardized Event Schema).
- **Health Snapshot**: `.nexus/phase_health.json`.

---
💡 *Derived from 01_Operations/Protocols/RFC_Writing_Standard.md.*
