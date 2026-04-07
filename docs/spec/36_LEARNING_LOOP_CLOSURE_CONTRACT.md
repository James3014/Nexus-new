# 36_LEARNING_LOOP_CLOSURE_CONTRACT.md

**Purpose**: Formalize the required engineering stages to qualify the Nexus Learning System as a "Closed Loop".
**Source**: nexus/research/evidence_chain (Ref), brain_loop_closure.py (Ref)
**Commit**: v23.5-learning-spec-036
**Generated_at**: 2026-04-08 07:00

---

## 1. The 7-Step Closure Chain
To be considered "Closed", the knowledge must traverse these atomic stages without manual intervention:
1. **Source Event**: Identification of high-signal trace/log (MUSE_PROTO).
2. **Distillation**: AI-driven pruning of noise into structured "FindingsCard".
3. **Ingest**: Automated insertion into the `memory_repository` (LanceDB).
4. **Vectorization**: Real-time embedding generation for semantic retrieval.
5. **Retrieval**: System-wide availability for future task planning.
6. **Decision Reuse**: Actual utilization of previous findings in a new task.
7. **Writeback**: Promotion of proven findings to the Wiki Standard.

## 2. Partial vs Full Closed Loop
- **Partial Loop**: Requires a human or agent to manually run `brain_loop_closure.py`. Lineage is interrupted.
- **Full Closed Loop**: The system triggers closure automatically via **Post-Run Hooks**. Lineage is 100% serializable.

## 3. Audit & Acceptance Criteria
- **Lineage Probe**: A random finding MUST be traceable back to its source episode ID within 1 second.
- **Decision Delta**: New tasks MUST show a > 20% reduction in "re-discovery" steps compared to baseline.

---

# 37_BRAIN_LOOP_AUTOMATION_AND_TRIGGER_SPEC.md

**Purpose**: Define the automated execution triggers and daemon behavior for `brain_loop_closure.py`.
**Source**: scripts/ops/brain_loop_closure.py (Ref), swarm_harness.py (Ref)
**Commit**: v23.5-learning-spec-037
**Generated_at**: 2026-04-08 07:02

---

## 1. Trigger Points
The loop closure MUST trigger upon:
- **Task Success (Exit 0)**: Immediate ingestion of findings.
- **Swarm Batch End**: Batch distillation and cross-episode synthesis.
- **Context Distillation Trigger**: When session reset is required (v23.5 Spec-33).

## 2. Post-Run Hook Behavior
The `swarm_harness.py` will execute `brain_loop_closure.py --mode=async` as a child process. 
- **Non-blocking**: The main agent continues while the brain processes the past episode.
- **Environment**: All environment variables and lineage pointers are passed to the closure engine.

## 3. Idempotency & Duplicate Prevention
- **Episode Locking**: Every processed episode ID is stored in `.nexus/closure_log.json`.
- **Duplicate Check**: The closure engine will SKIP any episode already marked as `PROCESSED`.

## 4. Failure Logging & Manual Fallback
- **Failure**: On ingest failure, the payload is moved to `/tmp/nexus_dead_letters/` and triggers a HUD alert.
- **Manual Path**: `python brain_loop_closure.py --retry-dead-letters` provides the human-fix path.
